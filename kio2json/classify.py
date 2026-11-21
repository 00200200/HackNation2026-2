"""Classify by the document's own heading and transaction evidence."""

import re

from rapidfuzz.distance import Levenshtein
from stdnum import iban

from . import bank_transfer, power_of_attorney
from .appeal_charges import FILING
from .ocr_accounts import AccountEvidence
from .receipt_layout import booking_heading

UNRELATED_HEADING = re.compile(
    r"^(?:wyrok|postanowienie|w imieniu rzeczypospolitej polskiej|faktura|wyciąg (?:bankowy|z rachunku)|wezwanie|prośba|wniosek|"
    r"prosimy o|proszę o|instrukcja|zamówienie|oferta handlowa)\b",
    re.IGNORECASE,
)
CONFIRMATION = (
    r"(?:potwierdzenie|dowód|zaświadczenie)\s+(?:(?:o\s+)?(?:wykonaniu|wykonania|realizacji|zaksięgowania)\s+)?(?:polecenia\s+)?"
    r"(?:przelewu|transakcji|operacji(?: bankowej)?)\b"
)
CONFIRMATION_HEADING = re.compile(
    rf"^(?:dotyczy:\s*|(?-i:[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ &.-]+)\s+)?{CONFIRMATION}", re.IGNORECASE
)
EXECUTED = re.compile(
    r"^(?:status[\s.:]*)?(?:przelew\s+)?(?:zrealizowan[yaoe]|wykonan[yaoe]|zaksięgowan[yaoe])\b", re.IGNORECASE
)
BANK_FIELDS = re.compile(
    r"\b(?:kwot[ayęą]|wartość|(?:nr|numer|identyfikator) (?:transakcji|operacji)|"
    r"data (?:operacji|księgowania|transakcji|obciążenia)|rachun(?:ek|ku)|IBAN|nadawc[ay]|odbiorc[ay]|beneficjent\w*)\b",
    re.IGNORECASE,
)


# A "stan" field can also describe a balance or another bank-specific state.
# It vetoes a confirmation only when the value actually describes a pending or failed payment.
NONEXECUTED_STATE = re.compile(
    r"^(?:przelew\s+)?(?:oczekuj|odrzucon|anulowan|wstrzyman|zaplanowan|"
    r"nie\s*(?:wykon|opłac|zrealiz|zaksięgow|zatwierdz|rozlicz)|w (?:realizacji|toku)|do (?:realizacji|akceptacji))",
    re.IGNORECASE,
)


def _nonexecuted(lines: list[str]) -> bool:
    for line in lines:
        state = bank_transfer.STATUS.match(line)
        if state is None:
            continue
        if line.casefold().startswith("stan"):
            if NONEXECUTED_STATE.match(state["value"]):
                return True
        elif not EXECUTED.match(state["value"]):
            return True
    return False


def incomplete_booking_scan(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines()]
    if _nonexecuted(lines) or any(UNRELATED_HEADING.match(line) for line in lines):
        return False
    confirmation = any(CONFIRMATION_HEADING.match(line) or booking_heading(line, ocr=True) for line in lines)
    return bool((confirmation or bank_transfer.executed_letter(text)) and BANK_FIELDS.search(text))


