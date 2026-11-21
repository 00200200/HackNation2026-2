"""Batch CLI: python -m kio2json [--input DIR] [--output DIR]   (defaults: ./input, ./output)

Writes one JSON per PDF at the same relative path and file stem. A document outside the three
known classes gets an empty file. A PDF that cannot be processed also gets an empty file, is
reported on stderr, and makes the run exit with status 1 after the remaining files are done.
"""

import argparse
import sys
from pathlib import Path

import pytesseract

from .batch import configure_logging, read_document
from .class_config import load_classes


def ocr_problem() -> str | None:
    """Why scanned PDFs cannot be read on this machine, or None when OCR is ready."""
    try:
        languages = pytesseract.get_languages()
    except (pytesseract.TesseractNotFoundError, UnicodeDecodeError):
        return "Tesseract not found"
    return None if "pol" in languages else "Tesseract has no Polish language data (pol)"


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
    configure_logging(classes)
    problem = ocr_problem()
    if problem:
        print(f"{problem}: scanned PDFs cannot be read and will get an empty file.", file=sys.stderr)

    pdfs = sorted(p for p in args.input_dir.rglob("*") if p.suffix.lower() == ".pdf")
    failed = 0
    for pdf in pdfs:
        result = read_document(pdf, classes)
        if result.error:
            print(f"{pdf}: not processed ({result.error})", file=sys.stderr)
            failed += 1
        target = args.output_dir / pdf.relative_to(args.input_dir).with_suffix(".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.text, encoding="utf-8")
        label = "failed" if result.error else result.label
        print(f"{label or 'other':18} {target}")
    print(f"{len(pdfs)} PDF -> {args.output_dir}" + (f", {failed} failed" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
