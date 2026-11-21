"""Locate the first allegation and dates explicitly tied to the challenged act."""

import re

from .common import DATE, squash, to_iso

# Later allegations, remedies and the argument in support are separate evidence.
NEXT_ITEM = re.compile(r"(?im)(?:^\s*|(?<=[.;])\s+)(?:2[.)]\s|II[.)]\s|zarzut (?:nr )?2\b|uzasadnienie\b|wnoszę o\b)")
CHARGE = re.compile(r"\b(?:zarzuca(?:m|jąc)?|stawia zarzut)\b", re.IGNORECASE)
CHALLENGE = re.compile(
    r"\b(?:wnosz[ęą]|wnosi(?: niniejszym)?|składam)\s+(?:niniejsze\s+)?odwołanie\s+(?:wobec|od|na)\b"
    r"|\bodwołanie\s+(?:dotyczy|wobec)\b",
    re.IGNORECASE,
)
FILING = re.compile(
    r"\b(?:wnoszę|wnosimy|wnoszą|wnosi|składam|składamy|składa)\s+(?:niniejsze?\s+)?odwołanie\b", re.IGNORECASE
)
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


def sentences(text):
    """Split sentences and semicolon clauses, retaining dates, citations and legal abbreviations."""
    start = 0
    for stop in re.finditer(r"[;!?]|\.(?=\s|$)", text):
        if stop[0] == ".":
            before = text[start : stop.start()]
            after = text[stop.end() :].lstrip()
            if re.fullmatch(r"\d+|[IVX]+", before.strip()):
                continue
            if re.search(r"\b(?:art|ust|pkt|lit|poz|nr|im|ul|św|al|Dz|sygn)$", before, re.IGNORECASE):
                continue
            if after and after[0].islower() and re.search(r"\b(?:sp|o|j|k|p|a|r)$", before, re.IGNORECASE):
                continue
            if re.search(r"\bsp$", before, re.IGNORECASE) and re.match(r"(?:z|j|k|p)\b", after, re.IGNORECASE):
                continue
        yield squash(text[start : stop.start()])
        start = stop.end()
    yield squash(text[start:])


def first_sentence(text):
    return next(sentences(text))


def _act_in(passage):
    # More specific objects take precedence over the surrounding specification.
    for reason in (10, 7, 8, 6, 5, 12, 11, 1, 2, 3, 9, 4):
        if re.search(ACTS[reason], passage, re.IGNORECASE):
            return reason
    return None


def act_date(text, reason):
    # Only the notification or publication of this act starts its appeal deadline.
    cue = ACTS[reason]
    date = rf"(?P<day>{DATE})"
    clause = r"(?:(?![;!?]|\.(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ])|\b(?:termin|ustawy|odwołanie wniesiono)\b).)"
    # A date on a dependent document, or after a new clause, cannot date the act.
    clauses = re.split(
        r",(?!\s*(?:dokon\w*|podjęt\w*|ogłoszon\w*|z dnia|w dniu)\b)|\s+\b(?:a także|natomiast|podczas gdy)\b",
        text,
        flags=re.IGNORECASE,
    )
    named_entity = r"(?-i:[A-ZĄĆĘŁŃÓŚŹŻ])[\w-]*(?:\s+(?:(?-i:[A-ZĄĆĘŁŃÓŚŹŻ])[\w.-]*|sp\.|z|o\.o\.))*"
    citation = r"na podstawie art\.\s*\d+[a-z]?(?:\s+(?:ust|pkt|lit)\.?\s*[\da-z]+)*"
    patterns = [
        rf"(?:{cue}){clause}{{0,100}}?(?:powiadom\w*|poinform\w*|przekazan\w*|opublikowan\w*|zamieszczon\w*){clause}{{0,60}}?{date}",
        rf"(?:{cue})\s+(?:z\s+|w\s+)?(?:dnia|dniu)\s+{date}",
        rf"(?:{cue})\s+z\s+{date}",
        # The intervening text may identify the offer or cite its legal basis.
        rf"(?:{cue})\s+(?:{named_entity}|{citation}),?\s+(?:dokonan\w*\s+)?(?:w dniu|dnia)\s+{date}",
        rf"(?:w dniu|dnia)\s+{date}{clause}{{0,65}}?(?:poinform\w*|zawiadom\w*){clause}{{0,65}}?(?:{cue})",
    ]
    for part in clauses:
        for pattern in patterns:
            if match := re.search(pattern, part, re.IGNORECASE):
                return to_iso(match["day"])
    return None


def prose_action(text):
    first = CHARGE.search(text)
    charge = NEXT_ITEM.split(text[first.start() :], maxsplit=1)[0] if first else ""
    # A first numbered item may start on the next line after its introduction.
    charge = re.split(r"(?im)^\s*(?:[b-z]\)|2\s*[.)])", charge, maxsplit=1)[0]
    charge = squash(re.sub(r"(?:^|(?<=:)|(?<=\n))\s*(?:1|I)[.)]\s+", " ", charge))[:1250]
    through = re.search(r"\b(?:poprzez|polegając\w* na)\s+", charge, re.IGNORECASE)
    opening = charge[through.end() :] if through else charge
    reason = _act_in(first_sentence(opening))
    introduction = text[: first.start()] if first else text
    if reason is None:
        for match in reversed(list(CHALLENGE.finditer(introduction))):
            reason = _act_in(first_sentence(squash(introduction[match.end() :])))
            if reason:
                break
    if not reason:
        return None, None

    evidence = [charge]
    for filing in CHALLENGE.finditer(introduction):
        evidence.append(first_sentence(squash(introduction[filing.end() :])))
    if first and (later := NEXT_ITEM.search(text, first.end())):
        # A separately labelled notice or timeliness section may also date this act.
        notice_section = False
        for line in text[later.start() :].splitlines():
            heading = re.match(r"^([^:]{1,80}):[ \t]*(.*)$", line.strip())
            if heading:
                notice_section = bool(
                    re.search(r"\b(?:termin\w*|doręczen\w*|publikacj\w*|zawiadom\w*)\b", heading[1], re.IGNORECASE)
                )
                if notice_section:
                    evidence.append(heading[2])
            elif notice_section and not NEXT_ITEM.match(line):
                evidence[-1] += " " + line.strip()
            else:
                notice_section = False
    for section in evidence:
        for clause in sentences(squash(section)):
            day = act_date(clause, reason)
            if day:
                return day, reason
    return None, reason
