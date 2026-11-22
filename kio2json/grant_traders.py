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
    r"(?P<narrative>\bpod\s+(?:firmą|nazwą))[ \t]*:?[ \t]*|^[ \t]*(?:firma(?: przedsiębiorcy)?|nazwa (?:firmy|przedsiębiorstwa))[ \t]*:[ \t]*",
    re.IGNORECASE | re.MULTILINE,
)
RECIPIENT_ROLE = (
    r"pełnomocni(?:k\w*|cy|czk\w*)|osob\w*\s+(?:upoważnion\w*|umocowan\w*)"
    r"|zamawiając\w*|odbiorc\w*|uczestni(?:k\w*|cy|czk\w*)|świadek|świadk\w*"
)
# Printed field labels may qualify the business name with the registry that supplied it.
FIRM_LABEL = re.compile(
    r"(?i)(?:\bpełna\s+)?\b(?:firma(?:\s+(?:przedsiębiorcy|mocodawcy))?|"
    r"nazwa\s+(?:handlowa|firmy|przedsiębiorcy|działalności(?:\s+gospodarczej)?|przedsiębiorstwa))"
    r"(?:[ \t]*(?:\((?:wg\.? |według )?CEIDG\)|(?:wg\.? |według |w )CEIDG))?[ \t]*:[ \t]*"
)
STATIONERY = re.compile(
    r"(?im)^[ \t]*(?:piecz(?:ęć|ątka)|stempel|papier firmowy|nagłówek firmowy)"
    r"(?:[ \t]+firmow[ay])?(?:[ \t]+(?P<issuer>mocodawcy|przedsiębiorcy|wystawcy))?"
    r"[ \t]*(?:[:–—-][ \t]*|(?=$))"
)
CONTACT_CAPTION = (
    r"osoba (?:do kontaktu|kontaktowa)|dane kontaktowe|kontakt(?: do korespondencji)?|"
    r"adres(?:at)? (?:do )?korespondencji|koordynator(?: postępowania)?"
)
FOREIGN_CARD = (
    rf"(?:dane\s+|oznaczenie\s+)?(?:{RECIPIENT_ROLE}|kontrahent\w*|adresat\w*|klient\w*|"
    rf"nabywc\w*|dostawc\w*|{CONTACT_CAPTION})"
)
FOREIGN_FIELD = re.compile(rf"(?im)(?:^|[;|])[ \t]*{FOREIGN_CARD}\b")
CARD_END = re.compile(
    rf"(?im)^[ \t]*(?:{FOREIGN_CARD}|"
    r"podpis\w*|za zgodność|załącznik\w*|pełnomocnictw\w*|mocodawc[ąa]|udzielam|ustanawiam)\b"
)
TRADE_LINE = re.compile(
    r"(?i)\b(?:przedsiębiorstwo|zakład|usługi|biuro|pracownia|warsztat|studio|handel|sklep|"
    r"produkcja|serwis|drukarnia|hurtownia|firma|kancelaria|atelier|PHU|P[.]?P[.]?H[.]?U[.]?)\b"
)
NO_FIRM = re.compile(
    r"(?i)^[\s._–—-]*(?:\[?\s*(?:brak(?: danych)?|nie (?:podano|dotyczy)|nieczyteln[aye](?: odcisk pieczęci)?|"
    r"miejsce na piecz[ęą]\w*|nazwa firmy)\s*\]?)?[\s._–—-]*$"
)
NAME_DELIMITER = r"[,;]|\s+[–—]\s+|\s+\b(?:NIP|REGON|CEIDG|zamieszkał\w*|z\s+siedzibą|wpisan\w*)\b"
END_NAME = re.compile(rf"\n|{NAME_DELIMITER}", re.IGNORECASE)
# In a sentence the business name can wrap. A new form field or paragraph still ends it.
NEXT_FIELD = re.compile(r"\n(?=[ \t]*(?:\n|(?:imię|adres|właściciel)\b|[^\W\d_][\w ./()-]{0,60}:))", re.IGNORECASE)
QUOTES = {"„": "”", "“": "”", "«": "»", '"': '"'}
OTHER_PARTY = re.compile(
    rf"\b(?:{RECIPIENT_ROLE})[ \t]*:|^[ \t]*(?:dane\s+)?(?:{RECIPIENT_ROLE})\b",
    re.IGNORECASE | re.MULTILINE,
)


