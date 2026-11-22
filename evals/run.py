"""Score the app on organizer training cases or a paired PDF and JSON corpus (field-level F1).

    uv run python -m evals.run --quick                 # small dev subset, before a push
    uv run python -m evals.run                         # all 60 cases + negatives, before submitting
    uv run python -m evals.run --pred output/          # score an existing output tree, no app run
    uv run python -m evals.run --corpus DIR            # cases/<case>/*.pdf with matching gold/<case>/*.json

The app is called as a black box with the jury's contract: `input/<case>/*.pdf` -> `output/<case>/<stem>.json`.
PDFs are copied under neutral names, so classification cannot lean on file names.
Command: `--cmd` or `ODW_CMD`, with `{input}` and `{output}` placeholders.
"""

import argparse
import json
import logging
import os
import random
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from pdfminer import settings as pdf_settings

from evals.metrics import (
    CLASSES,
    NEGATIVE,
    DocResult,
    flatten,
    load_reference,
    reject_json_constant,
    score_doc,
    summarise,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "uzp" / "dane"
RESULTS = ROOT / "evals" / "results" / "latest.json"
DEFAULT_CMD = "uv run python -m kio2json --input {input} --output {output}"
GOLD_FOR = {"odwolanie.pdf": "odwolanie.json", "pelnomocnictwo.pdf": "pelnomocnictwo.json"}
GOLD_FOR["potwierdzenie_przelewu.pdf"] = "przelew.json"
QUICK = {"przyklad_01", "przyklad_02", "przyklad_03", "przyklad_04", "przyklad_05", "przyklad_24", "negatywne"}
FULL = {f"przyklad_{n:02d}" for n in range(1, 61)} | {"negatywne"}
HOLDOUT = {f"przyklad_{n}" for n in range(51, 61)}
NON_PRODUCT_RE = re.compile(
    r"^(docs/|data/|\.claude/|\.githooks/|\.github/|evals/results/)|^(\.gitignore|LICENSE.*)$|\.md$"
)
TIMEOUT_S = int(os.environ.get("ODW_TIMEOUT_S", "3600"))
F1_TARGET = float(os.environ.get("ODW_F1_TARGET", "0.90"))  # team target, not an organizer threshold


def check_pdf(path: Path) -> None:
    # Precomputed predictions and custom commands must score the same readable inputs.
    with path.open("rb") as stream:
        previous_strict = pdf_settings.STRICT
        try:
            with pdfplumber.open(stream) as pdf:
                if not pdf.pages:
                    # Some readable PDFs have a page tree only PDFium can recover.
                    stream.seek(0)
                    with pdfium.PdfDocument(stream) as rendered:
                        if not len(rendered):
                            raise ValueError("empty page tree")
                        for page in rendered:
                            page.render(scale=512 / max(page.get_size())).close()
                            page.close()
                    return
                # pdfminer otherwise recovers damaged compressed streams as empty content.
                pdf_settings.STRICT = True
                for page in pdf.pages:
                    page.extract_text()
                    page.close()
        except OSError:
            raise
        except Exception as exc:  # PDF parsers raise several unrelated errors for damaged input.
            raise ValueError("a selected PDF could not be decoded") from exc
        finally:
            pdf_settings.STRICT = previous_strict


def case_names(directory: Path) -> set[str]:
    return {p.name for p in directory.iterdir() if stat.S_ISDIR(p.stat().st_mode)}


def files_with_suffixes(directory: Path, *suffixes: str) -> set[str]:
    names = set()
    for path in directory.iterdir():
        if path.suffix.lower() in suffixes:
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("a selected document or reference is not a regular file")
            names.add(path.name)
    return names


def training_inventory() -> dict[str, set[str]]:
    # Organizer negatives have no JSON. The pinned tree identifies them even if a local PDF is lost.
    try:
        raw = subprocess.check_output(
            ["git", "ls-tree", "-rz", "--name-only", "HEAD:data/uzp/dane"],
            cwd=ROOT,
            stderr=subprocess.PIPE,
            timeout=10,
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        )
    except subprocess.SubprocessError as exc:
        raise ValueError("cannot read the committed organizer training inventory") from exc
    inventory = defaultdict(set)
    for entry in raw.split(b"\0"):
        path = Path(os.fsdecode(entry))
        if len(path.parts) >= 2 and path.suffix.lower() in {".pdf", ".json"}:
            inventory[path.parts[0]].add(Path(*path.parts[1:]).as_posix())
    return inventory


def load_cases(data: Path, quick: bool, *, holdout: bool = False) -> dict[str, dict[str, dict]]:
    selected = HOLDOUT if holdout else QUICK if quick else FULL
    inventory = training_inventory()
    if not (quick or holdout) and case_names(data) - {"skany"} != FULL:
        raise ValueError("full training requires cases 01–60 and the negatives directory")
    cases = {}
    for case in sorted(selected):
        folder = data / case
        expected = inventory[case]
        found = files_with_suffixes(folder, ".pdf", ".json")
        pdfs = sorted(name for name in expected if name.lower().endswith(".pdf"))
        if case == "negatywne" and quick:
            pdfs = pdfs[:3]
            if len(pdfs) != 3:
                raise ValueError("quick training requires the first three organizer negatives")
            selected_stems = {Path(name).stem for name in pdfs}
            found = {name for name in found if Path(name).stem in selected_stems}
            expected = {name for name in expected if Path(name).stem in selected_stems}
        if found != expected or not pdfs:
            raise ValueError(f"training files differ from the committed organizer inventory in {case}")
        positive_refs = {pdf: GOLD_FOR[pdf] for pdf in pdfs if pdf in GOLD_FOR}
        if "przelew.pdf" in pdfs:
            positive_refs["przelew.pdf"] = "przelew.json"
        if case != "negatywne" and sorted(positive_refs.values()) != sorted(GOLD_FOR.values()):
            raise ValueError(f"missing required organizer PDF in {case}")
        refs = {name for name in found if name.lower().endswith(".json")}
        pairs = {name: positive_refs.get(name, Path(name).with_suffix(".json").name) for name in pdfs}
        if not refs <= set(pairs.values()):
            raise ValueError(f"an organizer reference has no corresponding PDF in {case}")
        docs = {}
        for name in pdfs:
            check_pdf(folder / name)
            ref = pairs[name]
            reference = load_reference(folder / ref) if name in positive_refs or ref in refs else {}
            if name in positive_refs:
                marker = CLASSES[Path(ref).stem]
                markers = reference.keys() & CLASSES.values()
                if markers != {marker} or not flatten(reference[marker]):
                    raise ValueError(f"organizer reference {case}/{ref} must contain fields for its expected class")
            docs[name] = reference
        cases[case] = docs
    return cases


def load_organizer_scans(data: Path) -> dict[str, dict[str, dict]]:
    """Stage the nested public scan pairs as one batch with neutral document names."""
    folder = data / "skany"
    expected = training_inventory().get("skany", set())
    found = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.suffix.lower() in {".pdf", ".json"}}
    pdfs = sorted(name for name in found if name.endswith(".pdf"))
    references = {Path(name).with_suffix(".json").as_posix() for name in pdfs}
    if not pdfs or found != expected or found != references | set(pdfs):
        raise ValueError("organizer scan pairs differ from the committed inventory")
    groups = {"odwolania": "odwolanie", "pelnomocnictwa": "pelnomocnictwo", "potwierdzenia": "przelew"}
    cases = {}
    for name in pdfs:
        check_pdf(folder / name)
        gold = load_reference((folder / name).with_suffix(".json"))
        label = groups.get(Path(name).parts[0])
        if label is None or gold.keys() & CLASSES.values() != {CLASSES[label]} or not flatten(gold[CLASSES[label]]):
            raise ValueError("organizer scan reference must contain fields for its expected class")
        # Files in different scan folders are independent examples, even when their stems match.
        relative = Path("skany", name)
        cases.setdefault(relative.parent.as_posix(), {})[relative.name] = gold
    return cases


