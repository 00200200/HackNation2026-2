"""PDF -> (document class, canonical JSON)."""

import os
import sys
from collections.abc import Callable
from dataclasses import replace
from functools import cache, partial
from pathlib import Path

from . import appeal, bank_transfer, ocr_extract, power_of_attorney
from .appeal_layout import restore_party_columns
from .class_config import DocumentClass, load_classes, route
from .classify import incomplete_booking_scan
from .engines import extract
from .model_pages import AlternateOCR
from .ocr_accounts import AccountEvidence, account_evidence, normalize_receipt
from .pdf_text import DEFAULT_OCR_ENGINE, NoReadableTextError, OCRRecognitionError, join_pages, read_pages
from .receipt_layout import append_receipt_fields, has_detached_labels, receipt_cell_fields


def _is_receipt(definition: DocumentClass | None) -> bool:
    return definition is not None and definition.rules_only.extractor is bank_transfer.extract


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
    return route(pages, definitions, ocr_accounts=evidence, rules_only=True), evidence


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
    if not pages or (definition is not None and not _is_receipt(definition)):
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
        if _is_receipt(candidate):
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
            if _is_receipt(receipt) and _compatible_reads(original[0], alternate[0]):
                definition, accounts, pages = receipt, evidence, alternate
    return pages, definition, accounts


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
        return _process(pdf_path, definitions, read, force_ocr)
    except Exception:  # The PDF, OCR and model libraries raise unrelated per-document errors.
        if not any(d.enabled and d.profile.keyed for d in definitions):
            raise
    result = None, {}
    message = "Could not read document. Returning empty output."
    if read.cache_info().currsize:
        try:
            result = _process(pdf_path, [d.rules_only for d in definitions if d.profile.keyed], read, force_ocr)
            message = "Used rules after document processing failed."
        except Exception:  # noqa: BLE001 - a failed per-document rule retry must yield an empty output
            message = "Document processing and rule recovery failed. Returning empty output."
    print(f"{str(pdf_path)!r}: {message}", file=sys.stderr)
    if on_recovery:
        on_recovery(message)
    return result


def _process(
    pdf_path: Path,
    definitions: list[DocumentClass],
    read: Callable[[str], tuple[list[str], list[int]]],
    force_ocr: bool,
) -> tuple[str | None, dict]:
    selected = os.getenv("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    engines = ("tesseract-dpi", "rapidocr") if selected == "hybrid" else (selected,)
    readable = False
    for engine in engines:
        try:
            primary, ocr_pages = read(engine)
            pages, definition, accounts = _read_receipt(
                primary,
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
        alternate = None
        if selected == "tesseract-dpi" and ocr_pages and any(d.enabled and d.profile.dual_ocr for d in definitions):
            alternate = AlternateOCR(pdf_path, ocr_pages)
        if any(
            d.enabled and (d.profile.routing == "model" or (definition is None and d.profile.routing == "fallback"))
            for d in definitions
        ):
            routed = route(primary, definitions, ocr_accounts=accounts, alternate=alternate)
            if definition is not routed:
                pages = primary
                accounts = account_evidence(primary[0]) if 1 in ocr_pages else None
            definition = routed
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
            return definition.id, extract(
                definition,
                join_pages(pages),
                ocr_python=ocr_python,
                alternate=alternate if definition.profile.dual_ocr else None,
                model_text=join_pages(primary) if pages is not primary else None,
            )
        if not ocr_pages:
            break
    return None, {}
