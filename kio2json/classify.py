"""Classify by the document's own heading and transaction evidence."""

import re

from rapidfuzz.distance import Levenshtein

from .appeal_charges import FILING
from .bank_transfer import ACCOUNT_RE, transaction_values
from .ocr_accounts import AccountEvidence

UNRELATED_HEADING = re.compile(
    r"^(?:wyrok|postanowienie|w imieniu rzeczypospolitej polskiej|faktura|wezwanie|prośba|wniosek|"
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
EXECUTED = re.compile(r"^(?:status[\s.:]*)?(?:przelew\s+)?(?:zrealizowan[yo]|wykonan[yo])\b", re.IGNORECASE)
STATUS = re.compile(r"^status[\s.:]+(\S.*)$", re.IGNORECASE)


def classify(pages: list[str], *, ocr_accounts: AccountEvidence | None = None) -> str | None:
    if not pages:
        return None
    head = "\n".join(pages[:2])
    transfer_heading = False
    register_heading = False
    for line in head.splitlines():
        line = line.strip()
        heading = re.sub(r"\s", "", line).upper()
        if UNRELATED_HEADING.match(line):
            return None
        if re.match(r"^(?:rejestr|wykaz|spis|ewidencja)\b", line, re.IGNORECASE):
            register_heading = True
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
        if heading in {"PEŁNOMOCNICTWO", "PEŁNOMOCNICTWOPROCESOWE", "PEŁNOMOCNICTWOSZCZEGÓLNE"}:
            return "power_of_attorney"
        if CONFIRMATION_HEADING.match(line):
            transfer_heading = True
            break

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    statuses = [m[1] for line in lines if (m := STATUS.match(line))]
    if any(not EXECUTED.match(status) for status in statuses):
        return None
    if not transfer_heading and not any(EXECUTED.match(line) for line in lines):
        return None
    if ocr_accounts is None:
        account_count = len({re.sub(r"\s", "", match[1]) for match in ACCOUNT_RE.finditer(first)})
    else:
        account_count = ocr_accounts.distinct_numbers
    masked = ocr_accounts is not None and account_count == 1 and ocr_accounts.masked_pair and transfer_heading
    if (account_count < 2 and not masked) or "przelew" not in first.casefold():
        return None
    amount, day = transaction_values(first)
    if masked and (amount is None or day is None):
        return None
    return "bank_transfer" if amount is not None or day is not None else None
