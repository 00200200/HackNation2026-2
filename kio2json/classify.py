"""Classify by the document's own heading and transaction evidence."""

import re

from stdnum import iban

from .bank_transfer import ACCOUNT_RE, BANK_ACCOUNT, booking_form, transaction_values
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

ACCOUNT_LINE = re.compile(r"rachunek (nadawcy|odbiorcy):\s*(.+)", re.IGNORECASE)


def _masked_pair(lines: list[str]) -> bool:
    """One explicitly masked role opposite one checksum-valid, explicitly labelled NRB."""
    matched = [m.groups() for line in lines if (m := ACCOUNT_LINE.fullmatch(line))]
    if len(matched) != 2 or len({role.casefold() for role, _ in matched}) != 2:
        return False
    values = [value for _, value in matched]
    return any(re.fullmatch(r"\*{4,}", value) for value in values) and any(
        (number := ACCOUNT_RE.fullmatch(value)) and iban.is_valid("PL" + re.sub(r"\s", "", number[1]))
        for value in values
    )


def classify(pages: list[str]) -> str | None:
    if not pages:
        return None
    head = "\n".join(pages[:2])
    transfer_heading = False
    for line in head.splitlines():
        line = line.strip()
        heading = re.sub(r"\s", "", line).upper()
        if UNRELATED_HEADING.match(line):
            return None
        if heading == "ODWOŁANIE":
            return "appeal" if "odwołując" in head.casefold() else None
        if re.fullmatch(r"PEŁNOMOCNICTWO(?:PROCESOWE|SZCZEGÓLNE)?(?:NR[.:]?[0-9][A-Z0-9./-]*)?", heading):
            return "power_of_attorney"
        if CONFIRMATION_HEADING.match(line) or booking_heading(line):
            transfer_heading = True
            break

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    statuses = [m[1] for line in lines if (m := STATUS.match(line))]
    if any(not EXECUTED.match(status) for status in statuses):
        return None
    if not transfer_heading and not any(EXECUTED.match(line) for line in lines):
        return None
    accounts = {re.sub(r"\s", "", match[1]) for match in ACCOUNT_RE.finditer(first)}
    if transfer_heading and booking_form(first):
        amount, day = transaction_values(first)
        candidates = {re.sub(r"\s", "", m[1]) for m in BANK_ACCOUNT.finditer(first)}
        if amount is not None and day and len(candidates) == 2 and any(iban.is_valid("PL" + n) for n in candidates):
            return "bank_transfer"
    if "przelew" not in first.casefold():
        return None
    amount, day = transaction_values(first)
    if len(accounts) < 2 and not (
        transfer_heading and len(accounts) == 1 and amount is not None and day and _masked_pair(lines)
    ):
        return None
    return "bank_transfer" if amount is not None or day is not None else None
