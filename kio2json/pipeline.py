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
from .classify import incomplete_booking_scan, resembles_appeal_heading
from .engines import extract
from .grant_certificates import add_certificate_signers
from .model_pages import AlternateOCR
from .ocr_accounts import AccountEvidence, account_evidence, normalize_receipt
from .ocr_budget import RereadExpired, document_budget, remaining_ms
from .ocr_grant_register import verified_pages
from .ocr_signatures import recover_board_stamp
from .pdf_text import (
    DEFAULT_OCR_ENGINE,
    NoReadableTextError,
    OCRRecognitionError,
    WordBox,
    damaged_text_layer,
    join_pages,
    read_pages,
)
from .receipt_account_crop import recover_account_crops
from .receipt_layout import append_receipt_fields, has_detached_labels, receipt_cell_fields
from .receipt_title import reread_title


def _is_receipt(definition: DocumentClass | None) -> bool:
    return definition is not None and definition.rules_only.extractor is bank_transfer.extract


def _route_receipt(
    pages: list[str], definitions: list[DocumentClass], scanned: bool, cells: dict[str, str] | None = None
) -> tuple[DocumentClass | None, AccountEvidence | None]:
    evidence = account_evidence(pages[0]) if scanned else None
    if evidence is not None and cells:
        # A source cell keeps its owner even if the linear transcript interleaves the columns.
        roles = {}
        prefixed = set(evidence.prefixed_roles)
        for label, role in (("Rachunek nadawcy", "sender"), ("Rachunek odbiorcy", "recipient")):
            if label in cells:
                raw = "".join(cells[label].split())
                digits = raw.removeprefix("PL")
                roles[role] = digits if digits.isdigit() else None
                if raw.startswith("PL"):
                    prefixed.add(role)
                else:
                    prefixed.discard(role)
        evidence = replace(
            evidence, **roles, declared=evidence.declared | roles.keys(), prefixed_roles=frozenset(prefixed)
        )
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
    boxes: list[WordBox],
    retry: bool,
) -> tuple[list[str], DocumentClass | None, AccountEvidence | None]:
    definition, accounts = _route_receipt(pages, definitions, scanned)
    if not pages or (definition is not None and not _is_receipt(definition)):
        return pages, definition, accounts
    original = pages
    fields = {}
    if scanned and (definition is not None or incomplete_booking_scan(pages[0])):
        if boxes:
            pages = recover_account_crops(pdf_path, pages, boxes)
        pages = [normalize_receipt(pages[0]), *pages[1:]]
    if has_detached_labels(pages, ocr=scanned):
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
        if not remaining_ms(1):
            return pages, definition, accounts
        try:
            alternate = read_pages(pdf_path, max_pages=1, force_ocr=True, engine="tesseract", reread=True)
        except RereadExpired:
            return pages, definition, accounts
        if alternate:
            alternate = [normalize_receipt(alternate[0]), *pages[1:]]
            receipt, evidence = _route_receipt(alternate, definitions, True)
            if _is_receipt(receipt) and _compatible_reads(original[0], alternate[0]):
                definition, accounts, pages = receipt, evidence, alternate
    return pages, definition, accounts


def _grant_signers(pdf_path, record, pages, ocr_pages, engine):
    add_certificate_signers(pdf_path, record, join_pages(pages))
    if engine.startswith("tesseract") and len(pages) == 1 and 1 in ocr_pages:
        recover_board_stamp(pdf_path, record, pages[0])


def _document_rules(definition, pdf_path, pages, ocr_pages, boxes, engine, selected, accounts):
    """Build the local candidate, including PDF evidence, before optional model gap filling."""
    rules_first = definition.profile.rules_first
    if definition.extractor is bank_transfer.extract and ocr_pages:
        record = ocr_extract.extract_bank_transfer(pages, ocr_pages, accounts=accounts)
        if boxes and 1 in ocr_pages and (definition.engines == ["python"] or definition.profile.mode == "RL"):
            fields = record["przelew_bankowy"]
            title = reread_title(pdf_path, boxes, fields["tytul"])
            if title is not None:
                fields["tytul"] = title
        return record
    if definition.extractor is appeal.extract and ocr_pages:
        if rules_first:
            words = [box for box in boxes if box.page == 1] if selected == "tesseract-dpi" else []
            return ocr_extract.extract_scanned_appeal(pages, ocr_pages, pdf_path, words)
        return ocr_extract.extract_appeal(pages, ocr_pages)
    if definition.extractor is power_of_attorney.extract:
        if ocr_pages:
            grant_pages = verified_pages(pdf_path, pages, boxes) if rules_first else pages
            record = ocr_extract.extract_power_of_attorney(grant_pages, ocr_pages)
        else:
            record = power_of_attorney.extract(join_pages(pages))
        if definition.profile.mode == "RL":
            _grant_signers(pdf_path, record, pages, ocr_pages, engine)
        return record
    return definition.extractor(join_pages(pages))


