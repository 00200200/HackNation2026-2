"""PDF -> (document class, canonical JSON)."""

import os
import sys
from collections.abc import Callable
from functools import cache, partial
from pathlib import Path

from . import appeal, bank_transfer, ocr_extract, power_of_attorney
from .class_config import DocumentClass, load_classes, route
from .engines import extract
from .model_pages import AlternateOCR
from .ocr_accounts import account_evidence
from .pdf_text import DEFAULT_OCR_ENGINE, NoReadableTextError, OCRRecognitionError, join_pages, read_pages


def process_pdf(
    pdf_path: Path,
    force_ocr: bool = False,
    *,
    classes: list[DocumentClass] | None = None,
    on_recovery: Callable[[str], None] | None = None,
) -> tuple[str | None, dict]:
    """Return the class and JSON, using local recovery for a failed keyed organizer document."""
    definitions = classes if classes is not None else load_classes()

    @cache
    def read(engine: str) -> tuple[list[str], list[int]]:
        scanned = []
        pages = read_pages(pdf_path, force_ocr=force_ocr, engine=engine, ocr_pages=scanned)
        return pages, scanned

    try:
        return _process(pdf_path, definitions, read)
    except Exception:  # The PDF, OCR and model libraries raise unrelated per-document errors.
        if not any(d.enabled and d.profile.keyed for d in definitions):
            raise
    result = None, {}
    message = "Could not read document. Returning empty output."
    if read.cache_info().currsize:
        try:
            result = _process(pdf_path, [d.rules_only for d in definitions if d.profile.keyed], read)
            message = "Used rules after document processing failed."
        except Exception:  # noqa: BLE001 - a failed per-document rule retry must yield an empty output
            message = "Document processing and rule recovery failed. Returning empty output."
    print(f"{str(pdf_path)!r}: {message}", file=sys.stderr)
    if on_recovery:
        on_recovery(message)
    return result


def _process(
    pdf_path: Path, definitions: list[DocumentClass], read: Callable[[str], tuple[list[str], list[int]]]
) -> tuple[str | None, dict]:
    selected = os.getenv("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    engines = ("tesseract-dpi", "rapidocr") if selected == "hybrid" else (selected,)
    readable = False
    for engine in engines:
        try:
            pages, ocr_pages = read(engine)
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
        alternate = None
        if selected == "tesseract-dpi" and ocr_pages and any(d.enabled and d.profile.dual_ocr for d in definitions):
            alternate = AlternateOCR(pdf_path, ocr_pages)
        definition = route(pages, definitions, ocr_accounts=accounts, alternate=alternate)
        if definition is not None:
            ocr_python = None
            if ocr_pages:
                if definition.extractor is bank_transfer.extract:
                    ocr_python = partial(ocr_extract.extract_bank_transfer, pages, ocr_pages, accounts=accounts)
                elif definition.extractor is power_of_attorney.extract:
                    ocr_python = partial(ocr_extract.extract_power_of_attorney, pages, ocr_pages)
                elif definition.extractor is appeal.extract:
                    ocr_python = partial(ocr_extract.extract_appeal, pages, ocr_pages)
            return definition.id, extract(
                definition,
                join_pages(pages),
                ocr_python=ocr_python,
                alternate=alternate if definition.profile.dual_ocr else None,
            )
        if not ocr_pages:
            break  # A second engine would read the same native text.
    return None, {}
