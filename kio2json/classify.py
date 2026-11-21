"""Classify by the document's own heading and transaction evidence."""

import re

from .bank_transfer import AccountEvidence, account_evidence, booking_form, transaction_values
from .receipt_layout import booking_heading

UNRELATED_HEADING = re.compile(
    r"^(?:wyrok|postanowienie|w imieniu rzeczypospolitej polskiej|faktura|wyciąg (?:bankowy|z rachunku)|wezwanie|prośba|wniosek|"
    r"prosimy o|proszę o|instrukcja|zamówienie|oferta handlowa)\b",
    re.IGNORECASE,
)
CONFIRMATION = (
    r"(?:potwierdzenie|dowód)\s+(?:(?:wykonania|realizacji)\s+)?(?:polecenia\s+)?"
    r"(?:przelewu|transakcji|operacji bankowej)\b"
)
CONFIRMATION_HEADING = re.compile(
    rf"^(?:dotyczy:\s*|(?-i:[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ &.-]+)\s+)?{CONFIRMATION}", re.IGNORECASE
)
EXECUTED = re.compile(
    r"^(?:status[\s.:]*)?(?:przelew\s+)?(?:zrealizowan[yaoe]|wykonan[yaoe]|zaksięgowan[yaoe])\b", re.IGNORECASE
)
STATUS = re.compile(r"^(?:status|stan)[\s.:]+(\S.*)$", re.IGNORECASE)


def classify(pages: list[str]) -> str | None:
    label, _ = classify_with_evidence(pages)
    return label


def classify_with_evidence(pages: list[str]) -> tuple[str | None, AccountEvidence | None]:
    if not pages:
        return None, None
    head = "\n".join(pages[:2])
    transfer_heading = False
    for line in head.splitlines():
        line = line.strip()
        heading = re.sub(r"\s", "", line).upper()
        if UNRELATED_HEADING.match(line):
            return None, None
        if heading == "ODWOŁANIE":
            return ("appeal" if "odwołując" in head.casefold() else None), None
        if re.fullmatch(r"PEŁNOMOCNICTWO(?:PROCESOWE|SZCZEGÓLNE)?(?:NR[.:]?[0-9][A-Z0-9./-]*)?", heading):
            return "power_of_attorney", None
        if CONFIRMATION_HEADING.match(line) or booking_heading(line):
            transfer_heading = True
            break

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    statuses = [m[1] for line in lines if (m := STATUS.match(line))]
    if any(not EXECUTED.match(status) for status in statuses):
        return None, None
    if not transfer_heading and not any(EXECUTED.match(line) for line in lines):
        return None, None
    amount, day = transaction_values(first)
    if amount is None and day is None:
        return None, None
    accounts = account_evidence(first)
    if transfer_heading and booking_form(first):
        roles = accounts.sender or accounts.recipient
        pair = accounts.distinct_numbers == 2 or accounts.masked_pair
        return ("bank_transfer", accounts) if amount is not None and day and roles and pair else (None, None)
    if "przelew" not in first.casefold():
        return None, None
    if accounts.distinct_numbers < 2 and not (
        transfer_heading and accounts.distinct_numbers == 1 and amount is not None and day and accounts.masked_pair
    ):
        return None, None
    return "bank_transfer", accounts
