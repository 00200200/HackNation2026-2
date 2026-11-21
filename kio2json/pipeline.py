"""PDF -> (document class, canonical JSON)."""

from pathlib import Path

from . import appeal, bank_transfer, power_of_attorney
from .classify import classify
from .pdf_text import join_pages, read_pages

EXTRACTORS = {
    "appeal": appeal.extract,
    "power_of_attorney": power_of_attorney.extract,
    "bank_transfer": bank_transfer.extract,
}


def process_pdf(pdf_path: Path, force_ocr: bool = False) -> tuple[str | None, dict]:
    """Class and JSON for one PDF. Any other document gives (None, {}). Raises on a PDF it cannot read."""
    pages = read_pages(pdf_path, force_ocr=force_ocr)
    label = classify(pages)
    if label is None:
        return None, {}
    return label, EXTRACTORS[label](join_pages(pages))