def corpus_partition(root: Path, split: str, folders: set[str]) -> set[str]:
    """Validate the whole-case split and return the case names to score."""
    manifest = root / "SPLIT.json"
    try:
        mode = manifest.stat().st_mode
    except FileNotFoundError:
        if split == "all" and not manifest.is_symlink():
            return folders
        raise ValueError("--split dev or test requires a readable SPLIT.json in the corpus") from None
    if not stat.S_ISREG(mode):
        raise ValueError("SPLIT.json must be a regular file")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"), parse_constant=reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("SPLIT.json must contain a JSON object with dev and test lists") from exc
    parts = {}
    for label in ("dev", "test"):
        names = data.get(label) if isinstance(data, dict) else None
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError("SPLIT.json must contain dev and test lists of case folder names")
        parts[label] = set(names)
        if len(parts[label]) != len(names):
            raise ValueError("duplicate case in SPLIT.json")
    names = parts["dev"] | parts["test"]
    if parts["dev"] & parts["test"] or folders != names:
        raise ValueError("SPLIT.json must assign every case folder to exactly one split")
    return folders if split == "all" else parts[split]


def load_corpus(root: Path, split: str = "all") -> dict[str, dict[str, dict]]:
    """Pair every PDF with its reference by case and stem. An empty reference explicitly labels a negative."""
    data, gold = root / "cases", root / "gold"
    folders = case_names(data)
    selected = corpus_partition(root, split, folders)
    if split == "all" and case_names(gold) != folders:
        raise ValueError("case folders differ between the PDF and reference trees")
    if not selected:
        raise ValueError("the selected corpus split contains no cases")
    cases = {}
    for case in sorted(selected):
        pdfs = files_with_suffixes(data / case, ".pdf")
        references = files_with_suffixes(gold / case, ".json")
        pairs = {name: Path(name).with_suffix(".json").name for name in pdfs}
        if not pairs or len(pairs) != len(references) or set(pairs.values()) != references:
            raise ValueError("each selected case needs PDFs paired one-to-one with gold references")
        docs = {}
        for name in sorted(pairs):
            check_pdf(data / case / name)
            docs[name] = load_reference(gold / case / pairs[name])
        cases[case] = docs
    return cases


