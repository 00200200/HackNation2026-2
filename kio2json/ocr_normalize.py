"""Conservative substitutions for text produced by OCR."""

import re
from itertools import product

from .accounts import IBAN_COUNTRIES, account_pattern, has_detached_country, normalize_account, valid_account
from .common import EMAIL_RE

# Only substitute characters with a plausible digit shape inside a complete Polish NRB.
GLYPHS = {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "/": "17", "S": "5", "B": "8"}
_ACCOUNT_CHAR = r"[0-9OoIl|/SB]"
_ACCOUNT = account_pattern(_ACCOUNT_CHAR, "[A-Za-z]", "[A-Za-z0-9]")
_FORM = re.compile(r"(?i)(\bsp\.[ \t]*z[ \t]+)[o0]\.[ \t]*[o0]\.")
# Obfuscated addresses have an explicit separator. A bare Q, O, or space is ambiguous.
_MAIL = re.compile(r"(?<=\w)[ \t]*(?:\[at\]|\(at\)|@)[ \t]*(?=[\w-]+(?:\.[\w-]+)+\b)", re.IGNORECASE)

MAIL_TOKEN_RE = re.compile(r"[\w.+%©®\-]+\.[a-zA-Z]{2,}")

# Only canonicalize dedicated headings and role labels. Keep ordinary words and proper names verbatim.
_HEADING = re.compile(r"(?im)^([ \t]*)(ODWOLANIE|PELNOMOCNICTWO)(?=[ \t]*(?:PROCESOWE[ \t]*)?$)")
_APPELLANT = re.compile(r"(?im)^([ \t]*)Odwo[lł]uj[aą]cy(?=[ \t]*[:(])")


def _repair_account(match: re.Match) -> str:
    raw = "".join(match[1].split())
    if normalize_account(raw):
        return match[0]
    country = raw[:2] if raw[:2].upper() in IBAN_COUNTRIES else ""
    if not country and has_detached_country(match.string[: match.start()]):
        return match[0]
    body = raw[len(country) :]
    if sum(c in GLYPHS for c in body) > 2:
        return match[0]
    # A letter in a foreign BBAN can be genuine, even beside a damaged digit.
    choices = [c + GLYPHS[c] if c in GLYPHS else c for c in body]
    candidates = (country + "".join(parts) for parts in product(*choices))
    valid = [candidate for candidate in candidates if valid_account(candidate)]
    if len(valid) == 1:
        return valid[0]
    return match[0]


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
