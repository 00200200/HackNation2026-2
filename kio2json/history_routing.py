"""Recognize a single booked transfer printed in an account ledger."""

import re

from .accounts import account_matches
from .bank_transfer import CURRENCY, MONEY, WHOLE_AMOUNT
from .common import RECEIPT_DATE_RE

LEDGER = re.compile(
    r"\b(?:histori[aię] (?:operacji|rachunku|transakcji|obrotów)|"
    r"wyciąg (?:bankowy|z (?:konta|rachunku)|nr)|(?:zestawienie|lista) (?:zaksięgowanych )?(?:operacji|transakcji))\b"
)
DAY_LABEL = re.compile(r"\b(?:dzień|data) (operacji|transakcji|waluty|(?:za)?księgowania|zapisu|obciążenia)\b")
BOOKING_DAY = re.compile(r"\b(?:dzień|data) (?:waluty|(?:za)?księgowania|zapisu|obciążenia)\b")
METADATA = re.compile(r"^(?:(?:data|dzień) (?:wydruku|sporządzenia|wygenerowania)|okres (?:wyciągu|od)|saldo\b)")
SELECTED = re.compile(
    r"^(?:\[x\]|☑|(?:szczegóły )?(?:wybran[ayejgo]*|zaznaczon[ayejgo]*) (?:operacj\w*|transakcj\w*|pozycj\w*))"
)
UNBOOKED = re.compile(
    r"\b(?:planowan\w*|przewidywan\w*|oczekuj\w*|odrzucon\w*|anulowan\w*|"
    r"do (?:wykonania|realizacji|autoryzacji)|nie ?(?:zaksięgow|wykon|zrealiz)\w*)\b"
)
OWNER = re.compile(r"\b(?:posiadacz\w*|właściciel\w*|nadawc[ay]|z (?:rachunku|konta)|rachunek własny)\b")
COUNTERPARTY = re.compile(r"\b(?:kontrahent\w*|odbiorc[ay]|beneficjent\w*|na (?:rachunek|konto))\b")
DEBIT = re.compile(
    rf"\b(?:wn|winien|obciążeni[ae]|wychodząc\w*)\b|(?<!\d)[−-][ \t]*(?:{MONEY}|{WHOLE_AMOUNT}[ \t]*{CURRENCY}\b)",
    re.IGNORECASE,
)
CREDIT = re.compile(r"\b(?:ma|uznani[ae]|zwrot\w*)\b")
FEE = re.compile(r"\b(?:wpis|opłat\w*|wadium)\b")
VALUE = re.compile(rf"{MONEY}|\b{WHOLE_AMOUNT}[ \t]*{CURRENCY}\b|\b{CURRENCY}[ \t]+{WHOLE_AMOUNT}\b", re.IGNORECASE)
CURRENCY_UNIT = re.compile(rf"\b{CURRENCY}\b", re.IGNORECASE)


def _ledger_heading(heading: str) -> bool:
    if LEDGER.search(heading):
        return True
    # A title may be absent when the exporter prints only bank date fields
    # or a table with the account heading and date, description and amount columns.
    if BOOKING_DAY.search(heading) and (
        re.search(r"\bdata (?:operacji|transakcji)\b", heading)
        or (FEE.search(heading) and any(account_matches(heading)))
    ):
        return True
    account = re.search(r"\b(?:rachun(?:ek|ku)|kont[oa]|bank\w*)\b", heading)
    return bool(
        account
        and any(
            re.search(r"\b(?:data|dzień)\b", line)
            and re.search(r"\b(?:tytuł|treść|opis|kontrahent)\b", line)
            and re.search(r"\b(?:kwota|wartość|obciążenie)\b", line)
            for line in heading.splitlines()
        )
    )


def _one_entry(lines: list[str]) -> bool:
    amounts = 0
    date_roles = set()
    for index, line in enumerate(lines):
        prior = lines[index - 1] if index else ""
        dates = RECEIPT_DATE_RE.findall(line)
        remainder = RECEIPT_DATE_RE.sub("", line)
        # A bank may give the same posting an operation day and a value day, or
        # put both dates in adjacent cells. A second row under one label competes.
        if dates and not re.search(r"\bgodz\.", line):
            role = DAY_LABEL.search(line) or DAY_LABEL.fullmatch(prior.rstrip(": "))
            label = role[1] if role else None
            if label in date_roles:
                return False
            date_roles.add(label)
        amounts += sum(1 for _ in VALUE.finditer(remainder))
    return amounts == 1 and bool(date_roles)


def settled_history(pages: list[str]) -> bool:
    """Accept a dated ledger debit or transfer between identified account roles."""
    lines = [line.strip().casefold() for page in pages for line in page.splitlines() if line.strip()]
    heading = "\n".join(lines[:8])
    if not _ledger_heading(heading):
        return False
    marked = [index for index, line in enumerate(lines) if SELECTED.match(line)]
    if len(marked) > 1:
        return False
    entries = lines
    if marked:
        start = marked[0]
        # A checked table row owns only its cells. A separate selection caption
        # introduces a detail block, which must itself contain only one posting.
        entries = [lines[start]] if RECEIPT_DATE_RE.search(lines[start]) else lines[start:]
    # Summary values sometimes appear on their own line below the caption.
    entries = [
        line
        for index, line in enumerate(entries)
        if not METADATA.match(line)
        and not (
            index
            and METADATA.match(entries[index - 1])
            and (RECEIPT_DATE_RE.fullmatch(line) or VALUE.fullmatch(CURRENCY_UNIT.sub("", line).strip()))
        )
    ]
    if not _one_entry(entries):
        return False
    record = "\n".join(entries)
    if UNBOOKED.search(record):
        return False
    # A selection inherits the units and direction of ledger columns, but not
    # amounts, remittances or debit markers printed on other transaction rows.
    captions = [
        line
        for line in lines[:8]
        if not METADATA.match(line) and not RECEIPT_DATE_RE.search(line) and not VALUE.search(line)
    ]
    currency = CURRENCY_UNIT.search(record) or any(CURRENCY_UNIT.search(line) for line in captions)
    # A caption listing both debit and credit cannot establish the populated side.
    debit = any(DEBIT.search(line) and not CREDIT.search(line) for line in entries + captions)
    parties = OWNER.search(record) and COUNTERPARTY.search(record)
    transfer = re.search(r"\bprzelew\w*\b", record)
    fee = FEE.search(record) and not CREDIT.search(record)
    if LEDGER.search(heading) and not marked:
        # On a full statement a generic detail card below the header can be
        # an enclosure. Require a dated ledger row or a procedure-fee posting.
        if re.search(
            r"\b(?:szczegóły|potwierdzenie|zaświadczenie o wykonaniu) (?:transakcji|operacji|przelewu)\b", heading
        ):
            return False
        dated_row = any(
            RECEIPT_DATE_RE.search(line) and VALUE.search(RECEIPT_DATE_RE.sub("", line)) for line in entries
        )
        fee_for_case = fee and re.search(r"\b(?:odwołan|pełnomocnict|postępowan|spraw|przetarg|kio\b)\w*", record)
        if not (dated_row or fee_for_case):
            return False
    return bool(currency and (transfer or fee) and (debit or parties))
