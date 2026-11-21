"""Batch CLI: python -m kio2json [--input DIR] [--output DIR]   (defaults: ./input, ./output)

Writes one JSON per PDF at the same relative path and file stem. A document outside the three
known classes gets an empty file. A PDF that cannot be processed also gets an empty file, is
reported on stderr, and makes the run exit with status 1 after the remaining files are done.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .class_config import load_classes
from .endpoint_error import EndpointError
from .pipeline import process_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", dest="input_dir", default="input", type=Path)
    parser.add_argument("--output", dest="output_dir", default="output", type=Path)
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        parser.error(f"input folder not found: {args.input_dir}")
    try:
        classes = load_classes()
    except (OSError, ValueError) as error:
        print(f"Class configuration: {error}", file=sys.stderr)
        return 1
    if any(c.enabled and "llm" in c.engines for c in classes):
        # The SDK banner names the model; its debug logs include response headers and request URLs.
        os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
        os.environ.pop("OPENAI_LOG", None)
        for name in ("openai", "httpx2", "httpcore2"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)

    pdfs = sorted(p for p in args.input_dir.rglob("*") if p.suffix.lower() == ".pdf")
    failed = 0
    for pdf in pdfs:
        try:
            label, data = process_pdf(pdf, classes=classes)
        except Exception as error:  # noqa: BLE001 - pdfminer raises many unrelated types on damaged files
            detail = str(error) if isinstance(error, EndpointError) else f"{type(error).__name__}: {error}"
            print(f"{pdf}: not processed ({detail})", file=sys.stderr)
            label, data, failed = "failed", {}, failed + 1
        target = args.output_dir / pdf.relative_to(args.input_dir).with_suffix(".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n" if data else "", encoding="utf-8")
        print(f"{label or 'other':18} {target}")
    print(f"{len(pdfs)} PDF -> {args.output_dir}" + (f", {failed} failed" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
