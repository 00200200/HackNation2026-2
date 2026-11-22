"""Identify a sole proprietor from the grantor's declaration or identity card."""

import re

from .common import PERSON, registry_ids, squash
from .personal_names import nominative

UNDERSIGNED = r"(?:ja,?\s+(?:niżej\s+)?|niżej\s+)podpisan[ay](?:/[ay])?"
ISSUER = re.compile(
    r"\b(?:(?P<genitive>działając\s+w\s+imieniu)|mocodawc[ąa](?:\s+jest)?|wykonawca"
    rf"|{UNDERSIGNED}|ja)\b"
    r"[ \t,:–—-]*",
    re.IGNORECASE,
)
TRADING = re.compile(
    r"\b(?:CEIDG|imię i nazwisko przedsiębiorcy|jednoosobow\w*\s+działalnoś\w*|prowadz\w*(?:/[ay])?\s+(?:jednoosobow\w*\s+)?"
    r"działalność\s+gospodarczą)",
    re.IGNORECASE,
)
PERSON_FIELD = re.compile(
    rf"(?im:^\s*(?:imię i nazwisko(?: przedsiębiorcy)?|właściciel(?:ka)?)\s*:\s*)({PERSON})(?=[,;\n]|$)"
)
FIRM = re.compile(r"\bpod\s+(?:firmą|nazwą)\s*:?\s*|^[ \t]*(?:firma|nazwa firmy)\s*:\s*", re.IGNORECASE | re.MULTILINE)
END_NAME = re.compile(
    r"[,;\n]|\s+[–—]\s+|\s+\b(?:NIP|REGON|CEIDG|zamieszkał\w*|z\s+siedzibą|wpisan\w*)\b", re.IGNORECASE
)
OTHER_PARTY = re.compile(
    r"\b(?:zamawiając\w*|pełnomocni(?:k|cy|ka)|odbiorc\w*|uczestnik\w*|świadek|świadkowie)\s*:"
    r"|^[ \t]*(?:pełnomocni(?:k|cy)|zamawiający|świadek|świadkowie)\b",
    re.IGNORECASE | re.MULTILINE,
)


def sole_trader(declaration: str, company_pattern: re.Pattern) -> dict | None:
    """Require both the identity of a natural person and local evidence of their business."""
    evidence = TRADING.search(declaration)
    if not evidence:
        return None
    slots = [(m.end(), bool(m["genitive"])) for m in ISSUER.finditer(declaration)]
    if not slots and not OTHER_PARTY.search(declaration, 0, evidence.start()):
        # An unlabelled nominative subject can introduce the trading declaration.
        bare = re.search(rf"(?m)^({PERSON})[ ,]+(?i:wpisan|prowadzą|wykonują)", declaration)
        if bare:
            slots.append((bare.start(), False))
    for start, genitive in slots:
        # A company's officer may also own a business. Require the trading
        # evidence to belong to the same person in the same party block.
        clause = OTHER_PARTY.split(declaration[start:].lstrip(), maxsplit=1)[0]
        if not TRADING.search(clause) or ISSUER.search(clause) or company_pattern.search(clause):
            continue
        identity = END_NAME.split(clause, maxsplit=1)[0].strip(" :")
        identity = TRADING.split(identity, maxsplit=1)[0].strip()
        if field := PERSON_FIELD.search(clause):
            identity = field[1]
        person = re.fullmatch(PERSON, identity)
        firm = FIRM.search(clause)
        if person:
            name = squash(person[0])
            if genitive and not field:
                name = nominative(name, "gen")
                if name is None:
                    continue
            business = None
        else:
            # A registered business name may put the proprietor first or last.
            # Use only an independently recognizable given name/surname pair.
            words = identity.split()
            if len(words) < 3:
                continue
            edges = {" ".join(words[:2]), " ".join(words[-2:])}
            people = {edge for edge in edges if nominative(edge, "nom") == edge}
            if len(people) != 1:
                continue
            name = people.pop()
            business = identity
        if firm:
            raw = END_NAME.split(clause[firm.end() :], maxsplit=1)[0]
            business = squash(raw).strip(' „”"«»') or business
        return {
            "imie_nazwisko": name,
            "krs": None,
            "nazwa": business,
            "nip": registry_ids(clause)["nip"],
            "typ": "osoba_fizyczna",
        }
    return None
