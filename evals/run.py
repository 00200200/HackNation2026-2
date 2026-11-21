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
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from evals.metrics import DocResult, load_json, score_doc, summarise

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "uzp" / "dane"
RESULTS = ROOT / "evals" / "results" / "latest.json"
DEFAULT_CMD = "uv run python -m kio2json --input {input} --output {output}"
GOLD_FOR = {"odwolanie.pdf": "odwolanie.json", "pelnomocnictwo.pdf": "pelnomocnictwo.json"}
GOLD_FOR["potwierdzenie_przelewu.pdf"] = "przelew.json"
QUICK = {"przyklad_01", "przyklad_02", "przyklad_03", "przyklad_04", "przyklad_05", "przyklad_24", "negatywne"}
HOLDOUT = {f"przyklad_{n}" for n in range(51, 61)}
NON_PRODUCT_RE = re.compile(
    r"^(docs/|data/|\.claude/|\.githooks/|\.github/|evals/results/)|^(\.gitignore|LICENSE.*)$|\.md$"
)
TIMEOUT_S = int(os.environ.get("ODW_TIMEOUT_S", "3600"))
F1_TARGET = float(os.environ.get("ODW_F1_TARGET", "0.90"))  # team target, not an organizer threshold


def load_cases(data: Path, quick: bool) -> dict[str, dict[str, dict]]:
    """{case: {pdf name: gold dict}}; negatives have an empty gold dict."""
    cases: dict[str, dict[str, dict]] = {}
    for case_dir in sorted(p for p in data.iterdir() if p.is_dir()):
        if quick and case_dir.name not in QUICK:
            continue
        pdfs = sorted(case_dir.glob("*.pdf"))
        if quick and case_dir.name == "negatywne":
            pdfs = pdfs[:3]
        cases[case_dir.name] = {
            pdf.name: (load_json(case_dir / GOLD_FOR[pdf.name]) or {}) if pdf.name in GOLD_FOR else {} for pdf in pdfs
        }
    return cases


def load_corpus(root: Path) -> dict[str, dict[str, dict]]:
    """Pair every PDF with its reference by case and stem. An empty reference explicitly labels a negative."""
    data, gold = root / "cases", root / "gold"
    if not data.is_dir() or not gold.is_dir():
        raise ValueError("corpus must contain cases/ and gold/ directories")
    cases: dict[str, dict[str, dict]] = {}
    references = {p.relative_to(gold) for p in gold.glob("*/*.json") if p.is_file()}
    for pdf in sorted(data.glob("*/*.pdf", case_sensitive=False)):
        if not pdf.is_file():
            continue
        relative = pdf.relative_to(data).with_suffix(".json")
        if relative not in references:
            raise ValueError(f"missing or already matched reference: gold/{relative}")
        reference = load_json(gold / relative)
        if reference is None:
            raise ValueError(f"invalid reference: gold/{relative}")
        references.remove(relative)
        cases.setdefault(pdf.parent.name, {})[pdf.name] = reference
    if references:
        raise ValueError(f"reference has no matching PDF: gold/{min(references)}")
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


def run_app(cmd: str, input_dir: Path, output_dir: Path) -> tuple[float, str | None]:
    args = [a.format(input=input_dir, output=output_dir) for a in shlex.split(cmd)]
    start = time.monotonic()
    try:
        proc = subprocess.run(args, check=False, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S)
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


def build_results(docs: list[DocResult], mode: str, seconds_per_doc: float | None, cases: dict, run_error: str | None):
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
    required = [m for m in metrics.values() if mode != "corpus" or m["value"] is not None]
    return {
        "commit": commit,
        "dirty": dirty,
        "mode": mode,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_cases": n_cases,
        "n_docs": len(docs),
        "coverage_ok": mode == "full" and n_cases >= 60 and "negatywne" in cases,
        "overall_pass": bool(docs) and run_error is None and all(m["pass"] is True for m in required),
        "run_error": "app failed" if mode == "corpus" and run_error else run_error,
        "metrics": metrics,
        "detail": summary,
        "holdout_51_60": holdout,
        "f1_definition": "evals/metrics.py docstring (organizer formula UNCONFIRMED)",
    }