def classify(pages: list[str], *, ocr_accounts: AccountEvidence | None = None) -> str | None:
    if not pages:
        return None
    head = "\n".join(pages[:2])
    scan_filing = ocr_accounts is not None and FILING.search(pages[0])
    transfer_heading = False
    register_heading = False
    for index, page in enumerate(pages[:2]):
        for row in page.splitlines():
            line = row.strip()
            heading = re.sub(r"\s", "", line).upper()
            if UNRELATED_HEADING.match(line):
                return None
            if re.match(r"^(?:rejestr|wykaz|spis|ewidencja)\b", line, re.IGNORECASE):
                register_heading = True
            if index == 0 and scan_filing:
                # Flecks at the edge of a scanned title can appear as bullets or quotes.
                if heading.strip("*•|.,„”'—–-") == "ODWOŁANIE":
                    return "appeal"
                if (
                    not register_heading
                    and Levenshtein.distance(heading, "ODWOŁANIE", score_cutoff=1) == 1
                    and re.search(r"(?im)^odwo[łl]uj[ąa]cy\s*:", page)
                    and re.search(r"(?im)^zamawiaj[ąa]cy\s*:", page)
                    and re.search(r"krajowej izby odwoławczej", page, re.IGNORECASE)
                ):
                    return "appeal"
            if Levenshtein.distance(heading, "ODWOŁANIE", score_cutoff=1) <= 1:
                party = re.search(r"odwo[łl]uj[ąa]c", head, re.IGNORECASE)
                labelled_parties = re.search(r"(?im)^(?:wykonawca|odwo[łl]uj[ąa]cy)\s*[:(]", head) and re.search(
                    r"(?im)^zamawiaj[ąa]cy\s*[:(]", head
                )
                # A grammatical word one edit away can be a register heading.
                clear_heading = heading.translate(str.maketrans({"0": "O", "L": "Ł"})) == "ODWOŁANIE"
                if clear_heading and (labelled_parties or FILING.search(head) or (heading == "ODWOŁANIE" and party)):
                    return "appeal"
                # With an ambiguous heading, require party fields and the filer's own declaration.
                if (
                    not register_heading
                    and labelled_parties
                    and re.search(r"(?im)^\s*(?:wnoszę|wnosimy|składam|składamy)\s+(?:niniejsze\s+)?odwołanie\b", head)
                ):
                    return "appeal"
            if re.fullmatch(r"PEŁNOMOCNICTWO(?:PROCESOWE|SZCZEGÓLNE)?(?:NR[.:]?[0-9][A-Z0-9./-]*)?", heading):
                return "power_of_attorney"
            if CONFIRMATION_HEADING.match(line) or booking_heading(line, ocr=index == 0 and ocr_accounts is not None):
                transfer_heading = True
                break
        if transfer_heading:
            break
    if not transfer_heading and power_of_attorney.has_notarial_grant(head):
        return "power_of_attorney"

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    if _nonexecuted(lines) or bank_transfer.payment_denied(first):
        return None
    letter = bank_transfer.executed_letter(first)
    if not (transfer_heading or letter or any(EXECUTED.match(line) for line in lines)):
        return None
    amount, day = bank_transfer.transaction_values(first)
    if amount is None and day is None:
        return None

    if ocr_accounts is None:
        sender, recipient = bank_transfer._accounts(first)
    else:
        sender, recipient = ocr_accounts.sender, ocr_accounts.recipient
    bound_pair = bool(sender and recipient and sender != recipient)
    # Classic confirmations sometimes give an unlabelled pair. Preserve their routing
    # while keeping explicit commission/refund/archive accounts out of that pair.
    payment_fields = bank_transfer.ANCILLARY_ACCOUNT.sub("", first)
    candidates = {"".join(number[1].split()) for number in bank_transfer.ACCOUNT_RE.finditer(payment_fields)}
    known_party = (sender or recipient) and len(
        {"".join(number[1].split()) for number in bank_transfer.ACCOUNT_RE.finditer(first)}
    ) >= 2
    if (
        (bound_pair or known_party or len(candidates) >= 2)
        and "przelew" in first.casefold()
        and (transfer_heading or any(EXECUTED.match(line) for line in lines))
    ):
        return "bank_transfer"
    if amount is None or day is None:
        return None
    if bound_pair:
        return "bank_transfer"
    if transfer_heading:
        if ocr_accounts is not None and ocr_accounts.masked_pair:
            return "bank_transfer"
        visible = sender or recipient
        if (
            bool(sender) != bool(recipient)
            and visible
            and iban.is_valid("PL" + visible)
            and bank_transfer.partial_account_mask(first, "recipient" if sender else "sender")
        ):
            return "bank_transfer"
    return None
