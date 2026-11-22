"""Identify a sole proprietor from the grantor's declaration or identity card."""

import re

from .common import PERSON, registry_ids, squash
from .personal_names import compatible_names, nominative

UNDERSIGNED = r"(?:ja,?\s+(?:niżej\s+)?|niżej\s+)podpisan[ay](?:/[ay])?"
GRANTOR_CAPTION = (
    r"(?:dane|oznaczenie)\s+mocodawcy|mocodawc[ąa](?:\s+jest)?|wykonawca"
    r"|(?:osob[aą]\s+)?udzielając[ay]\s+(?:pełnomocnictwa|umocowania)"
)
PASSIVE_ISSUER = r"(?:pełnomocnictw[oa]|umocowani[ae])\s+udzielon[ey]\s+przez"
OWNER_TITLE = r"właściciel(?:ka|em|ką)?\s+(?:firmy|zakładu|pracowni|przedsiębiorstwa|warsztatu|sklepu)"
ISSUER = re.compile(
    rf'(?<![„"«])\b(?:(?P<genitive>działając\s+w\s+imieniu)|(?P<accusative>{PASSIVE_ISSUER})|{GRANTOR_CAPTION}'
    rf"|(?P<first_person>{UNDERSIGNED}|ja))\b"
    r"[ \t,:–—-]*",
    re.IGNORECASE,
)
TRADING = re.compile(
    rf"\b(?:CEIDG|przedsiębiorc(?:a|ą|y)|{OWNER_TITLE}|osob[aą] fizyczn[aą]|pod (?:firmą|nazwą)|jednoosobow\w*\s+działalnoś\w*|prowadz\w*(?:/[ay])?\s+(?:jednoosobow\w*\s+)?"
    r"działalność(?:\s+gospodarczą)?)",
    re.IGNORECASE,
)
PERSON_FIELD = re.compile(
    rf"(?im:^[ \t]*(?:imię i nazwisko(?: przedsiębiorcy| mocodawcy)?|właściciel(?:ka)?)\s*:\s*)({PERSON})(?=[,;\n]|$)"
)
SPLIT_PERSON = re.compile(r"(?im:^[ \t]*imię(?: pierwsze)?\s*:\s*)(\S+)\s+(?i:nazwisko\s*:\s*)(\S+)")
ENTREPRENEUR = re.compile(r"(?i:^(?:przedsiębiorc[aą]|osoba fizyczna)\b[ \t,:–—-]*)")
OWNER_SUBJECT = re.compile(
    rf'(?im:^[ \t]*(?:jako\s+)?{OWNER_TITLE})\s+[„«"](?P<business>[^\n„»”"]+)[”»"](?:\s*,\s*(?i:ja,?\s+)?|\s+(?i:ja,?\s+))(?P<person>{PERSON})\b'
)
FIRM = re.compile(
    r"(?P<narrative>\bpod\s+(?:firmą|nazwą))\s*:?\s*|^[ \t]*(?:firma(?: przedsiębiorcy)?|nazwa (?:firmy|przedsiębiorstwa))\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)
NAME_DELIMITER = r"[,;]|\s+[–—]\s+|\s+\b(?:NIP|REGON|CEIDG|zamieszkał\w*|z\s+siedzibą|wpisan\w*)\b"
END_NAME = re.compile(rf"\n|{NAME_DELIMITER}", re.IGNORECASE)
# In a sentence the business name can wrap. A new form field or paragraph still ends it.
NEXT_FIELD = re.compile(r"\n(?=[ \t]*(?:\n|(?:imię|adres|właściciel)\b|[^\W\d_][\w ./()-]{0,60}:))", re.IGNORECASE)
QUOTES = {"„": "”", "“": "”", "«": "»", '"': '"'}
RECIPIENT_ROLE = (
    r"pełnomocni(?:k\w*|cy|czk\w*)|osob\w*\s+(?:upoważnion\w*|umocowan\w*)"
    r"|zamawiając\w*|odbiorc\w*|uczestni(?:k\w*|cy|czk\w*)|świadek|świadk\w*"
)
OTHER_PARTY = re.compile(
    rf"\b(?:{RECIPIENT_ROLE})[ \t]*:|^[ \t]*(?:dane\s+)?(?:{RECIPIENT_ROLE})\b",
    re.IGNORECASE | re.MULTILINE,
)


def _business_name(raw: str, *, narrative: bool) -> str:
    value = squash(NEXT_FIELD.split(raw, maxsplit=1)[0] if narrative else raw.partition("\n")[0])
    outer_quote = value[:1] in QUOTES
    closings = []
    for i, char in enumerate(value):
        if closings and char == closings[-1]:
            closings.pop()
            if outer_quote and not closings:
                return value[1:i].strip()
        elif char in QUOTES:
            closings.append(QUOTES[char])
        elif not closings and END_NAME.match(value, i):
            return value[:i].strip()
    # A missing closing quote does not claim later registry or address fields.
    return END_NAME.split(value, maxsplit=1)[0].strip() if closings else value


def _firm_owner(business: str, inflected: str | None = None) -> str | None:
    """A registered trade name can print the owner's name before or after the brand."""
    words = business.split()
    if len(words) < 2:
        return None
    edges = {" ".join(words[:2]), " ".join(words[-2:])}
    candidates = {
        edge
        for edge in edges
        if edge != inflected
        and re.fullmatch(PERSON, edge)
        and (compatible_names(inflected, edge) if inflected else nominative(edge, "nom") == edge)
    }
    return candidates.pop() if len(candidates) == 1 else None


def sole_trader(declaration: str, company_pattern: re.Pattern) -> dict | None:
    """Require both the identity of a natural person and local evidence of their business."""
    slots = []
    last_explicit = 0
    for marker in ISSUER.finditer(declaration):
        if marker["first_person"] and OTHER_PARTY.search(declaration, last_explicit, marker.start()):
            continue
        if not marker["first_person"]:
            last_explicit = marker.end()
        case = "gen" if marker["genitive"] else "acc" if marker["accusative"] else "nom"
        slots.append((marker.end(), case, False))
    if owner := OWNER_SUBJECT.match(declaration.lstrip()):
        start = len(declaration) - len(declaration.lstrip()) + owner.start("person")
        slots.insert(0, (start, "nom", True))
    if not slots:
        # Without a caption, require a grammatical subject at the beginning of a line.
        bare = re.search(
            rf"(?m)^[ \t]*(?:(?i:przedsiębiorca)\s*[:–—-]?\s+({PERSON})\b"
            rf"|({PERSON})[\s,]+(?i:wpisan|prowadzą|wykonują|właściciel))",
            declaration,
        )
        if bare and not OTHER_PARTY.search(declaration, 0, bare.start()):
            slots.append((bare.start(), "nom", True))

    for start, case, subject in slots:
        clause = OTHER_PARTY.split(declaration[start:].lstrip(), maxsplit=1)[0]
        identifiers = registry_ids(clause)
        if ISSUER.search(clause) or company_pattern.search(clause) or identifiers["krs"]:
            continue
        firm = FIRM.search(clause)
        trading = TRADING.search(clause)
        if not (subject or trading or firm or identifiers["nip"]):
            continue

        identity = ENTREPRENEUR.sub("", clause, count=1).lstrip()
        identity = END_NAME.split(identity, maxsplit=1)[0].partition("(")[0]
        identity = TRADING.split(identity, maxsplit=1)[0].strip(" .:")
        field = PERSON_FIELD.search(clause)
        split_field = SPLIT_PERSON.search(clause)
        if field:
            identity = squash(field[1])
        elif split_field:
            identity = " ".join(split_field.groups())
        business = _business_name(clause[firm.end() :], narrative=bool(firm["narrative"])) if firm else None
        if re.fullmatch(PERSON, identity):
            name = squash(identity)
            if case != "nom" and not (field or split_field):
                name = nominative(name, case) or (_firm_owner(business, name) if business else None)
                if name is None:
                    continue
            elif not (field or split_field) and (not subject or ENTREPRENEUR.match(clause)):
                # A two-word brand in an issuer slot alone does not identify its owner.
                narrative = re.match(rf"{PERSON}\s*,?\s*(?i:prowadz|przedsiębiorc|właściciel|wpisan)", clause)
                if not narrative and nominative(name, "nom") != name:
                    continue
        else:
            words = identity.split()
            if field or split_field or not (trading or subject):
                continue
            if not business and len(words) >= 3:
                business = identity
            name = _firm_owner(business) if business else None
            if not name:
                continue
        if not business and subject and owner:
            business = squash(owner["business"])
        if not business and (title := re.search(rf'(?i:{OWNER_TITLE})\s+(?=[„«"])', clause)):
            business = _business_name(clause[title.end() :], narrative=True)
        return {
            "imie_nazwisko": name,
            "krs": None,
            "nazwa": business,
            "nip": identifiers["nip"],
            "typ": "osoba_fizyczna",
        }
    return None
