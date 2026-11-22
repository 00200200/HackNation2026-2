"""Recognize an executed payment on a bank's single-operation or single-order screen."""

import re

from .accounts import account_identity, account_matches
from .bank_transfer import MONEY, REFERENCE_RE, TITLE_LABEL_RE, WHOLE_AMOUNT, normalize_account_spacing
from .common import POLISH_FOLD, RECEIPT_DATE

SUBJECT = r"(?:operacj|transakcj|przelew|platnos|zlecen|dyspozycj)\w*"
DETAIL = re.compile(
    rf"\b(?:szczegol\w*|podglad|karta|metryka|informacj\w*|dane|widok|wydruk|zapis)\b.{{0,42}}\b{SUBJECT}\b"
    rf"|\b{SUBJECT}\b.{{0,42}}\b(?:szczegol\w*|podglad|widok)\b"
    r"|^(?:operacja|transakcja|przelew)\s+(?:na rachun\w*|bankow\w*|krajow\w*|wychodzac\w*)\b",
    re.MULTILINE,
)
BANK = re.compile(r"\b(?:[a-z-]*bank|bankowosc\w*|serwis transakcyjny)\b")
UNSETTLED_HEADING = re.compile(
    rf"\b(?:przyjecia|zlozenia)\s+(?:{SUBJECT}|do realizacji)\b|\b{SUBJECT}\s+(?:za)?planowan\w*"
    r"|\bbrak\s+(?:potwierdzenia|poswiadczenia|dowodu|wykonania|realizacji)\b"
)
NON_TRANSFER_TYPE = re.compile(r"\b(?:platnosc karta|transakcja kartowa|wyplata (?:gotowki|z bankomatu))\b")
TYPE = re.compile(rf"\b(?:rodzaj|typ|status|stan|(?:numer|nr|id|identyfikator))\s+{SUBJECT}\b")
PAYER = re.compile(r"\b(?:platnik\w*|nadawc\w*|zleceniodawc\w*|obciaz[ao]n\w*|zrodlow\w*|winien|z rachunku)\b")
PAYEE = re.compile(r"\b(?:odbiorc\w*|beneficjen\w*|kontrahen\w*|uzna(?:n|wan)\w*|docelow\w*|strona ma|na rachunek)\b")
ACCOUNT_LABEL = re.compile(r"\b(?:rachun\w*|kont[oa]|iban)\b")
ACCOUNT_FRAGMENT = re.compile(r"\b\d{2}[ \t-]+\d{4}\b|(?:[Xx*…]{2,}|…)\s*\d{4}\b")
PURPOSE = re.compile(r"\b(?:tytul\w*|opis|tresc|szczegoly platnosci|(?:wpis|oplata|wadium)\b.{0,55}\d)")
AMOUNT = re.compile(
    rf"(?<![\d.,])(?:{MONEY}|{WHOLE_AMOUNT})[ \t]*(?:pln|zl|eur)\b"
    rf"|\b(?:pln|eur)[ \t]*[−-]?[ \t]*(?:{MONEY}|{WHOLE_AMOUNT})(?![\d.,])"
)
STATUS_WORD = r"(?:wykonan|zrealizowan|zaksiegowan|rozliczon|dokonan)[aeyo]"
SETTLED = re.compile(
    rf"^(?:(?:(?:status|stan|wynik)(?:\s+(?:realizacji|{SUBJECT}))?|{SUBJECT})(?:\s+zostal[ao]?)?\s*[:|–—-]?\s*)?"
    rf"{STATUS_WORD}\b(?:[ .!]*$|\s*(?:\||\s{{2}})|\s+(?:na rachunku|przez bank|w dniu|dnia)\b)"
)
DAY = RECEIPT_DATE.translate(POLISH_FOLD)
DATE_NOUN = r"(?:wykonania|(?:za)?ksiegowania|obciazenia|realizacji)"
GAP = r"[\s:|–—-]*"
BOOKING_DATE = re.compile(rf"\b(?:data|dzien){GAP}(?:{DATE_NOUN}{GAP}{DAY}|{DAY}{GAP}{DATE_NOUN})", re.IGNORECASE)
OPERATION_DATE = re.compile(rf"\b(?:data|dzien)\s+(?:operacji|transakcji){GAP}{DAY}", re.IGNORECASE)
ORDER_CONTEXT = re.compile(r"\b(?:zleceni[aeu]|dyspozycj[aei]|poleceni[ae] przelewu|wniosek)\b")
EXPECTED = (
    r"(?:zlecon|zadan|wybran|wskazan|wnioskowan|planowan|zaplanowan|przewidywan|oczekiwan|proponowan)"
    r"\w*(?:[ \t]+przez[ \t]+\w+)?"
)
EXPECTED_BEFORE = re.compile(rf"(?:\b{EXPECTED}[ \t]*|(?:^|\n){EXPECTED}[ \t]*\n[ \t]*)\Z")
EXPECTED_AFTER = re.compile(rf"[ \t(\[,—–-]*(?:data[ \t]+)?{EXPECTED}\b(?![ \t]+(?:data|dzien|termin)\b)")
PADDING = " \t|:.•*—–-»_"


