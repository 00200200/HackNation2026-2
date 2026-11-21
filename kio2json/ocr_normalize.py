"""Conservative substitutions for text produced by OCR."""

import re
from itertools import product

from stdnum import iban

# Only substitute characters with a plausible digit shape inside a complete Polish NRB.
GLYPHS = {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "/": "17", "S": "5", "B": "8"}
_ACCOUNT_CHAR = r"[0-9OoIl|/SB]"
_ACCOUNT = re.compile(rf"(?<![\w/])(?:PL[ \t]?)?({_ACCOUNT_CHAR}{{2}}(?:[ \t\n]?{_ACCOUNT_CHAR}{{4}}){{6}})(?![\w/])")
_FORM = re.compile(r"(?i)(\bsp\.[ \t]*z[ \t]+)[o0]\.[ \t]*[o0]\.")
# Obfuscated addresses have an explicit separator. A bare Q, O, or space is ambiguous.
_MAIL = re.compile(r"(?<=\w)[ \t]*(?:\[at\]|\(at\)|@)[ \t]*(?=[\w-]+(?:\.[\w-]+)+\b)", re.IGNORECASE)


def _repair_account(match: re.Match) -> str:
    number = re.sub(r"\s", "", match[1])
    if number.isdigit() or sum(not c.isdigit() for c in number) > 2:
        return match[0]
    candidates = ("".join(digits) for digits in product(*(GLYPHS.get(c, c) for c in number)))
    valid = [n for n in candidates if iban.is_valid("PL" + n)]
    return valid[0] if len(valid) == 1 else match[0]


def normalize_ocr(text: str) -> str:
    text = _FORM.sub(lambda match: match[1] + "o.o." if "0" in match[0] else match[0], text)
    return _MAIL.sub("@", _ACCOUNT.sub(_repair_account, text))
