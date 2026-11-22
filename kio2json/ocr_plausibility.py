"""Null out OCR text that cannot be a name or title (FAQ 6: null beats an invented value)."""

import re
from collections.abc import Collection

# Isolated scanner marks between words, as opposed to operators in technical notation.
_MARK = re.compile(r"(?<!\S)[|{}~^=\\\[\]#<>—]+(?!\S)")
_LEGAL_FORM = re.compile(
    r"\b(?i:sp(?:ółka|\.)\s+z\s+(?:ograniczoną\s+odpowiedzialnością|o\.\s?o\.)"
    r"|spółka\s+(?:akcyjna|jawna|komandytowa|komandytowo-akcyjna|cywilna|partnerska)"
    r"|s\.\s?a\.|sp\.\s?[kjp]\.|sp\.\s?k\.\s?a\.)"
    r"|\b(?:SA|SC|SE|AG|GmbH)\b"
)
# A short capitals-only token: real in acronyms, but a run of them after the legal form is stamp noise.
_NOISE_TOKEN = re.compile(r"[A-ZĄĆĘŁŃÓŚŹŻ]{1,5}|\W+")
# A further consortium member or a role marker after the legal form is not noise.
_JOINER = re.compile(
    r"(?i)(?:^|\s)(?:i|oraz|&)(?:\s|$)|,|\b(?:partner|lider|członek|konsorcj|oddział|zakład|fili[aei]|delegatur)\w*"
)


def _noise(token: str) -> bool:
    return bool(_NOISE_TOKEN.fullmatch(token)) and not _LEGAL_FORM.fullmatch(token)


def _letter_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in chars) / len(chars) if chars else 0.0


def plausible_text(text: str | None, min_letters: float = 0.6) -> str | None:
    """Return the value, its clean prefix ending in a legal form, or None when it reads as OCR noise."""
    if not text:
        return text
    marks = _MARK.findall(text)
    if not min_letters:  # A technical title can contain formulas, brackets and legal forms.
        return None if len(marks) >= 2 and not any(c.isalpha() for c in text) else text
    forms = list(_LEGAL_FORM.finditer(text))
    if forms:
        head, rest = text[: forms[-1].end()], text[forms[-1].end() :]
        tail = rest.split()
        fragments = sum(len(word) == 1 for word in tail)
        noisy = len(tail) >= 5 and fragments >= 2 and sum(map(_noise, tail)) * 3 >= len(tail) * 2
        table_tail = len(tail) >= 2 and tail[0] == "|" and all(map(_noise, tail[1:]))
        if not _JOINER.search(rest) and (table_tail or noisy):
            return head
    if len(marks) >= 2 and (re.search(r"\|\s*[|\]]", text) or _letter_ratio(text) < min_letters):
        return None
    return text


def gate_appeal(record: dict, pages: list[str], ocr_pages: Collection[int]) -> None:
    """In a mixed PDF, change only values found on OCR pages and absent from native text."""
    if not ocr_pages:
        return

    def normalized(text: str) -> str:
        return " ".join(text.casefold().split())

    mixed = len(set(ocr_pages)) != len(pages)
    scanned = [normalized(page) for i, page in enumerate(pages, 1) if mixed and i in ocr_pages]
    native = [normalized(page) for i, page in enumerate(pages, 1) if mixed and i not in ocr_pages]

    def cleaned(value: str | None, min_letters: float = 0.6) -> str | None:
        if mixed and value:
            needle = normalized(value)
            if any(needle in page for page in native) or not any(needle in page for page in scanned):
                return value
        return plausible_text(value, min_letters)

    for party in record["Odwolujacy"]:
        party["nazwa"] = cleaned(party["nazwa"])
        lawyer = party["pelnomocnik"]
        for key in ("imie_nazwisko", "nazwa"):
            lawyer[key] = cleaned(lawyer[key])
    for party in record["Zamawiajacy"]:
        party["nazwa"] = cleaned(party["nazwa"])
    procurement = record["ZamowieniePubliczne"]
    procurement["tytul"] = cleaned(procurement["tytul"], min_letters=0.0)