def stage(cases: dict[str, dict[str, dict]], data: Path, input_dir: Path) -> dict[tuple[str, str], str]:
    """Copy PDFs under shuffled neutral names. Returns {(case, original name): staged stem}."""
    names: dict[tuple[str, str], str] = {}
    rng = random.Random(2026)
    for case, docs in cases.items():
        order = list(docs)
        rng.shuffle(order)
        (input_dir / case).mkdir(parents=True)
        for i, name in enumerate(order, 1):
            stem = f"dokument_{i:02d}"
            shutil.copy(data / case / name, input_dir / case / f"{stem}.pdf")
            names[(case, name)] = stem
    return names


def run_app(cmd: str, input_dir: Path, output_dir: Path, *, env: dict | None = None) -> tuple[float, str | None]:
    args = [a.format(input=input_dir, output=output_dir) for a in shlex.split(cmd)]
    start = time.monotonic()
    try:
        proc = subprocess.run(args, check=False, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return time.monotonic() - start, f"{type(exc).__name__}: {exc}"
    error = None if proc.returncode == 0 else f"exit {proc.returncode}: {proc.stderr.strip()[-2000:]}"
    return time.monotonic() - start, error


def git_state() -> tuple[str, bool]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], check=False, cwd=ROOT, capture_output=True, text=True).stdout

    changed = [line[3:] for line in git("status", "--porcelain").splitlines()]
    return git("rev-parse", "HEAD").strip(), any(not NON_PRODUCT_RE.search(p) for p in changed)


def metric(value: float | None, target: float | None, higher_is_better: bool = True) -> dict:
    passed = None if value is None or target is None else (value >= target if higher_is_better else value <= target)
    return {"value": value, "target": target, "pass": passed}


def build_results(docs: list[DocResult], mode: str, seconds_per_doc: float | None, cases: dict):
    summary = summarise(docs)
    holdout = summarise([d for d in docs if d.case in HOLDOUT]) if mode == "full" else None
    metrics = {
        "micro_f1": metric(summary["micro_f1"], F1_TARGET),
        "outputs_complete": metric(summary["outputs_complete"], 1.0),
        "negatives_empty": metric(summary["negatives_empty"], 1.0),
        "classification_accuracy": metric(summary["classification_accuracy"], 1.0),
        "seconds_per_doc": {"value": seconds_per_doc, "target": None, "pass": True},
    }
    commit, dirty = git_state()
    n_cases = len(cases) if mode == "corpus" else sum(1 for c in cases if c != "negatywne")
    coverage_ok = mode == "full" and cases.keys() == FULL
    required = [m for m in metrics.values() if mode in {"quick", "full"} or m["value"] is not None]
    metrics["micro_f1_strict"] = metric(summary["micro_f1_strict"], None)
    return {
        "commit": commit,
        "dirty": dirty,
        "mode": mode,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_cases": n_cases,
        "n_docs": len(docs),
        "coverage_ok": coverage_ok,
        "overall_pass": bool(docs) and (mode != "full" or coverage_ok) and all(m["pass"] is True for m in required),
        "run_error": None,
        "metrics": metrics,
        "detail": summary,
        "holdout_51_60": holdout,
        "f1_definition": "UZP #59 with RapidFuzz normalized Levenshtein >= 0.80 on five long fields",
    }