def _one_amount(text: str) -> bool:
    amounts = AMOUNT.findall(text)
    if amounts:
        return len(amounts) == 1
    # Currency and value can be independent cells on a native bank screen.
    return bool(
        re.search(r"\b(?:kwota|wartosc|suma)\b", text)
        and re.search(r"\b(?:pln|eur|zl)\b", text)
        and len(re.findall(MONEY, text)) == 1
    )


def _identified_operation(page: str) -> bool:
    """Only a bank operation's own identifier and a filled remittance corroborate its date."""
    operation_id = any(
        re.search(r"\b(?:operacji|transakcji)\b", page[m.start() : m.start(1)], re.IGNORECASE)
        for m in REFERENCE_RE.finditer(page)
    )
    return operation_id and any(
        (title := TITLE_LABEL_RE.match(row.strip())) and re.search(r"[^\W_]", title[1]) for row in page.splitlines()
    )


def settled_details(pages: list[str]) -> bool:
    """Test the document's transaction evidence without requiring extractable field pairs."""
    if not pages:
        return False
    page = pages[0]
    lines = [line.casefold().translate(POLISH_FOLD).strip(PADDING) for line in page.splitlines() if line.strip()]
    text = "\n".join(lines)
    header = "\n".join(lines[:10])
    detail = DETAIL.search(header)
    bank = BANK.search(header)
    typed = TYPE.search(text)
    if UNSETTLED_HEADING.search(header) or NON_TRANSFER_TYPE.search(header) or not (detail or (bank and typed)):
        return False
    if not _one_amount(text) or any(AMOUNT.search(p.casefold().translate(POLISH_FOLD)) for p in pages[1:]):
        return False
    status = any(SETTLED.search(line) for line in lines)
    payer, payee = PAYER.search(text), PAYEE.search(text)
    # A dated outgoing debit has already occurred. A submitted order can
    # instead print its order date before the payment has been executed.
    outgoing = re.search(r"\b(?:przelew wychodzacy|platnosc wychodzaca|strona winien)\b", text)
    dates = [*BOOKING_DATE.finditer(text)]
    if not ORDER_CONTEXT.search(header) and (outgoing or (detail and payer and payee and _identified_operation(page))):
        dates.extend(OPERATION_DATE.finditer(text))
    booked = any(
        not EXPECTED_BEFORE.search(text[: m.start()]) and not EXPECTED_AFTER.match(text, m.end()) for m in dates
    )
    if not (status or booked):
        return False

    numbers = [
        account_identity("".join(match[1].split())) for match in account_matches(normalize_account_spacing(page))
    ]
    purpose = PURPOSE.search(text)
    if len(set(numbers)) == 2:
        # A bank can print both account values in a separate panel from the labels.
        return bool((payer and payee) or (not payer and not payee and bank and status and (purpose or typed)))
    # OCR may break the account strings. Their opposing printed roles and the
    # remittance still describe the payment without asserting either value.
    return bool(
        len(numbers) < 2
        and bank
        and payer
        and payee
        and purpose
        and len(ACCOUNT_LABEL.findall(text)) >= 2
        and len(ACCOUNT_FRAGMENT.findall(text)) >= 2
    )
