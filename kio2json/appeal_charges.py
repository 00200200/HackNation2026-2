"""Locate the first allegation and dates explicitly tied to the challenged act."""

import re

from .common import DATE, find_date, squash, to_iso

# Later allegations, remedies and the argument in support are separate evidence.
NEXT_ITEM = re.compile(r"(?im)(?:^\s*|(?<=[.;])\s+)(?:2[.)]\s|II[.)]\s|zarzut (?:nr )?2\b|uzasadnienie\b|wnoszę o\b)")
CHARGE = re.compile(r"\b(?:zarzuca(?:m|jąc)?|stawia zarzut)\b", re.IGNORECASE)
CHALLENGE = re.compile(
    r"\b(?:wnosz[ęą]|wnosi(?: niniejszym)?|składam)\s+(?:niniejsze\s+)?odwołanie\s+(?:wobec|od|na)\b"
    r"|\bodwołanie\s+(?:dotyczy|wobec)\b",
    re.IGNORECASE,
)
CLAUSE_END = re.compile(r"(?:;|\.(?=\s+[A-ZĄĆĘŁŃÓŚŹŻ]))")
ACTS = {
    1: r"odrzuc\w*\s+ofert\w*",
    2: r"wyb[oó]r\w*\s+(?:najkorzystniejsz\w*\s+)?ofert\w*",
    3: r"wyklucz\w*\s+wykonawc\w*",
    4: r"(?:specyfikacj\w*|\bsi?wz\b)",
    5: r"(?:modyfikacj\w*|zmian\w*)\s+(?:treści\s+)?si?wz",
    6: r"(?:wyjaśnie\w*|odpowied[źz]\w*)\s+(?:treści\s+)?(?:si?wz|zamawiającego|na pytani)",
    7: r"(?:zaniecha\w*\s+odrzuceni\w*|nie odrzucił)\s+ofert\w*",
    8: r"(?:zaniecha\w*\s+wykluczeni\w*|nie wykluczył)\s+wykonawc\w*",
    9: r"unieważni\w*\s+postępowani\w*",
    10: r"(?:zaniecha\w*\s+unieważnieni\w*|nie unieważnił)\s+postępowani\w*",
    11: r"opis\w*\s+przedmiotu zamówienia|\bopz\b",
    12: r"(?:wz[oó]r\w*|projekt\w*|postanowieni\w*)\s+umow\w*",
}


def _act_in(passage):
    # More specific objects take precedence over the surrounding specification.
    for reason in (10, 7, 8, 6, 5, 12, 11, 1, 2, 3, 9, 4):
        if re.search(ACTS[reason], passage, re.IGNORECASE):
            return reason
    return None


def _act_date(text, reason):
    # Only the notification or publication of this act starts its appeal deadline.
    cue = ACTS[reason]
    date = rf"(?P<day>{DATE})"
    clause = r"(?:(?![;!?]|\.(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ])|\b(?:termin|ustawy|odwołanie wniesiono)\b).)"
    patterns = [
        rf"(?:{cue}){clause}{{0,100}}?(?:powiadom\w*|poinform\w*|przekazan\w*|opublikowan\w*|zamieszczon\w*){clause}{{0,60}}?{date}",
        rf"(?:{cue})\s+(?:z\s+|w\s+)?(?:dnia|dniu)\s+{date}",
        rf"(?:{cue})\s+z\s+{date}",
        rf"(?:w dniu|dnia)\s+{date}{clause}{{0,65}}?(?:poinform\w*|zawiadom\w*){clause}{{0,65}}?(?:{cue})",
    ]
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE):
            return to_iso(match["day"])
    return None


def prose_action(text):
    first = CHARGE.search(text)
    charge = NEXT_ITEM.split(text[first.start() :], maxsplit=1)[0] if first else ""
    # A first numbered item may start on the next line after its introduction.
    charge = re.split(r"(?im)^\s*(?:[b-z]\)|2\s*[.)])", charge, maxsplit=1)[0]
    charge = squash(charge)[:1250]
    through = re.search(r"\b(?:poprzez|polegając\w* na)\s+", charge, re.IGNORECASE)
    opening = charge[through.end() :] if through else charge
    reason = _act_in(CLAUSE_END.split(opening, maxsplit=1)[0])
    introduction = text[: first.start()] if first else text
    if reason is None:
        for match in reversed(list(CHALLENGE.finditer(introduction))):
            passage = squash(introduction[match.end() :])[:1100]
            # Exclude the next numbered charge and subsequent sentences.
            passage = re.split(r"(?i)\.(?=\s+(?:Zamawiający|Odwołujący|Postępowanie)\b)|;", passage, maxsplit=1)[0]
            reason = _act_in(passage)
            if reason:
                break
    if not reason:
        return None, None

    dated_text = text
    if first and (later := NEXT_ITEM.search(text, first.end())):
        dated_text = text[: later.start()]
        # The timeliness section may separately date publication or notification.
        deadline = re.search(
            r"(?im)^termin (?:wniesienia odwołania|na wniesienie odwołania)[^\n]*", text[later.end() :]
        )
        if deadline:
            start = later.end() + deadline.end()
            dated_text += "\n" + text[start : start + 600]
    flat = squash(re.sub(r"(?<=\d)\.\s+(?=\d{2}\.|\d{4}\b)", ".", dated_text))
    day = _act_date(flat, reason)
    if not day and (
        notice := re.search(rf"({DATE})\s+r?\.?\s+stanowi\s+początkową datę biegu terminu", flat, re.IGNORECASE)
    ):
        day = find_date(notice[0])
    return day, reason
