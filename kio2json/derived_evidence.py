"""Ground organizer codes and canonical notice numbers in explicit Polish source phrases."""

import re

from .appeal import REASON_RULES, REASONS, _first_sentence
from .class_config import OutputField
from .common import UPPER
from .output_schema import quote_covers, scalar_value

# Exclude substrings of longer references while allowing sentence punctuation.
LEFT = r"(?<![\w/–-])(?<!\w[.+@])"
RIGHT = r"(?![\w/–-]|[.+@]\w)"
NOTICE = {
    "numer_bzp": re.compile(LEFT + r"([0-9]{4})/BZP\s*([0-9]{8}(?:/[0-9]{2})?)" + RIGHT, re.IGNORECASE),
    "numer_ted": re.compile(
        LEFT + r"(?:([0-9]{4})/S\s*[0-9]{3}[-–]([0-9]{6})|([0-9]{6})[-–]([0-9]{4}))" + RIGHT, re.IGNORECASE
    ),
}
FIRST_CHARGE = re.compile(
    r"^[ \t]*(?:zarzut\s+(?:(?:nr\.?\s*)?[1I]|pierwszy)\b|zarzuty\s*:\s*[1I][.)])[:. \t–—-]*",
    re.IGNORECASE | re.MULTILINE,
)
END_CHARGE = re.compile(
    r"\bzarzut\s+(?:(?:nr\.?\s*)?2|drugi|II)\b|^[ \t]*(?:2[.)]|uzasadnienie\b)", re.IGNORECASE | re.MULTILINE
)
# The rule extractor uses stems. For citations, require the entire matching source word.
REASON_WORDS = [(reason, re.compile(r"\b(?:" + pattern + r")\w*\b", re.IGNORECASE)) for reason, pattern in REASON_RULES]

GRANTOR = r"^[ \t]*mocodawc[aą]\b[ \t]*(?::|jest\b)[ \t]*"
COMPANY_WORD = rf"(?!(?:przez|reprezentowan\w*|pełnomocni\w*)\b)(?-i:[{UPPER}])[\w&'’-]*"
COMPANY = (
    rf"(?:{COMPANY_WORD}[ \t]+){{1,10}}"
    + r"(?:sp\.[ \t]*z[ \t]*o\.[ \t]*o\.|s\.[ \t]*a\.|spółka (?:akcyjna|z ograniczoną odpowiedzialnością))"
)
END_GRANTOR = r"(?=[ \t]*(?:$|,?[ \t]+(?:z siedzibą|KRS\b|NIP\b|udziela\b)))"
APPELLANT = r"^[ \t]*odwołując[ya]\b(?:[ \t]*:[ \t]*(?:\n[ \t]*)?[^:\n;]{1,120}\n)?[ \t]*"
COUNSEL = r"(?:pełnomocnik(?:a|ów)|adwokat(?:a|ów)?|adw\.|radc[ęa] prawn(?:ego|y)|r\.[ \t]*pr\.)"
ROLE = {
    "typ": [
        (
            "osoba_prawna",
            re.compile(GRANTOR + rf"(osoba prawna|{COMPANY})" + END_GRANTOR, re.IGNORECASE | re.MULTILINE),
        ),
        ("osoba_fizyczna", re.compile(GRANTOR + r"(osoba fizyczna)" + END_GRANTOR, re.IGNORECASE | re.MULTILINE)),
    ],
    "przez-pelnomocnika": [
        (
            1,
            re.compile(
                APPELLANT + r"((?:(?:jest\s+)?reprezentowan[ya]\s+|działa\s+)przez\s+" + COUNSEL + r")(?!\w)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
        (
            0,
            re.compile(
                APPELLANT + r"((?:działa|występuje)\s+(?:osobiście|samodzielnie|bez pełnomocnika))\b",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
    ],
}
REASON_KEYS = {"czynnosc_powod_id", "czynnosc_opis"}
DERIVED_KEYS = REASON_KEYS | NOTICE.keys() | ROLE.keys()


def _reason(key: str, quote: str, text: str, visible_end: int | None):
    marker = FIRST_CHARGE.search(text)
    if marker is None:
        return None
    stop = END_CHARGE.search(text, marker.end())
    opening = _first_sentence(text[marker.end() : stop.start() if stop else None])
    for reason, pattern in REASON_WORDS:
        cue = pattern.search(opening)
        if cue:
            if quote_covers(quote, text, marker.end() + cue.start(), marker.end() + cue.end(), visible_end):
                return reason if key == "czynnosc_powod_id" else REASONS[reason]
            break
    return None


def derived_value(key: str, field: OutputField, proposed, quote: str, text: str, *, visible_end: int | None = None):
    """Return the proposed typed value only when the quoted source maps to it unambiguously."""
    if key not in DERIVED_KEYS or not quote.strip() or quote not in text:
        return None
    value = scalar_value(field, proposed)
    if key in REASON_KEYS:
        return value if value == _reason(key, quote, text, visible_end) else None
    candidates = set()
    if key in NOTICE:
        for match in NOTICE[key].finditer(text):
            if quote_covers(quote, text, *match.span(), visible_end):
                if key == "numer_bzp":
                    candidates.add(f"{match[1]}/BZP{match[2]}")
                else:
                    candidates.add(f"{match[2] or match[3]}-{match[1] or match[4]}")
    else:
        for candidate, pattern in ROLE[key]:
            if any(quote_covers(quote, text, *match.span(1), visible_end) for match in pattern.finditer(text)):
                candidates.add(candidate)
    return value if candidates == {value} else None
