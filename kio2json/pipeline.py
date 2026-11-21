"""PDF -> (document class, canonical JSON)."""

import os
from pathlib import Path

from .class_config import DocumentClass, load_classes, route_with_evidence
from .engines import extract
from .pdf_text import DEFAULT_OCR_ENGINE, NoReadableTextError, OCRRecognitionError, join_pages, read_pages
from .receipt_layout import has_detached_labels, restore_receipt_rows


def process_pdf(
    pdf_path: Path, force_ocr: bool = False, *, classes: list[DocumentClass] | None = None
) -> tuple[str | None, dict]:
    """Class and JSON for one PDF. Any other document gives (None, {}). Raises on a PDF it cannot read."""
    definitions = classes if classes is not None else load_classes()
    selected = os.getenv("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    engines = ("tesseract-dpi", "rapidocr") if selected == "hybrid" else (selected,)
    readable = False
    for engine in engines:
        ocr_pages = []
        try:
            pages = read_pages(pdf_path, force_ocr=force_ocr, engine=engine, ocr_pages=ocr_pages)
            if has_detached_labels(pages):
                boxes = []
                read_pages(pdf_path, max_pages=1, force_ocr=force_ocr, engine=engine, word_boxes=boxes)
                pages = restore_receipt_rows(pages, boxes)
        except NoReadableTextError:
            if engine == engines[-1] and not readable:
                raise
            continue
        except OCRRecognitionError:
            if engine == engines[-1]:
                raise
            continue
        readable = True
        definition, accounts = route_with_evidence(pages, definitions)
        if definition is not None:
            if accounts is not None and 1 in ocr_pages:
                accounts = accounts.checked_ocr_numbers()
            return definition.id, extract(definition, join_pages(pages), accounts=accounts)
        if not ocr_pages:
            break  # A second engine would read the same native text.
    return None, {}
