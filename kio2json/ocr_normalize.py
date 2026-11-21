"""Conservative substitutions for text produced by OCR."""

import re
from itertools import product

from stdnum import iban

from .common import EMAIL_RE

# Only substitute characters with a plausible digit shape inside a complete Polish NRB.
GLYPHS = {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "/": "17", "S": "5", "B": "8"}
_ACCOUNT_CHAR = r"[0-9OoIl|/SB]"
_ACCOUNT = re.compile(rf"(?<![\w/])(?:PL[ \t]?)?({_ACCOUNT_CHAR}{{2}}(?:[ \t\n]?{_ACCOUNT_CHAR}{{4}}){{6}})(?![\w/])")
_FORM = re.compile(r"(?i)(\bsp\.[ \t]*z[ \t]+)[o0]\.[ \t]*[o0]\.")
# Obfuscated addresses have an explicit separator. A bare Q, O, or space is ambiguous.
_MAIL = re.compile(r"(?<=\w)[ \t]*(?:\[at\]|\(at\)|@)[ \t]*(?=[\w-]+(?:\.[\w-]+)+\b)", re.IGNORECASE)

MAIL_TOKEN_RE = re.compile(r"[\w.+%©®\-]+\.[a-zA-Z]{2,}")

# Only canonicalize dedicated headings and role labels. Keep ordinary words and proper names verbatim.
_HEADING = re.compile(r"(?im)^([ \t]*)(ODWOLANIE|PELNOMOCNICTWO)(?=[ \t]*(?:PROCESOWE[ \t]*)?$)")
_APPELLANT = re.compile(r"(?im)^([ \t]*)Odwo[lł]uj[aą]cy(?=[ \t]*[:(])")


def _repair_account(match: re.Match) -> str:
    number = re.sub(r"\s", "", match[1])
    if number.isdigit() or sum(not c.isdigit() for c in number) > 2:
        return match[0]
    candidates = ("".join(digits) for digits in product(*(GLYPHS.get(c, c) for c in number)))
    valid = [n for n in candidates if iban.is_valid("PL" + n)]
    return valid[0] if len(valid) == 1 else match[0]


def confirmed_email(raw: str, second_read: str) -> str:
    """Accept a second OCR reading only when the two disagree on the separator alone."""
    if EMAIL_RE.fullmatch(second_read):
        local, domain = second_read.split("@")
        if any(raw == local + glyph + domain for glyph in ("", "Q", "O", "0", "©", "®", "e")):
            return second_read
    return raw


def normalize_ocr(text: str) -> str:
    text = _FORM.sub(lambda match: match[1] + "o.o." if "0" in match[0] else match[0], text)
    text = _HEADING.sub(lambda m: m[1] + m[2].upper().replace("L", "Ł"), text)
    text = _APPELLANT.sub(r"\1Odwołujący", text)
    return _MAIL.sub("@", _ACCOUNT.sub(_repair_account, text))
