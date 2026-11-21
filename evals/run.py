"""Run the app on the organizer's training cases and score it like the jury (field-level F1).

    uv run python -m evals.run --quick                 # small dev subset, before a push
    uv run python -m evals.run                         # all 60 cases + negatives, before submitting
    uv run python -m evals.run --pred output/          # score an existing output tree, no app run

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
    n_positive = sum(1 for c in cases if c != "negatywne")
    return {
        "commit": commit,
        "dirty": dirty,
        "mode": mode,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_cases": n_positive,
        "n_docs": len(docs),
        "coverage_ok": mode == "full" and n_positive >= 60 and "negatywne" in cases,
        "overall_pass": run_error is None and all(m["pass"] is True for m in metrics.values()),
        "run_error": run_error,
        "metrics": metrics,
        "detail": summary,
        "holdout_51_60": holdout,
        "f1_definition": "evals/metrics.py docstring (organizer formula UNCONFIRMED)",
        "docs": [asdict(d) for d in docs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="dev subset: 6 cases + 3 negatives")
    parser.add_argument("--cmd", default=os.environ.get("ODW_CMD", DEFAULT_CMD))
    parser.add_argument("--pred", type=Path, help="score this output tree (original file names) instead of running")
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()

    if not args.data.is_dir():
        print(f"no data at {args.data}; run: make data", file=sys.stderr)
        return 2
    mode = "quick" if args.quick else "full"
    cases = load_cases(args.data, args.quick)
    n_docs = sum(len(d) for d in cases.values())

    with tempfile.TemporaryDirectory(prefix="odw-eval-") as tmp:
        if args.pred:
            out_dir, run_error, elapsed = args.pred, None, None
            names = {(c, n): Path(n).stem for c, docs in cases.items() for n in docs}
        else:
            in_dir, out_dir = Path(tmp) / "input", Path(tmp) / "output"
            names = stage(cases, args.data, in_dir)
            out_dir.mkdir()
            elapsed, run_error = run_app(args.cmd, in_dir, out_dir)
        docs = [
            score_doc(case, name, out_dir / case / f"{names[(case, name)]}.json", gold)
            for case, items in cases.items()
            for name, gold in items.items()
        ]

    seconds_per_doc = None if elapsed is None else elapsed / max(n_docs, 1)
    results = build_results(docs, mode, seconds_per_doc, cases, run_error)
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(payload + "\n", encoding="utf-8")
    git_dir = subprocess.run(
        ["git", "rev-parse", "--git-dir"], check=False, cwd=ROOT, capture_output=True, text=True
    ).stdout
    if git_dir.strip():
        (ROOT / git_dir.strip() / "eval-latest.json").write_text(payload + "\n", encoding="utf-8")

    if run_error:
        print(f"app failed: {run_error}", file=sys.stderr)
    print(
        f"mode={mode} cases={results['n_cases']} docs={n_docs} commit={results['commit'][:9]} dirty={results['dirty']}"
    )
    for name, m in results["metrics"].items():
        value = "unknown" if m["value"] is None else f"{m['value']:.3f}"
        print(f"  {name:24} {value:>8}  target={m['target']}  pass={m['pass']}")
    print(
        "  per class F1:", {k: None if v is None else round(v, 3) for k, v in results["detail"]["per_class_f1"].items()}
    )
    if holdout := results["holdout_51_60"]:
        print(f"  holdout 51-60 micro F1: {holdout['micro_f1']}")
    print(f"written: {RESULTS.relative_to(ROOT)}")
    return 0 if results["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
