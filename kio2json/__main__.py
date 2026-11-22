"""Batch CLI: python -m kio2json [--input DIR] [--output DIR]   (defaults: ./input, ./output)

Writes one JSON per PDF at the same relative path and file stem. A document outside the three
known classes gets an empty file. --classes adds class TOML files, --enable turns on a class that
its file disables, and --explain DIR writes DIR/<case>/<name>.trace.json with the routing reason and
field sources. The keyed organizer profile retries failed documents with rules and continues with
empty output if recovery fails. Other document errors give exit status 1.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .batch import configure_logging, read_batch, reconcile_cases
from .case_repair import case_repair_enabled
from .class_config import add_class_options, class_sources, parse_classes

DEFAULT_WORKER_CAP = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", dest="input_dir", default="input", type=Path)
    parser.add_argument("--output", dest="output_dir", default="output", type=Path)
    parser.add_argument(
        "--workers",
        "--jobs",
        type=int,
        choices=range(1, 9),
        help=f"PDF processes (default: available CPUs up to {DEFAULT_WORKER_CAP})",
    )
    add_class_options(parser)
    parser.add_argument(
        "--explain",
        type=Path,
        metavar="DIR",
        help="also write DIR/<case>/<name>.trace.json for each PDF (a folder outside --output)",
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        parser.error(f"input folder not found: {args.input_dir}")
    if args.explain:
        if args.explain.resolve().is_relative_to(args.output_dir.resolve()):
            parser.error("--explain needs a folder outside --output, because every JSON there is scored")
        try:
            args.explain.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            parser.error(f"--explain folder cannot be created: {error}")
    try:
        sources = class_sources(extra=args.classes, enable=args.enable)
        classes = parse_classes(sources)
    except (OSError, ValueError) as error:
        print(f"Class configuration: {error}", file=sys.stderr)
        return 1
    configure_logging(classes)

    pdfs = sorted(p for p in args.input_dir.rglob("*") if p.suffix.lower() == ".pdf")
    failed = 0
    workers = args.workers or min(DEFAULT_WORKER_CAP, os.process_cpu_count() or 1)
    explain = args.explain is not None
    results = read_batch(pdfs, sources, workers, explain=explain)
    if case_repair_enabled():
        results = reconcile_cases([pdf.relative_to(args.input_dir) for pdf in pdfs], list(results))
    for pdf, result in zip(pdfs, results, strict=True):
        if result.error:
            print(f"{pdf}: not processed ({result.error})", file=sys.stderr)
            failed += 1
        target = args.output_dir / pdf.relative_to(args.input_dir).with_suffix(".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.text, encoding="utf-8", newline="\n")
        if explain:
            name = pdf.relative_to(args.input_dir)
            trace = {"document": name.as_posix(), "error": result.error} | (result.trace or {})
            evidence = args.explain / name.with_suffix(".trace.json")
            try:
                evidence.parent.mkdir(parents=True, exist_ok=True)
                text = json.dumps(trace, ensure_ascii=False, indent=2) + "\n"
                evidence.write_text(text, encoding="utf-8", newline="\n")
            except OSError as error:
                # Evidence is optional; the jury's JSON for this and later PDFs must still be written.
                print(f"{evidence}: trace not written ({error})", file=sys.stderr)
        label = "failed" if result.error else result.label
        print(f"{label or 'other':18} {target}")
    print(f"{len(pdfs)} PDF -> {args.output_dir}" + (f", {failed} failed" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