@document_budget()
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
    def read(engine: str) -> tuple[list[str], list[int], list[WordBox]]:
        scanned = []
        boxes = []
        pages = read_pages(
            pdf_path,
            force_ocr=force_ocr,
            engine=engine,
            ocr_pages=scanned,
            word_boxes=boxes,
            reread=engine == "rapidocr" and os.getenv("KIO_OCR_ENGINE") == "hybrid",
        )
        return pages, scanned, boxes

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
    pdf_path: Path,
    definitions: list[DocumentClass],
    read: Callable[[str], tuple[list[str], list[int], list[WordBox]]],
) -> tuple[str | None, dict]:
    selected = os.getenv("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    engines = ("tesseract-dpi", "rapidocr") if selected == "hybrid" else (selected,)
    readable = False
    primary_error = None
    for engine in engines:
        try:
            if engine != engines[0] and not remaining_ms(1):
                raise RereadExpired
            primary, ocr_pages, boxes = read(engine)
            pages, definition, accounts = _read_receipt(
                primary,
                pdf_path,
                definitions,
                scanned=1 in ocr_pages,
                boxes=boxes,
                retry=engine == selected == "tesseract-dpi",
            )
        except RereadExpired:
            if primary_error is not None:
                raise primary_error
            break
        except NoReadableTextError as error:
            primary_error = error
            if engine == engines[-1] and not readable:
                raise
            continue
        except OCRRecognitionError as error:
            primary_error = error
            if engine == engines[-1]:
                raise
            continue
        readable = True
        if (
            definition is None
            and 1 not in ocr_pages
            and engine == "tesseract-dpi"
            and primary
            and damaged_text_layer(primary[0])
            and resembles_appeal_heading(primary[0])
            and any(d.enabled and d.extractor is appeal.extract and d.profile.rules_first for d in definitions)
        ):
            repaired_pages, repaired_boxes = [], []
            try:
                repaired = read_pages(
                    pdf_path,
                    engine=engine,
                    repair_image_text=True,
                    reread=True,
                    ocr_pages=repaired_pages,
                    word_boxes=repaired_boxes,
                )
            except RereadExpired:
                repaired = []
            if repaired and 1 in repaired_pages:
                candidate, _ = _route_receipt(repaired, definitions, True)
                if candidate is not None and candidate.extractor is appeal.extract and candidate.profile.rules_first:
                    primary = pages = repaired
                    definition, accounts, ocr_pages, boxes = candidate, None, repaired_pages, repaired_boxes
        rule_class = definition
        alternate = None
        if selected == "tesseract-dpi" and ocr_pages and any(d.enabled and d.profile.dual_ocr for d in definitions):
            alternate = AlternateOCR(pdf_path, ocr_pages)
        if any(
            d.enabled
            and (
                d.profile.routing == "model" or (definition is None and d.profile.routing in {"fallback", "supported"})
            )
            for d in definitions
        ):
            routed = route(primary, definitions, ocr_accounts=accounts, alternate=alternate)
            if definition is not routed:
                pages = primary
                accounts = account_evidence(primary[0]) if 1 in ocr_pages else None
            definition = routed
        if definition is not None:
            check_core_fields = (
                definition is rule_class
                and (
                    not ocr_pages
                    or (
                        definition.profile.routing != "model"
                        and definition.extractor in (appeal.extract, bank_transfer.extract)
                    )
                )
                and definition.profile.mode == "RL"
                and definition.profile.gap_scope == "incomplete"
            )
            if definition.id == "appeal":
                pages = restore_party_columns(pages, boxes)
            scan_boxes = [box for box in boxes if box.page in ocr_pages]
            python_rules = partial(
                _document_rules, definition, pdf_path, pages, ocr_pages, scan_boxes, engine, selected, accounts
            )
            record = extract(
                definition,
                join_pages(pages),
                ocr_python=python_rules,
                alternate=alternate if definition.profile.dual_ocr else None,
                model_text=join_pages(primary) if pages is not primary else None,
                check_core_fields=check_core_fields,
            )
            if definition.extractor is power_of_attorney.extract and not definition.profile.keyed:
                _grant_signers(pdf_path, record, pages, ocr_pages, engine)
            return definition.id, record
        if not ocr_pages:
            break
    return None, {}
