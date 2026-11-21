"""PDF -> (document class, canonical JSON)."""

import os
from functools import partial
from pathlib import Path

from . import appeal, bank_transfer, ocr_extract, power_of_attorney
from .appeal_layout import restore_party_columns
from .class_config import DocumentClass, load_classes, route
from .engines import extract
from .ocr_accounts import account_evidence
from .pdf_text import DEFAULT_OCR_ENGINE, NoReadableTextError, OCRRecognitionError, join_pages, read_pages


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
        except NoReadableTextError:
            if engine == engines[-1] and not readable:
                raise
            continue
        except OCRRecognitionError:
            if engine == engines[-1]:
                raise
            continue
        readable = True
        accounts = account_evidence(pages[0]) if 1 in ocr_pages else None
        definition = route(pages, definitions, ocr_accounts=accounts)
        if definition is not None:
            if definition.id == "appeal":
                pages = restore_party_columns(pdf_path, pages, force_ocr, engine=engine)
            ocr_python = None
            if ocr_pages:
                if definition.extractor is bank_transfer.extract:
                    ocr_python = partial(ocr_extract.extract_bank_transfer, pages, ocr_pages, accounts=accounts)
                elif definition.extractor is power_of_attorney.extract:
                    ocr_python = partial(ocr_extract.extract_power_of_attorney, pages, ocr_pages)
                elif definition.extractor is appeal.extract:
                    ocr_python = partial(ocr_extract.extract_appeal, pages, ocr_pages)
            return definition.id, extract(definition, join_pages(pages), ocr_python=ocr_python)
        if not ocr_pages:
            break  # A second engine would read the same native text.
    return None, {}
