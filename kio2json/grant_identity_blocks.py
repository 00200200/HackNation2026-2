"""Link a labelled sole-trader identity block (CEIDG-style card, letterhead) to the operative grant."""

import re
from itertools import pairwise

from .common import registry_ids, squash
from .grant_traders import FIRM_LABEL, FOREIGN_FIELD, PERSON_FIELD, _business_name, printed_firm
from .personal_names import compatible_names, nominative

FIELD_LINE = re.compile(r"^[ \t]*([^\W\d_][\w ./()-]{0,60}?)[ \t]*:[ \t]*(\S.*)$")
HEADER_LINE = re.compile(r"^[ \t]*[^\W\d_][\w ./()-]{0,60}:[ \t]*$")
NIP_LINE = re.compile(r"^[ \t]*NIP[ \t]*:?[ \t]*(?:PL[ \t]?)?(\d(?:[ \-]?\d){9})[ \t]*$")
FIRST_PERSON_GRANT = re.compile(r"(?i)^(?:udzielam|ustanawiam|upoważniam)\b")
COMPANY_FORM = re.compile(
    r"(?i)\b(?:sp\.\s?z\s?o\.\s?o|sp\.\s?k|sp\.\s?j|sp\.\s?p|s\.\s?c|S\.\s?A|spółk\w+|fundacj\w+|stowarzyszeni\w+)\b"
)


def _identity_blocks(text: str) -> list[dict]:
    """Groups of consecutive "label: value" rows that carry a person, a firm and a NIP."""
    groups, current, header = [], [], ""
    for line in [*text.splitlines(), ""]:
        if FIELD_LINE.match(line):
            current.append(line)
            continue
        if current:
            groups.append((header, current))
            current, header = [], ""
        header = line if HEADER_LINE.match(line) else ""
    found = []
    for header, rows in groups:
        if FOREIGN_FIELD.search(header) or any(FOREIGN_FIELD.search(row) for row in rows):
            continue
        block = "\n".join(rows)
        person = {squash(m[1]) for m in PERSON_FIELD.finditer(block)}
        firms = {
            printed_firm(_business_name(block[m.end() :], narrative=False)) for m in FIRM_LABEL.finditer(block)
        } - {None}
        ids = registry_ids(block)
        if len(person) == len(firms) == 1 and not ids["krs"] and ids["nip"]:
            found.append({"person": person.pop(), "firm": firms.pop(), "nip": ids["nip"]})
    return found


def _same_person(printed: str, name: str) -> bool:
    return printed == name or (len(printed.split()) == len(name.split()) and compatible_names(name, printed))


def recover_trader(text: str, grant: re.Match, offset: int, attorneys: list[str]) -> dict | None:
    """A grant without a named issuer can rest on the one identity card printed above it.

    `grant` matches in a suffix of `text` that starts at `offset`.
    """
    start = offset + grant.start()
    cards = _identity_blocks(text[:start])
    if len(cards) != 1:
        return None
    card = cards[0]
    lead = []
    for line in reversed(text[:start].splitlines()[-3:]):
        if FIELD_LINE.match(line):
            break
        lead.append(line)
    sentence = "\n".join(reversed(lead)) + text[start : start + 300]
    if not (FIRST_PERSON_GRANT.match(grant[0]) or card["nip"] in re.sub(r"\D", "", sentence)):
        return None
    if COMPANY_FORM.search(card["firm"]) or nominative(card["person"], "nom") != card["person"]:
        return None
    if any(_same_person(card["person"], a) for a in attorneys if a):
        return None
    return {
        "imie_nazwisko": card["person"],
        "krs": None,
        "nazwa": card["firm"],
        "nip": card["nip"],
        "typ": "osoba_fizyczna",
    }


def complete_trader(before: str, principal: dict) -> None:
    """Fill a missing firm or NIP from the identity card of the same proprietor; never overwrite."""
    name = principal["imie_nazwisko"]
    cards = [
        c
        for c in _identity_blocks(before)
        if _same_person(c["person"], name) and (not principal["nip"] or principal["nip"] == c["nip"])
    ]
    if len(cards) == 1 and not COMPANY_FORM.search(cards[0]["firm"]):
        principal["nazwa"] = principal["nazwa"] or cards[0]["firm"]
        principal["nip"] = principal["nip"] or cards[0]["nip"]
    if principal["nip"] or not principal["nazwa"]:
        return
    lines = [line.strip() for line in before.splitlines()]
    numbers = {
        re.sub(r"\D", "", m[1])
        for line, following in pairwise(lines)
        if line.casefold() == principal["nazwa"].casefold() and (m := NIP_LINE.match(following))
    }
    numbers.discard(None)
    if len(numbers) == 1:
        principal["nip"] = numbers.pop()
