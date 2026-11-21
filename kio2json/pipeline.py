"""PDF -> (document class, canonical JSON)."""

import os
from dataclasses import replace
from functools import partial
from pathlib import Path

from . import appeal, bank_transfer, ocr_extract, power_of_attorney
from .class_config import DocumentClass, load_classes, route
from .classify import incomplete_booking_scan
from .engines import extract
from .ocr_accounts import AccountEvidence, account_evidence, normalize_receipt
from .pdf_text import DEFAULT_OCR_ENGINE, NoReadableTextError, OCRRecognitionError, join_pages, read_pages
from .receipt_layout import append_receipt_fields, has_detached_labels, receipt_cell_fields


def _route_receipt(
    pages: list[str], definitions: list[DocumentClass], scanned: bool, cells: dict[str, str] | None = None
) -> tuple[DocumentClass | None, AccountEvidence | None]:
    evidence = account_evidence(pages[0]) if scanned else None
    if evidence is not None and cells:
        # A source cell keeps its owner even if the linear transcript interleaves the columns.
        roles = {}
        for label, role in (("Rachunek nadawcy", "sender"), ("Rachunek odbiorcy", "recipient")):
            if label in cells:
                raw = "".join(cells[label].split())
                roles[role] = raw if raw.isdigit() else None
        evidence = replace(evidence, **roles, declared=evidence.declared | roles.keys())
    return route(pages, definitions, ocr_accounts=evidence), evidence


def _compatible_reads(first: str, second: str) -> bool:
    # Accept an alternate segmentation only when its independently bound facts agree.
    a, b = (bank_transfer.extract(page)["przelew_bankowy"] for page in (first, second))
    fields = ("data_operacji", "kwota", "numer_transakcji", "z_rachunku", "na_rachunek")
    return all(a[key] is None or b[key] is None or a[key] == b[key] for key in fields)


def _read_receipt(
    pages: list[str],
    pdf_path: Path,
    definitions: list[DocumentClass],
    *,
    scanned: bool,
    force_ocr: bool,
    engine: str,
    retry: bool,
) -> tuple[list[str], DocumentClass | None, AccountEvidence | None]:
    definition, accounts = _route_receipt(pages, definitions, scanned)
    if not pages or (definition is not None and definition.extractor is not bank_transfer.extract):
        return pages, definition, accounts
    original = pages
    fields = {}
    if scanned and (definition is not None or incomplete_booking_scan(pages[0])):
        pages = [normalize_receipt(pages[0]), *pages[1:]]
    if has_detached_labels(pages, ocr=scanned):
        boxes = []
        read_pages(pdf_path, max_pages=1, force_ocr=force_ocr, engine=engine, word_boxes=boxes)
        fields = receipt_cell_fields(boxes, ocr=scanned)
        # Keep the complete title already bound to a native label, including wrapped lines.
        if (
            not scanned
            and definition is not None
            and bank_transfer.extract(pages[0])["przelew_bankowy"]["tytul"] is not None
        ):
            fields.pop("Tytuł", None)
        pages = append_receipt_fields(pages, fields)
    if pages != original:
        candidate, evidence = _route_receipt(pages, definitions, scanned, fields)
        if candidate is not None and candidate.extractor is bank_transfer.extract:
            definition, accounts = candidate, evidence
        elif scanned and definition is not None:
            # Recognition already established a receipt. An ambiguous OCR account loses
            # its value, even when it supplied the second number for initial routing.
            accounts = evidence
        else:
            pages = original
    if definition is None and scanned and retry and incomplete_booking_scan(pages[0]):
        alternate = read_pages(pdf_path, max_pages=1, force_ocr=True, engine="tesseract")
        if alternate:
            alternate = [normalize_receipt(alternate[0]), *pages[1:]]
            receipt, evidence = _route_receipt(alternate, definitions, True)
            if (
                receipt is not None
                and receipt.extractor is bank_transfer.extract
                and _compatible_reads(original[0], alternate[0])
            ):
                definition, accounts, pages = receipt, evidence, alternate
    return pages, definition, accounts


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
            pages, definition, accounts = _read_receipt(
                pages,
                pdf_path,
                definitions,
                scanned=1 in ocr_pages,
                force_ocr=force_ocr,
                engine=engine,
                retry=engine == selected == "tesseract-dpi",
            )
        except NoReadableTextError:
            if engine == engines[-1] and not readable:
                raise
            continue
        except OCRRecognitionError:
            if engine == engines[-1]:
                raise
            continue
        readable = True
        if definition is not None:
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
            break
    return None, {}
