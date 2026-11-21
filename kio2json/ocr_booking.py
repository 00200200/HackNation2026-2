"""Reassemble printed debit and execution fields on image-only receipt pages."""

import re

from rapidfuzz.distance import Levenshtein

from .bank_transfer import MONEY, transaction_values
from .common import DATE, to_iso

# On a single-debit history printout the two leftmost cells span multiple
# description rows. The status of the debit comes from its posted row and date.
INTERLEAVED_DEBIT = re.compile(
    rf"(?im)^data[ \t]+opis[ \t]+kwota[ \t]*\n"
    rf"data operacji[ \t]+[|:–-]*[ \t]*(przelew\b[^\n]*?[−-]{MONEY}\s*(?:PLN|zł))[ \t]*\n"
    rf"({DATE})[ \t]+(?=z rachunku\b)"
)
ORDER_TYPE = re.compile(r"(?im)^typ zlecenia[ :]+przelew\b")
BANK_SIGNATURE = re.compile(
    r"(?im)^dokument (\w+) prze[zż] bank[^\n]*\n"
    r"da[tł]a:[ \t]+(\d{4})[.-](\d{2})[.-](\d{2}) \d{1,2}:\d{2}:\d{2}\b"
)
REQUESTED_DAY = re.compile(r"(?im)^([\w]+ [\w]+ [\w]+)[ \t]+(\d{2})[. -](\d{2})[. -](\d{4})\b")


def _signed_order_day(text: str) -> str | None:
    # The requested day alone does not establish execution. On a completed
    # order, corroborate it with the bank's signature on the same day.
    if transaction_values(text)[1] is not None:
        return None
    signed = {
        "-".join(m.groups()[1:])
        for m in BANK_SIGNATURE.finditer(text)
        if Levenshtein.distance(m[1].casefold(), "podpisany", score_cutoff=2) <= 2
    }
    requested = {
        to_iso(".".join(m.groups()[1:]))
        for m in REQUESTED_DAY.finditer(text)
        if all(
            Levenshtein.distance(word, label, score_cutoff=2) <= 2
            for word, label in zip(m[1].casefold().split(), ("zlecona", "data", "wykonania"), strict=True)
        )
    }
    return next(iter(signed)) if len(signed) == 1 and signed == requested else None


def _order_state(m: re.Match) -> str:
    if Levenshtein.distance(m[1].casefold(), "status", score_cutoff=1) <= 1:
        return "Status: wykonane"
    return m[0]


def normalize_booking_rows(text: str) -> str:
    if len(INTERLEAVED_DEBIT.findall(text)) == 1:
        text = INTERLEAVED_DEBIT.sub(r"Opis Kwota\n\1\nData operacji: \2\n", text)
    if not ORDER_TYPE.search(text):
        return text
    # The ruled status cell has just one word. Extra words such as "nie"
    # prevent recognition even when a fold or stamp obscures the border.
    text = re.sub(r"(?im)^(\w+)[ .:|–-]+wykona[nń][aye][ .:,|–-]*$", _order_state, text)
    text = re.sub(r"(?m)^\|[ \t]*[A-Z]{1,2}[ \t]+(wykonan[aye])[ \t]*$", r"Status: \1", text)
    if not re.search(r"(?im)^status[ :]+wykonan[aye]\b", text):
        return text
    for owner, role in (("zleceniodawcy", "nadawcy"), ("kontrahenta", "odbiorcy")):
        # The account field directly below its party heading supplies the role,
        # even when OCR damages the inflected party name on the field itself.
        pattern = rf"(?im)^(dane {owner}[^\w\n]*\n)(\w+) (\w+)[ \t:|–-]+(?=(?:PL\s*)?\d{{2}}(?: ?\d{{4}}){{6}}\b)"

        def account(m: re.Match, role: str = role, owner: str = owner) -> str:
            return (
                m[1] + "Rachunek " + role + ": "
                if (
                    Levenshtein.distance(m[2].casefold(), "rachunek", score_cutoff=2) <= 2
                    and m[3].casefold().endswith(owner[-4:])
                    and Levenshtein.distance(m[3].casefold(), owner, score_cutoff=5) <= 5
                )
                else m[0]
            )

        text = re.sub(pattern, account, text)
    if re.search(r"(?im)^rachunek (?:nadawcy|zleceniodawcy)\b", text):
        text = re.sub(r"(?im)^rachunek kontrahenta[ :|–-]+", "Rachunek odbiorcy: ", text)
    text = re.sub(rf"(?im)^(dane zlecenia[ \t]*\n)[^\w\n]*({MONEY})[ \t]+(PLN|zł)[ \t]*$", r"\1Kwota: \2 \3", text)
    day = _signed_order_day(text)
    return text + "\nData operacji: " + day if day else text