def document_rows(docs: list[DocResult]) -> list[dict]:
    return [
        {
            "case": d.case,
            "file": d.file,
            "gold_class": d.gold_class,
            "pred_class": d.pred_class,
            "counts": asdict(d.counts),
            "counts_strict": {k: v for k, v in asdict(d.counts_strict).items() if k != "tn"},
            "counts_non_null": {k: v for k, v in asdict(d.counts_non_null).items() if k != "tn"},
            "errors": d.errors,
        }
        for d in docs
    ]


def external_detail_path(value: str) -> Path:
    # A caller such as a Git hook may export a different repository or index.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=ROOT, env=env, stderr=subprocess.PIPE, timeout=10)

    try:
        path = Path(value).resolve()
        protected = {ROOT.resolve()}
        for entry in git("worktree", "list", "--porcelain", "-z").split(b"\0"):
            if entry.startswith(b"worktree "):
                protected.add(Path(os.fsdecode(entry.removeprefix(b"worktree "))).resolve())
        for option in ("--git-common-dir", "--git-dir"):
            raw = git("rev-parse", "--path-format=absolute", option)
            protected.add(Path(os.fsdecode(raw.removesuffix(b"\n"))).resolve())

        # samefile also catches case aliases on case-insensitive volumes.
        ancestors = (path, *path.parents)
        for root in protected:
            if root in ancestors or (root.is_dir() and any(p.is_dir() and p.samefile(root) for p in ancestors)):
                raise argparse.ArgumentTypeError(
                    "detail output must be outside all repository worktrees and Git metadata"
                )
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise argparse.ArgumentTypeError("cannot verify the private output destination") from exc
    return path


@contextmanager
def input_errors(parser: argparse.ArgumentParser, corpus: Path | None):
    # PDF libraries can log document metadata while decoding a page. CLI diagnostics are emitted below.
    previous_level = logging.root.manager.disable
    if corpus is not None:
        logging.disable(logging.CRITICAL)
    try:
        yield
    except OSError as exc:
        if corpus is None:
            parser.error(str(exc))
        parser.exit(2, f"corpus I/O errors=1 ({type(exc).__name__})\n")
    except UnicodeError:
        parser.error("input is not valid UTF-8")
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        if corpus is not None:
            logging.disable(previous_level)


