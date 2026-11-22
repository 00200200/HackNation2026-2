"""Apply OCR rules only to fields originating on OCR pages."""

import re
from collections.abc import Collection
from itertools import groupby
from pathlib import Path

from . import appeal, bank_transfer, ocr_signatures, power_of_attorney
from .accounts import account_identity
from .appeal_scan_action import apply_action
from .appeal_scan_crops import verify_cover
from .appeal_scan_parties import apply_parties
from .appeal_scan_procurement import apply_procurement
from .grant_declarations import check_ocr_trade_names, complete_represented_company, read_declaration
from .ocr_accounts import AccountEvidence, account_evidence
from .ocr_normalize import MAIL_TOKEN_RE
from .ocr_plausibility import gate_appeal
from .pdf_text import WordBox, iter_page_lines, join_pages
from .personal_names import repair_appointment_initials


def _lines(pages: list[str], ocr_pages: Collection[int]):
    # splitlines() is also used by the base extractors; include its non-LF separators.
    for page, line in iter_page_lines(pages):
        for part in (line + "\n").splitlines():
            yield page in ocr_pages, part


def extract_appeal(pages: list[str], ocr_pages: Collection[int]) -> dict:
    mail_lines = frozenset(
        i for i, (ocr, line) in enumerate(_lines(pages, ocr_pages)) if ocr and MAIL_TOKEN_RE.fullmatch(line.strip())
    )
    return appeal.extract(join_pages(pages), ocr_mail_lines=mail_lines)


def extract_scanned_appeal(pages: list[str], ocr_pages: Collection[int], pdf_path: Path, words: list[WordBox]) -> dict:
    record = extract_appeal(pages, ocr_pages)
    apply_action(record, pages, ocr_pages)
    apply_parties(record, pages, ocr_pages, words)
    apply_procurement(record, pages, ocr_pages)
    if 1 in ocr_pages:
        verify_cover(record, pages[0], words, pdf_path, all_scanned=len(set(ocr_pages)) == len(pages))
    gate_appeal(record, pages, ocr_pages)
    return record


def _account_fields(text: str, ocr: bool, receipt: AccountEvidence | None = None) -> dict[str, str | None]:
    """Keep declared but empty/ambiguous roles distinct from absent roles."""
    if ocr:
        evidence = receipt or account_evidence(text)
        values = {"sender": evidence.sender, "recipient": evidence.recipient}
        return {role: value for role, value in values.items() if value is not None or role in evidence.declared}
    sender, recipient = bank_transfer._accounts(text)
    lower = text.casefold()
    fields = {}
    for role, value, label in (
        ("sender", sender, bank_transfer.SENDER_RE),
        ("recipient", recipient, bank_transfer.RECIPIENT_RE),
    ):
        if value is not None or label.search(lower):
            fields[role] = value
    return fields


def extract_bank_transfer(
    pages: list[str], ocr_pages: Collection[int], *, accounts: AccountEvidence | None = None
) -> dict:
    record = bank_transfer.extract(join_pages(pages))
    if not pages or not ocr_pages:
        return record

    # The routing receipt owns its declared fields, including masks and conflicts.
    # Keep a continuous native receipt together so its base column/role rules
    # still work across pages. OCR routing uses the evidence on page one.
    first_ocr = 1 in ocr_pages
    receipt_end = 1 if first_ocr else min(ocr_pages) - 1
    lines = list(iter_page_lines(pages))
    receipt = "\n".join(line for page, line in lines if page <= receipt_end)
    fields = _account_fields(receipt, first_ocr, accounts)

    supplements = {"sender": set(), "recipient": set()}
    later = ((page in ocr_pages, line) for page, line in lines if page > receipt_end)
    for ocr, section in groupby(later, key=lambda pair: pair[0]):
        for role, value in _account_fields("\n".join(line for _, line in section), ocr).items():
            supplements[role].add(value)
    for role, opposite in (("sender", "recipient"), ("recipient", "sender")):
        candidates = supplements[role]
        if role not in fields and len(candidates) == 1:
            number = next(iter(candidates))
            if (
                number
                and account_identity(number) != account_identity(fields.get(opposite) or "")
                and (
                    opposite in fields
                    or all(account_identity(number) != account_identity(v or "") for v in supplements[opposite])
                )
            ):
                fields[role] = number
    record["przelew_bankowy"].update(z_rachunku=fields.get("sender"), na_rachunek=fields.get("recipient"))
    return record


def extract_power_of_attorney(pages: list[str], ocr_pages: Collection[int]) -> dict:
    pages = [
        power_of_attorney.normalize_registry_labels(
            re.sub(r"(?i)\b(spółka|sp\.)\s+z\s+[0o]\.[0o]\.", r"\1 z o.o.", repair_appointment_initials(page))
        )
        if index in ocr_pages
        else page
        for index, page in enumerate(pages, 1)
    ]
    lines = list(_lines(pages, ocr_pages))
    original = join_pages(pages)
    text = power_of_attorney.operative_grant_text(original)
    if text != original:
        lines = list(zip((ocr for ocr, _ in lines), (text + "\n").splitlines(), strict=True))
    principals, officers = power_of_attorney.grant_parties(text)
    # Drawn signature lines on scans terminate the appointment section just like dots.
    appointment = "\n".join(re.sub(r"_{5,}|[─━—]{4,}", "." * 10, line) if ocr else line for ocr, line in lines)
    attorneys = power_of_attorney._attorneys(appointment)
    signature_text = power_of_attorney.issuer_signature_text(text, principals, power_of_attorney.ISSUANCE.search(text))
    if signature_text != text:
        lines = list(zip((ocr for ocr, _ in lines), (signature_text + "\n").splitlines(), strict=True))
    principal_names = [power_of_attorney.principal_name(p) for p in principals]
    attorney_names = {attorney["imie_nazwisko"] for attorney in attorneys}
    signers = [[] for _ in principals]
    prefix = []
    for ocr, section in groupby(lines, key=lambda pair: pair[0]):
        run = [line for _, line in section]
        first = len(prefix)
        if ocr:
            names = ocr_signatures.signers(run, principal_names, attorney_names, prefix)
        else:
            names = power_of_attorney._signers(
                "\n".join(prefix + run), principal_names, attorney_names, from_line=first
            )
        prefix.extend(run)
        for owner, found in zip(signers, names, strict=True):
            owner.extend(name for name in found if name not in owner)
    record = power_of_attorney.finish_record(signature_text, principals, officers, attorneys, signers)
    if pages and 1 in ocr_pages and not any(power_of_attorney.GRANT.search(page) for page in pages[1:]):
        read_declaration(pages[0], record)
        complete_represented_company(pages[0], record)
        signing_page = power_of_attorney.issuer_signature_text(
            pages[0], principals, power_of_attorney.ISSUANCE.search(pages[0])
        )
        ocr_signatures.confirmed_scan_signer(signing_page, record)
    if ocr_pages:
        check_ocr_trade_names(record, pages, ocr_pages)
    return record
