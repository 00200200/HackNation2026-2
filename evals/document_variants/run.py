"""Entry point: generate the variant corpus, run the app on it as a black box and write .cache/document-variants.json.

The app is driven exactly as `evals.run` drives it (same staging, command and scorer), so a number here is comparable
with a number there; only the documents differ.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from evals.document_variants.corpus import SOURCES, Item, build_cases, build_negatives
from evals.document_variants.report import MIN_SLICE_DOCS, build_report
from evals.metrics import load_prediction, score_doc
from evals.run import DEFAULT_CMD, ROOT, git_state, run_app, stage

RESULTS = ROOT / ".cache" / "document-variants.json"


def parse_cases(text: str) -> list[str]:
    """`1-10,15` -> przyklad_01 ... przyklad_10, przyklad_15."""
    numbers: set[int] = set()
    for part in text.split(","):
        low, _, high = part.partition("-")
        if int(high or low) < int(low):
            raise ValueError(f"empty range: {part}")
        numbers.update(range(int(low), int(high or low) + 1))
    chosen = [f"przyklad_{n:02d}" for n in sorted(numbers)]
    unknown = [name for name in chosen if name not in SOURCES]
    if unknown:
        raise ValueError(f"no such training case: {', '.join(unknown)}")
    return chosen


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evals.document_variants", description=__doc__)
    p.add_argument("--n", type=int, default=1, help="variants generated per training case (default 1)")
    p.add_argument(
        "--control",
        type=int,
        default=1,
        help="text-only control documents per training case, with the template's default wording (default 1)",
    )
    p.add_argument("--seed", type=int, default=2026, help="the same seed gives byte-identical PDFs (default 2026)")
    p.add_argument("--cases", default="1-60", help="training cases to re-render, e.g. 1-10,15 (default 1-60)")
    p.add_argument(
        "--scan-share", type=float, default=0.3, help="share of documents rasterised into scans (default 0.3)"
    )
    p.add_argument("--negatives", type=int, default=3, help="invented negatives per kind, 10 kinds (default 3)")
    p.add_argument(
        "--cmd", default=DEFAULT_CMD + " --jobs 2", help="app command with {input} and {output} placeholders"
    )
    p.add_argument("--out", type=Path, default=RESULTS, help="where to write the report")
    p.add_argument("--min-docs", type=int, default=MIN_SLICE_DOCS, help="smallest slice that is reported (default 5)")
    p.add_argument("--dump", type=Path, help="also write the PDFs and reference JSON here, for inspection")
    p.add_argument("--no-run", action="store_true", help="only generate (needs --dump), do not run the app")
    p.add_argument("--pred", type=Path, help="score outputs already written to DIR/<case>/<file stem>.json")
    return p


def dump(items: list[Item], destination: Path) -> None:
    for item in items:
        folder = destination / item.case
        folder.mkdir(parents=True, exist_ok=True)
        (folder / item.name).write_bytes(item.pdf)
        (folder / f"{Path(item.name).stem}.gold.json").write_text(
            json.dumps(item.gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    index = {f"{i.case}/{i.name}": i.tags for i in items}
    (destination / "tags.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def score(items: list[Item], args: argparse.Namespace) -> tuple[list, dict, float | None, str | None]:
    cases: dict[str, dict[str, dict]] = {}
    for item in items:
        cases.setdefault(item.case, {})[item.name] = item.gold
    with tempfile.TemporaryDirectory(prefix="odw-variants-") as tmp:
        data, in_dir, out_dir = Path(tmp) / "data", Path(tmp) / "input", Path(tmp) / "output"
        if args.pred:
            out_dir, elapsed, error = args.pred, None, None
            names = {(i.case, i.name): Path(i.name).stem for i in items}
        else:
            for item in items:
                (data / item.case).mkdir(parents=True, exist_ok=True)
                (data / item.case / item.name).write_bytes(item.pdf)
            in_dir.mkdir()
            out_dir.mkdir()
            names = stage(cases, data, in_dir)
            env = {**os.environ, "KIO_LLM_BASE_URL": "", "KIO_LLM_MODEL": "", "KIO_LLM_API_KEY": ""}
            env.pop("KIO_OCR_ENGINE", None)
            env.pop("KIO_CLASSES_DIR", None)
            elapsed, error = run_app(args.cmd, in_dir, out_dir, env=env)
            if error and not any(out_dir.rglob("*.json")):
                return [], {}, elapsed, error  # nothing to score; a partial failure is scored and reported instead
        paths = {(i.case, i.name): out_dir / i.case / f"{names[(i.case, i.name)]}.json" for i in items}
        docs = [score_doc(i.case, i.name, paths[(i.case, i.name)], i.gold) for i in items]
        preds = {key: load_prediction(path)[0] for key, path in paths.items()}
    return docs, preds, elapsed, error


def report_for(docs: list, tags: dict, items: list[Item], preds: dict, min_docs: int) -> dict:
    """The variants report, plus the control set (same facts, default wording) scored on its own."""
    golds = {(i.case, i.name): i.gold for i in items}
    control = [d for d in docs if tags[(d.case, d.file)]["set"] == "control"]
    drifted = [d for d in docs if tags[(d.case, d.file)]["set"] != "control"]
    report = build_report(drifted, tags, golds, preds, min_docs)
    report["control"] = build_report(control, tags, golds, preds, min_docs) if control else None
    return report


def num(value: float | None) -> str:
    """Three decimals, or n/a for a score that has no documents behind it (for example no negatives were generated)."""
    return "n/a" if value is None else f"{value:.3f}"


def show(results: dict, destination: Path) -> None:
    summary, args, control = results["summary"], results["args"], results["control"]
    media = ", ".join(f"{m} {part['docs']}" for m, part in results["by_medium"].items())
    print(
        f"variants: docs={results['n_docs']} cases={args['cases']} n={args['n']} control={args['control']} "
        f"seed={args['seed']} commit={results['commit'][:9]}"
    )
    if results["app_error"]:
        print(f"  the app exited with an error, unprocessed documents score as misses: {results['app_error']}")
    print(f"  drifted set ({media}): micro F1 {num(summary['micro_f1'])}  strict {num(summary['micro_f1_strict'])}")
    print(
        f"  classification accuracy {num(summary['classification_accuracy'])}"
        f"   negatives empty {num(summary['negatives_empty'])}"
    )
    print("  per class F1:", {k: round(v, 3) for k, v in summary["per_class_f1"].items()})
    for gold, row in results["confusion"].items():
        wrong = {pred: n for pred, n in row.items() if pred != gold}
        if wrong:
            print(
                f"  routing: {sum(row.values()) - sum(wrong.values())}/{sum(row.values())} {gold} right, instead {wrong}"
            )
    for medium, part in results["by_medium"].items():
        print(f"  {medium}: micro F1 {num(part['micro_f1'])} over {part['docs']} docs")
    if control:
        print(
            f"  control set (same facts, default wording): micro F1 {num(control['summary']['micro_f1'])}"
            f"  strict {num(control['summary']['micro_f1_strict'])}"
        )
        print("    per class F1:", {k: round(v, 3) for k, v in control["summary"]["per_class_f1"].items()})
        for path, row in list(control["by_field"].items())[:5]:
            print(f"    {path:46} F1 {num(row['f1'])}  tp={row['tp']} fp={row['fp']} fn={row['fn']}")
    print("  weakest fields (drifted set):")
    for path, row in list(results["by_field"].items())[:8]:
        print(f"    {path:48} F1 {num(row['f1'])}  tp={row['tp']} fp={row['fp']} fn={row['fn']}")
    print("  weakest slices (drifted set):")
    for row in results["slices"][:10]:
        print(f"    {row['medium']:5} {row['tag']}={row['value']:22} F1 {num(row['micro_f1'])}  docs={row['docs']}")
    print(f"written: {destination}")


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    try:
        sources = parse_cases(args.cases)
    except ValueError as exc:
        p.error(str(exc))
    if min(args.n, args.control, args.negatives) < 0:
        p.error("--n, --control and --negatives must be nonnegative")
    if not 0 <= args.scan_share <= 1:
        p.error("--scan-share must be between 0 and 1")
    if args.min_docs < 1:
        p.error("--min-docs must be positive")
    if args.no_run and not args.dump:
        p.error("--no-run needs --dump")
    items = build_cases(sources, args.n, args.seed, args.scan_share) + build_negatives(
        args.negatives, args.seed, args.scan_share
    )
    items += build_cases(
        sources, args.control, args.seed, 0.0, faithful=True
    )  # text only: scans are in the drifted set
    if not items:
        p.error("nothing to generate: --n, --control and --negatives are all zero")
    if args.dump:
        dump(items, args.dump)
    if args.no_run:
        print(f"generated {len(items)} documents in {args.dump}")
        return 0
    docs, preds, elapsed, app_error = score(items, args)
    if not docs:
        print(f"app failed: {app_error}", file=sys.stderr)
        return 2
    tags = {(i.case, i.name): i.tags for i in items}
    commit, dirty = git_state()
    digest = hashlib.sha256()
    for item in items:
        digest.update(hashlib.sha256(item.pdf).digest())
        metadata = [item.case, item.name, item.gold, item.tags]
        digest.update(hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).digest())
    results = {
        "dataset_sha256": digest.hexdigest(),
        "commit": commit,
        "dirty": dirty,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "args": {
            "n": args.n,
            "control": args.control,
            "seed": args.seed,
            "cases": args.cases,
            "scan_share": args.scan_share,
            "negatives": args.negatives,
        },
        "n_docs": len(docs),
        "app_error": app_error and app_error[-600:],
        "seconds_per_doc": None if elapsed is None else elapsed / len(docs),
        "metric": "micro_f1 is the organizer formula of evals/metrics.py (UZP #59); micro_f1_strict is exact leaf match",
        **report_for(docs, tags, items, preds, args.min_docs),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    show(results, args.out)
    return 1 if app_error or any(doc.errors for doc in docs) else 0