def _business_name(raw: str, *, narrative: bool) -> str:
    # A label on the next line starts a new field when the firm box is blank.
    if raw.lstrip(" \t").startswith(("\r", "\n")) and re.match(r"[^\W\d_][\w ./()-]{0,60}[:：]", raw.lstrip()):
        return ""
    raw = raw.lstrip()
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


def printed_firm(value: str | None) -> str | None:
    if not value or not any(c.isalpha() for c in value) or NO_FIRM.fullmatch(value):
        return None
    if re.match(r"(?i)^(?:(?:NIP|KRS|REGON|PESEL)\b|(?:adres|podpis|imię|nazwisko)\b[ \t]*:)", value):
        return None
    return value


def _stationery_name(block: str, person: str, nip: str | None, *, designated: bool, stamp: bool) -> str | None:
    lines = [line.strip() for line in block.splitlines() if line.strip()][:7]
    if not lines:
        return None
    block = "\n".join(lines)
    ids = registry_ids(block)
    if ids["krs"] or (ids["nip"] and nip and ids["nip"] != nip):
        return None
    labelled_people = {squash(m[1]).casefold() for m in PERSON_FIELD.finditer(block)}
    if labelled_people and labelled_people != {person.casefold()}:
        return None
    person_re = re.compile(rf"(?<!\w){re.escape(person)}(?!\w)", re.IGNORECASE)
    if not (designated or person_re.search(block) or (nip and ids["nip"] == nip)):
        return None
    fields = list(FIRM_LABEL.finditer(block))
    if fields:
        values = {printed_firm(_business_name(block[field.end() :], narrative=False)) for field in fields}
        values.discard(None)
        return values.pop() if len(values) == 1 else None
    line = next((line for line in lines if line.casefold() != person.casefold()), "")
    # Plain stationery can start with a date, an address or the person's name.
    # A named stamp explicitly designates its first value as the firm's legend.
    if not line or ":" in line or "@" in line:
        return None
    if not (
        stamp
        or (ids["nip"] and nip == ids["nip"] and person_re.search(line))
        or TRADE_LINE.search(line)
        or line[:1] in QUOTES
    ):
        return None
    if re.match(r"(?i)^(?:ul\.|al\.|adres|NIP|REGON|tel\.|e-mail|do |za |[0-9])", line):
        return None
    return printed_firm(_business_name(line, narrative=False))


def stationery_firm(text: str, heading: re.Match | None, person: str, nip: str | None) -> str | None:
    """Bind a letterhead or stamp to the sole issuer, keeping contradictory names empty."""
    candidates = set()
    marks = list(STATIONERY.finditer(text))
    body = text[heading.end() :] if heading else text
    headers = [text[: heading.start()]] if heading else []
    if issuer := ISSUER.search(body):
        headers.append(body[: issuer.start()])
    for header in headers:
        if STATIONERY.search(header) or CARD_END.search(header):
            continue
        if value := _stationery_name(header, person, nip, designated=False, stamp=False):
            candidates.add(value)
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = CARD_END.split(text[mark.end() : end].lstrip(), maxsplit=1)[0]
        if value := _stationery_name(block, person, nip, designated=bool(mark["issuer"]), stamp=True):
            candidates.add(value)
    return candidates.pop() if len(candidates) == 1 else None


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
        firm_clause = FOREIGN_FIELD.split(clause, maxsplit=1)[0]
        firm = FIRM.search(firm_clause)
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
        business = _business_name(firm_clause[firm.end() :], narrative=bool(firm["narrative"])) if firm else None
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
        if not business and (field := FIRM_LABEL.search(firm_clause)):
            business = _business_name(firm_clause[field.end() :], narrative=False)
        if not business and (title := re.search(rf"(?i:{OWNER_TITLE})[ \t]+", firm_clause)):
            legend = firm_clause[title.end() :].lstrip()
            if legend[:1].isupper() or legend[:1] in QUOTES:
                business = _business_name(legend, narrative=True)
        return {
            "imie_nazwisko": name,
            "krs": None,
            "nazwa": business,
            "nip": identifiers["nip"],
            "typ": "osoba_fizyczna",
        }
    return None
