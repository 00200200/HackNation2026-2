"""Run the jury CLI on newly invented, case-linked PDFs and report matched native/scan scores."""

import argparse
import json
import os
import random
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from evals.case_dataset import SEED, generate, write_json
from evals.metrics import NEGATIVE, Counts, load_prediction, score_doc, summarise
from evals.run import DEFAULT_CMD, ROOT, git_state, run_app


def interval(docs):
    """Percentile interval for pooled UZP F1, resampling whole cases including siblings."""
    totals = defaultdict(Counts)
    for doc, _ in docs:
        totals[doc.case].add(doc.counts)
    if len(totals) < 2:
        return None
    rng = random.Random(1829)
    cases = list(totals.values())
    samples = []
    for _ in range(1000):
        total = Counts()
        for case in rng.choices(cases, k=len(cases)):
            total.add(case)
        if total.f1 is not None:
            samples.append(total.f1)
    samples.sort()
    return [round(samples[int((len(samples) - 1) * p)], 5) for p in (0.025, 0.975)] if samples else None


def scores(docs):
    uzp, strict = Counts(), Counts()
    for doc, _ in docs:
        uzp.add(doc.counts)
        strict.add(doc.counts_strict)
    return {
        "cases": len({doc.case for doc, _ in docs}),
        "docs": len(docs),
        "uzp_f1": uzp.f1,
        "strict_f1": strict.f1,
        "uzp_ci95": interval(docs),
        "counts": asdict(uzp),
        "exact": sum(exact for _, exact in docs),
        "routed": sum(doc.gold_class == doc.pred_class for doc, _ in docs),
        "rejected": sum(doc.gold_class == NEGATIVE and doc.empty_output for doc, _ in docs),
        "negatives": sum(doc.gold_class == NEGATIVE for doc, _ in docs),
    }


def exact_json(actual, expected):
    """Structural equality with JSON number semantics and distinct booleans."""
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(exact_json(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(exact_json(left, right) for left, right in zip(actual, expected))
        )
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    return actual == expected


def score(root, manifest, predictions):
    groups = defaultdict(lambda: defaultdict(list))
    roles = defaultdict(lambda: defaultdict(Counts))
    all_docs = []
    for item in manifest["documents"]:
        gold = json.loads((root / item["gold"]).read_text(encoding="utf-8"))
        for view in ("native", "scan"):
            pdf = item[view]
            path = predictions / Path(pdf).with_suffix(".json")
            doc = score_doc(item["case"], pdf, path, gold)
            pred, empty_output = load_prediction(path)
            exact = exact_json(pred, gold) if gold else empty_output
            entry = (doc, exact)
            all_docs.append(entry)
            settings = item["rendering"]
            rendering = "native" if view == "native" else f"{settings['codec']}-{settings['dpi']}dpi"
            family = item["family"]
            for dimension, group in (
                ("class", doc.gold_class),
                ("family", family),
                ("rendering", rendering),
                ("view", view),
                ("split", item["split"]),
                ("family_and_view", f"{family}/{view}"),
            ):
                groups[dimension][group].append(entry)
            for field, counts in doc.by_field.items():
                roles[family][field].add(counts)
    report = {"overall": scores(all_docs), "missing_or_invalid": sum(bool(doc.errors) for doc, _ in all_docs)}
    jury = summarise([doc for doc, _ in all_docs])
    report["routing_aware_per_class_f1"] = jury["per_class_f1"]
    report["macro_f1_classes"] = jury["macro_f1_classes"]
    for dim, parts in groups.items():
        report["per_" + dim] = {k: scores(v) for k, v in sorted(parts.items())}
    report["per_family_role"] = {
        family: {role: {**asdict(counts), "uzp_f1": counts.f1} for role, counts in sorted(fields.items())}
        for family, fields in sorted(roles.items())
    }
    report["weakest_positive_families"] = sorted(
        (family for family, stats in report["per_family"].items() if not stats["negatives"]),
        key=lambda family: report["per_family"][family]["uzp_f1"],
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=int, default=26, help="case prefix before split selection (13 covers every family)"
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--split", choices=("all", "development", "reserved"), default="all")
    parser.add_argument("--generate-to", type=Path, help="only generate the dataset, in a new directory")
    parser.add_argument("--out", type=Path, default=ROOT / ".cache/case-benchmark.json")
    parser.add_argument("--cmd", default=DEFAULT_CMD + " --jobs 2", help="extractor command with {input} and {output}")
    args = parser.parse_args(argv)
    if args.cases < 1:
        parser.error("--cases must be positive")
    with tempfile.TemporaryDirectory(prefix="hn-cases-") as tmp:
        root = args.generate_to or Path(tmp) / "dataset"
        try:
            manifest = generate(root, args.cases, args.seed, args.split)
        except (ValueError, FileExistsError) as exc:
            parser.error(str(exc))
        print(f"Generated {manifest['cases']} cases, SHA-256 {manifest['dataset_sha256']}", flush=True)
        if args.generate_to:
            return 0
        output = Path(tmp) / "predictions"
        output.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith("KIO_")}
        env.update(KIO_LLM_BASE_URL="", KIO_LLM_MODEL="", KIO_LLM_API_KEY="")
        elapsed, error = run_app(args.cmd, root / "input", output, env=env)
        if error:
            parser.exit(2, f"case extraction failed: {error}\n")
        report = score(root, manifest, output)
        commit, dirty = git_state()
        report.update(
            commit=commit,
            dirty=dirty,
            seed=args.seed,
            case_prefix=args.cases,
            split=args.split,
            dataset_sha256=manifest["dataset_sha256"],
            extraction_seconds=round(elapsed, 2),
        )
        write_json(args.out, report)
    result = report["overall"]
    print(
        f"{result['docs']} PDFs, UZP {result['uzp_f1']:.4f}, strict {result['strict_f1']:.4f}, "
        f"exact {result['exact']}. Results in {args.out}"
    )
    return int(bool(report["missing_or_invalid"]))


if __name__ == "__main__":
    sys.exit(main())