@contextmanager
def private_output(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as staging:
        report = Path(staging) / "detail"
        report.touch(mode=0o600)
        with report.open("w", encoding="utf-8") as stream:
            yield stream
        report.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode_args = parser.add_mutually_exclusive_group()
    mode_args.add_argument("--variants", type=int, metavar="N", help="generate and score N synthetic case variants")
    parser.add_argument("--variant-baseline", type=Path, help="gate on a previous report for the same variant set")
    parser.add_argument(
        "--variant-out", type=Path, help="variant report destination (default evals/results/variants.json)"
    )
    mode_args.add_argument("--quick", action="store_true", help="dev subset: 6 cases + 3 negatives")
    mode_args.add_argument("--organizer-scans", action="store_true", help="score the organizer’s labelled scan set")
    mode_args.add_argument("--corpus", type=Path, help="corpus with separate cases/ and gold/ trees")
    parser.add_argument(
        "--split", choices=("dev", "test", "all"), help="case partition in corpus SPLIT.json (default all)"
    )
    parser.add_argument(
        "--detail-out", type=external_detail_path, help="write corpus document rows to this file outside the repository"
    )
    parser.add_argument("--cmd", default=os.environ.get("ODW_CMD", DEFAULT_CMD))
    parser.add_argument("--pred", type=Path, help="score this output tree (original file names) instead of running")
    parser.add_argument("--data", type=Path, help="override the organizer training data directory")
    args = parser.parse_args()

    with input_errors(parser, args.corpus):
        return evaluate(args, parser)


def evaluate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.variants is not None:
        if args.variants < 1 or args.pred or args.detail_out or args.split:
            parser.error("--variants requires a positive count and runs the extractor on generated inputs")
        from evals.variants import evaluate_variants

        cmd = DEFAULT_CMD + " --jobs 2" if args.cmd == DEFAULT_CMD else args.cmd
        destination = args.variant_out or RESULTS.with_name("variants.json")
        if args.variant_baseline:
            destination = args.variant_out or ROOT / ".cache" / "variants-current.json"
            if destination.resolve() == args.variant_baseline.resolve():
                parser.error("the candidate report and baseline need distinct paths")
        return evaluate_variants(
            args.variants,
            args.data or DATA,
            cmd,
            destination,
            args.variant_baseline,
        )
    if args.variant_out or args.variant_baseline:
        parser.error("--variant-out and --variant-baseline require --variants")
    if (args.detail_out or args.split) and not args.corpus:
        parser.error("--detail-out and --split require --corpus")
    if args.corpus:
        if args.data:
            parser.error("--data and --corpus select different layouts and cannot be used together")
        mode, data = "corpus", args.corpus / "cases"
        cases = load_corpus(args.corpus, args.split or "all")
    elif args.organizer_scans:
        mode, data = "organizer-scans", args.data or DATA
        cases = load_organizer_scans(data)
    else:
        mode, data = ("quick" if args.quick else "full"), args.data or DATA
        if not data.is_dir():
            print(f"no data at {data}; run: make data", file=sys.stderr)
            return 2
        cases = load_cases(data, args.quick)
    n_docs = sum(len(d) for d in cases.values())

    with tempfile.TemporaryDirectory(prefix="odw-eval-") as tmp:
        if args.pred:
            out_dir, elapsed = args.pred, None
            names = {(c, n): Path(n).with_suffix("").as_posix() for c, docs in cases.items() for n in docs}
        else:
            in_dir, out_dir = Path(tmp) / "input", Path(tmp) / "output"
            in_dir.mkdir()
            names = stage(cases, data, in_dir)
            out_dir.mkdir()
            elapsed, run_error = run_app(args.cmd, in_dir, out_dir)
            if run_error:
                parser.exit(2, "app failed\n" if args.corpus else f"app failed: {run_error}\n")
        docs = [
            score_doc(case, name, out_dir / case / f"{names[(case, name)]}.json", gold)
            for case, items in cases.items()
            for name, gold in items.items()
        ]

    seconds_per_doc = None if elapsed is None or not n_docs else elapsed / n_docs
    results = build_results(docs, mode, seconds_per_doc, cases)
    destination = RESULTS
    if args.corpus or args.organizer_scans:
        results["split"] = args.split or "all"
        routing = {}
        for label in (*CLASSES, NEGATIVE):
            selected = [d for d in docs if d.gold_class == label]
            correct = sum(d.empty_output if label == NEGATIVE else d.pred_class == label for d in selected)
            routing[label] = {"correct": correct, "total": len(selected)}
        results["detail"]["routing_by_class"] = routing
        destination = RESULTS.with_name("organizer-scans.json" if args.organizer_scans else "corpus-latest.json")
        if args.detail_out:
            with private_output(args.detail_out) as tmp:
                json.dump({**results, "docs": document_rows(docs)}, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
    else:
        results["docs"] = document_rows(docs)
    payload = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    if not (args.corpus or args.organizer_scans):
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"], check=False, cwd=ROOT, capture_output=True, text=True
        ).stdout
        if git_dir.strip():
            (ROOT / git_dir.strip() / "eval-latest.json").write_text(payload, encoding="utf-8")

    selection = f" split={results['split']}" if args.corpus else ""
    print(
        f"mode={mode}{selection} cases={results['n_cases']} docs={n_docs} commit={results['commit'][:9]} dirty={results['dirty']}"
    )
    for name, m in results["metrics"].items():
        value = "unknown" if m["value"] is None else f"{m['value']:.3f}"
        if name == "micro_f1_strict":
            print(f"  {name:24} {value:>8}  historical comparison")
            continue
        print(f"  {name:24} {value:>8}  target={m['target']}  pass={m['pass']}")
        if name == "micro_f1":
            for macro in ("macro_f1_documents", "macro_f1_classes", "macro_f1_fields"):
                score = results["detail"][macro]
                value = "unknown" if score is None else f"{score:.3f}"
                context = ""
                if macro == "macro_f1_classes":
                    classes = ", ".join(results["detail"]["per_class_f1"]) or "none"
                    context = f"  classes={results['detail']['macro_f1_class_count']} ({classes})"
                print(f"  {macro:24} {value:>8}{context}")
    print(
        "  per class F1:", {k: None if v is None else round(v, 3) for k, v in results["detail"]["per_class_f1"].items()}
    )
    if holdout := results["holdout_51_60"]:
        print(f"  holdout 51-60 micro F1: {holdout['micro_f1']}")
    print(f"written: {destination.relative_to(ROOT)}")
    return 0 if results["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
