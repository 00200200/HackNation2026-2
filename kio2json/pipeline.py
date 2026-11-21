"""PDF -> (document class, canonical JSON)."""

from pathlib import Path

from .class_config import DocumentClass, load_classes, route
from .engines import extract
from .pdf_text import join_pages, read_pages
from .receipt_layout import has_detached_labels, restore_receipt_rows


def process_pdf(
    pdf_path: Path, force_ocr: bool = False, *, classes: list[DocumentClass] | None = None
) -> tuple[str | None, dict]:
    """Class and JSON for one PDF. Any other document gives (None, {}). Raises on a PDF it cannot read."""
    pages = read_pages(pdf_path, force_ocr=force_ocr)
    if has_detached_labels(pages):
        boxes = []
        read_pages(pdf_path, max_pages=1, force_ocr=force_ocr, word_boxes=boxes)
        pages = restore_receipt_rows(pages, boxes)
    definition = route(pages, classes if classes is not None else load_classes())
    if definition is None:
        return None, {}
    return definition.id, extract(definition, join_pages(pages))