def document_rows(docs: list[DocResult]) -> list[dict]:
    return [
        {
            "case": d.case,
            "file": d.file,
            "gold_class": d.gold_class,
            "pred_class": d.pred_class,
            "counts": asdict(d.counts),
            "counts_non_null": asdict(d.counts_non_null),
            "errors": d.errors,
        }
        for d in docs
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode_args = parser.add_mutually_exclusive_group()
    mode_args.add_argument("--quick", action="store_true", help="dev subset: 6 cases + 3 negatives")
    mode_args.add_argument("--corpus", type=Path, help="corpus with separate cases/ and gold/ trees")
    parser.add_argument(
        "--detail-out", type=Path, help="write corpus document rows to this file outside the repository"
    )
    parser.add_argument("--cmd", default=os.environ.get("ODW_CMD", DEFAULT_CMD))
    parser.add_argument("--pred", type=Path, help="score this output tree (original file names) instead of running")
    parser.add_argument("--data", type=Path, help="override the organizer training data directory")
    args = parser.parse_args()

    if args.detail_out:
        detail_path = args.detail_out.resolve()
        if not args.corpus or any(p.is_dir() and p.samefile(ROOT) for p in (detail_path, *detail_path.parents)):
            parser.error("--detail-out requires --corpus and a destination outside the repository")
    if args.corpus:
        if args.data:
            parser.error("--data and --corpus select different layouts and cannot be used together")
        mode, data = "corpus", args.corpus / "cases"
        try:
            cases = load_corpus(args.corpus)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    else:
        mode, data = ("quick" if args.quick else "full"), args.data or DATA
        if not data.is_dir():
            print(f"no data at {data}; run: make data", file=sys.stderr)
            return 2
        cases = load_cases(data, args.quick)
    n_docs = sum(len(d) for d in cases.values())

    with tempfile.TemporaryDirectory(prefix="odw-eval-") as tmp:
        if args.pred:
            out_dir, run_error, elapsed = args.pred, None, None
            names = {(c, n): Path(n).stem for c, docs in cases.items() for n in docs}
        else:
            in_dir, out_dir = Path(tmp) / "input", Path(tmp) / "output"
            in_dir.mkdir()
            names = stage(cases, data, in_dir)
            out_dir.mkdir()
            elapsed, run_error = run_app(args.cmd, in_dir, out_dir)
        docs = [
            score_doc(case, name, out_dir / case / f"{names[(case, name)]}.json", gold)
            for case, items in cases.items()
            for name, gold in items.items()
        ]

    seconds_per_doc = None if elapsed is None or not n_docs else elapsed / n_docs
    results = build_results(docs, mode, seconds_per_doc, cases, run_error)
    destination = RESULTS
    if args.corpus:
        destination = RESULTS.with_name("corpus-latest.json")
        if args.detail_out:
            detail_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=detail_path.parent, encoding="utf-8", delete=False) as tmp:
                json.dump({**results, "docs": document_rows(docs)}, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            Path(tmp.name).replace(detail_path)
    else:
        results["docs"] = document_rows(docs)
    payload = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    if not args.corpus:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"], check=False, cwd=ROOT, capture_output=True, text=True
        ).stdout
        if git_dir.strip():
            (ROOT / git_dir.strip() / "eval-latest.json").write_text(payload, encoding="utf-8")

    if run_error:
        print("app failed" if args.corpus else f"app failed: {run_error}", file=sys.stderr)
    print(
        f"mode={mode} cases={results['n_cases']} docs={n_docs} commit={results['commit'][:9]} dirty={results['dirty']}"
    )
    for name, m in results["metrics"].items():
        value = "unknown" if m["value"] is None else f"{m['value']:.3f}"
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
