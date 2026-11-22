"""Trim OCR noise off the names and title of a scanned appeal.

The organizer counts a wrong value as one FP and a missing one as one FN, and a long string as a hit from 80 %
similarity (issue #59). Null therefore never beats a damaged value, and cutting noise off its end can only help.
This module trims and never replaces a present value with null.
"""

import re
from collections.abc import Callable

# Scanner noise from table rules, stamps and redaction boxes; none of these occurs in a party name or a title.
_STRAY = re.compile(r"[|{}~^=\\`\[\]]")
# What may be stripped from the end of a value. A name never ends in a bracket; a title may (`[ON, B7]`).
_NAME_END = " \t\r\n|{}~^=\\`[]"
_TITLE_END = " \t\r\n|{}~^=\\`"
# Corporate forms only: a civil partnership (`SC`, `spółka cywilna`) is followed by its partners' names, not by noise.
_LEGAL_FORM = re.compile(
    r"\b(?i:sp(?:ółka|\.)\s+z\s+(?:ograniczoną\s+odpowiedzialnością|o\.\s?o\.)"
    r"|spółka\s+(?:akcyjna|jawna|komandytowa|komandytowo-akcyjna|partnerska)"
    r"|s\.\s?a\.|sp\.\s?[kjp]\.|sp\.\s?k\.\s?a\.)"
    r"|(?<![\w-])(?:SA|SE|AG|GmbH)(?![\w-])"  # a hyphen is no boundary: AG-BUD is a name, not a legal form
)
# Short capitals are real in acronyms, but a run of them after the legal form is stamp noise.
_SHORT_CAPS = re.compile(r"[A-ZĄĆĘŁŃÓŚŹŻ]{1,5}")
# After the legal form: another consortium member, a role marker, a branch, a status, a seat or a number is not noise.
_KEEP_TAIL = re.compile(
    r"(?i)(?:^|\s)(?:i|oraz|&)(?:\s|$)|,|^\s*w\s|\d"
    r"|\b(?:partner|lider|członek|konsorcj|siedzib|oddzia[łl]|filia|zak[łl]ad|likwidacj|upad[łl]|restrukturyzacj)\w*"
)
# Stamp noise runs on; an all-capitals seat or unit ("W NOWYM SĄCZU", "ZW JAWORZNO III") is shorter than this.
_MIN_NOISE_TAIL = 6


def _noise(token: str) -> bool:
    """A stamp or scanner token: stray symbols without any letter, or short capitals that are no legal form."""
    if not any(c.isalnum() for c in token):
        return bool(_STRAY.search(token))
    core = token.strip(_NAME_END)  # a rule glued to a word ("|EBX") is read as the word
    return bool(_SHORT_CAPS.fullmatch(core)) and not _LEGAL_FORM.fullmatch(core)


def _cut_after_legal_form(text: str) -> str:
    """Drop a tail of scanner noise after the last legal form; keep a tail that names a member, branch or seat."""
    forms = list(_LEGAL_FORM.finditer(text))
    if not forms:
        return text
    head, rest = text[: forms[-1].end()], text[forms[-1].end() :].rstrip(_NAME_END)
    tail = rest.split()
    if not tail or _KEEP_TAIL.search(rest):
        return text
    noisy = sum(map(_noise, tail)) * 3 >= len(tail) * 2
    return head if noisy and (len(tail) >= _MIN_NOISE_TAIL or _STRAY.search(rest)) else text


def trim_name(text: str | None, *, legal_form: bool = True) -> str | None:
    """Return the name without its noisy tail or trailing stray symbols; None if only noise is left."""
    if not text:
        return text
    if legal_form:
        text = _cut_after_legal_form(text)
    return text.rstrip(_NAME_END) or None


def trim_title(text: str | None) -> str | None:
    """Return the title without trailing stray symbols. Titles keep brackets, `<`, `#`, numbers and legal forms."""
    if not text:
        return text
    return text.rstrip(_TITLE_END) or None


def _trim_person(text: str | None) -> str | None:
    return trim_name(text, legal_form=False)


def _squash(text: str) -> str:
    return " ".join(text.split()).casefold()


def trim_appeal(record: dict, native_text: str = "") -> None:
    """Trim the free-text fields of a scanned appeal. A value that is printed on a native page is not OCR output."""
    native = _squash(native_text)

    def trim(owner: dict, key: str, trimmer: Callable[[str], str | None]) -> None:
        if owner[key] and _squash(owner[key]) not in native:
            owner[key] = trimmer(owner[key])

    for party in record["Odwolujacy"]:
        trim(party, "nazwa", trim_name)
        trim(party["pelnomocnik"], "nazwa", trim_name)
        trim(party["pelnomocnik"], "imie_nazwisko", _trim_person)
    for party in record["Zamawiajacy"]:
        trim(party, "nazwa", trim_name)
    trim(record["ZamowieniePubliczne"], "tytul", trim_title)
