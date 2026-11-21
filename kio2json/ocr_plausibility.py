"""Null out OCR text that cannot be a name or title (FAQ 6: null beats an invented value)."""

import re

# Scanner noise from table rules and stamps; these never occur in a party name or a procurement title.
_STRAY = re.compile(r"[|{}~^=\\]")
_LEGAL_FORM = re.compile(
    r"\b(?i:sp(?:ółka|\.)\s+z\s+(?:ograniczoną\s+odpowiedzialnością|o\.\s?o\.)"
    r"|spółka\s+(?:akcyjna|jawna|komandytowa|komandytowo-akcyjna|cywilna|partnerska)"
    r"|s\.\s?a\.|sp\.\s?[kjp]\.|sp\.\s?k\.\s?a\.)"
    r"|\b(?:SA|SC|SE|AG|GmbH)\b"
)
# A short capitals-only token: real in acronyms, but a run of them after the legal form is stamp noise.
_NOISE_TOKEN = re.compile(r"[A-ZĄĆĘŁŃÓŚŹŻ]{1,5}|\W+")
# A further consortium member or a role marker after the legal form is not noise.
_JOINER = re.compile(r"(?i)(?:^|\s)(?:i|oraz|&)(?:\s|$)|,|\b(?:partner|lider|członek|konsorcj)\w*")
# A law firm named after a professional title ends in that lawyer's name; a given name followed by
# one to three capitals is a misread surname (a full surname in capitals is longer).
_LAWYER_TITLE = re.compile(r"(?i)\b(?:adwokat\w*|radc\w*\s+prawn\w*)\s+(.+)$")
_MISREAD_SURNAME = re.compile(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+\s+[A-ZĄĆĘŁŃÓŚŹŻ]{1,3}\b(?!\.)")


def _noise(token: str) -> bool:
    return bool(_NOISE_TOKEN.fullmatch(token)) and not _LEGAL_FORM.fullmatch(token)


def _letter_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in chars) / len(chars) if chars else 0.0


def plausible_text(text: str | None, min_letters: float = 0.6) -> str | None:
    """Return the value, its clean prefix ending in a legal form, or None when it reads as OCR noise."""
    if not text:
        return text
    forms = list(_LEGAL_FORM.finditer(text))
    if forms:
        head, rest = text[: forms[-1].end()], text[forms[-1].end() :]
        tail = rest.split()
        noisy = sum(map(_noise, tail)) * 3 >= len(tail) * 2
        if _STRAY.search(rest) or (len(tail) >= 3 and noisy and not _JOINER.search(rest)):
            text = head
    if _STRAY.search(text) or _letter_ratio(text) < min_letters:
        return None
    if (lawyer := _LAWYER_TITLE.search(text)) and _MISREAD_SURNAME.search(lawyer[1]):
        return None
    return text


def gate_appeal(record: dict) -> None:
    """Apply `plausible_text` to the free-text fields of a scanned appeal."""
    for party in record["Odwolujacy"]:
        party["nazwa"] = plausible_text(party["nazwa"])
        lawyer = party["pelnomocnik"]
        for key in ("imie_nazwisko", "nazwa"):
            lawyer[key] = plausible_text(lawyer[key])
    for party in record["Zamawiajacy"]:
        party["nazwa"] = plausible_text(party["nazwa"])
    procurement = record["ZamowieniePubliczne"]
    # Titles legitimately carry dates and numbers, so only stray symbols reject them.
    procurement["tytul"] = plausible_text(procurement["tytul"], min_letters=0.0)
