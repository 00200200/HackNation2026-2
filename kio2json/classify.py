"""Classify by the document's own heading and transaction evidence."""

import re

from rapidfuzz.distance import Levenshtein

from .bank_transfer import AccountEvidence, account_evidence, transaction_values

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
        if Levenshtein.distance(heading, "ODWOŁANIE", score_cutoff=1) <= 1:
            party = re.search(r"odwo[łl]uj[ąa]c", head, re.IGNORECASE)
            labelled_parties = re.search(r"(?im)^(?:wykonawca|odwo[łl]uj[ąa]cy)\s*[:(]", head) and re.search(
                r"(?im)^zamawiaj[ąa]cy\s*[:(]", head
            )
            if (heading == "ODWOŁANIE" and party) or labelled_parties:
                return "appeal", None
        if heading in {"PEŁNOMOCNICTWO", "PEŁNOMOCNICTWOPROCESOWE", "PEŁNOMOCNICTWOSZCZEGÓLNE"}:
            return "power_of_attorney", None
        if CONFIRMATION_HEADING.match(line):
            transfer_heading = True
            break

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    statuses = [m[1] for line in lines if (m := STATUS.match(line))]
    if any(not EXECUTED.match(status) for status in statuses):
        return None, None
    if not transfer_heading and not any(EXECUTED.match(line) for line in lines):
        return None, None
    if "przelew" not in first.casefold():
        return None, None
    amount, day = transaction_values(first)
    if amount is None and day is None:
        return None, None
    accounts = account_evidence(first)
    if accounts.distinct_numbers < 2 and not (
        transfer_heading and accounts.distinct_numbers == 1 and amount is not None and day and accounts.masked_pair
    ):
        return None, None
    return "bank_transfer", accounts
