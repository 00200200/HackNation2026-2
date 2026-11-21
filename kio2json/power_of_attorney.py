"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

from .common import ATTORNEY_RE, PERSON, UPPER, registry_ids, squash

LEGAL_FORM = (
    r"(?i:sp\.\s?z\s?o\.\s?o\.(?:\s?sp\.\s?k\.)?|S\.\s?A\.|sp\.\s?k\.|sp\.\s?j\.|sp\.\s?p\.|s\.c\."
    r"|spółka\s+z\s+ograniczoną\s+odpowiedzialnością|spółka\s+akcyjna)"
)
# Words need two characters so a letter-spaced heading (P E Ł N O ...) is not read as a name.
COMPANY_RE = re.compile(rf"((?:[{UPPER}][\w\-&]+\s+){{1,6}}?{LEGAL_FORM})")
# Label and heading words that directly precede a company name in the known layouts.
LABEL_WORDS = {
    "mocodawca",
    "mocodawcą",
    "pełnomocnik",
    "pełnomocnictwo",
    "procesowe",
    "za",
    "konsorcjum",
    "wykonawca",
    "lider",
    "partner",
}
SOLE_TRADER_RE = re.compile(r"prowadząc\w+ działalność gospodarczą pod firmą\s+(.+?),\s", re.DOTALL)
ROLE_WORDS_RE = re.compile(
    r"\b(?:Prezes|Wiceprezes|Członek|Zarządu|Zarząd|Prokurent|Dyrektor|Generalny|Wspólnik|Właściciel|"
    r"Komplementariusz|Mocodawca|Pełnomocnik\w*|Pełnomocnictwo|Podpis|Za|W)\b"
)
SIGNATURE_LINE_RE = re.compile(r"\.{10,}")
ID_WINDOW = 250  # characters after a company name in which its KRS/NIP must appear


def _company_name(raw: str) -> str:
    words = squash(raw).split(" ")
    while words and words[0].casefold().strip(":") in LABEL_WORDS:
        words.pop(0)
    return " ".join(words)


def _principals(text: str) -> list[dict]:
    sole_trader = SOLE_TRADER_RE.search(text)
    if sole_trader:
        person = re.search(rf"podpisan\w*\s+({PERSON})", text)
        ids = registry_ids(text[sole_trader.end() :])
        return [
            {
                "imie_nazwisko": squash(person.group(1)) if person else None,
                "krs": None,
                "nazwa": squash(sole_trader.group(1)),
                "nip": ids["nip"],
                "typ": "osoba_fizyczna",
            }
        ]

    principals = {}
    companies = list(COMPANY_RE.finditer(text))
    for index, match in enumerate(companies):
        window_end = companies[index + 1].start() if index + 1 < len(companies) else len(text)
        ids = registry_ids(text[match.end() : min(window_end, match.end() + ID_WINDOW)])
        if not (ids["krs"] or ids["nip"]):
            continue  # a company named without registry numbers is not the principal
        name = _company_name(match.group(1))
        principals.setdefault(
            name,
            {
                "imie_nazwisko": None,
                "krs": ids["krs"],
                "nazwa": name,
                "nip": ids["nip"],
                "typ": "osoba_prawna",
            },
        )
    return list(principals.values())


def _attorneys(text: str) -> list[dict]:
    attorneys = {}
    matches = list(ATTORNEY_RE.finditer(text))
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pesel = re.search(r"PESEL:?\s*(\d{11})(?!\d)", text[match.end() : min(next_start, match.end() + 60)])
        name = squash(match.group(1))
        attorneys.setdefault(name, {"imie_nazwisko": name, "pesel": pesel.group(1) if pesel else None})
    return list(attorneys.values())


def _signers(text: str, principal_names: list[str], attorney_names: set[str]) -> list[list[str]]:
    """Names under the signature lines, grouped by the principal named above them
    ('W imieniu X:', 'Za X'). Without such a marker they belong to the first principal."""
    signers = [[] for _ in principal_names]
    signature_start = SIGNATURE_LINE_RE.search(text)
    if not signature_start or not principal_names:
        return signers
    zone = text[signature_start.start() :]
    for index, name in enumerate(principal_names):
        zone = re.sub(r"\s+".join(map(re.escape, name.split(" "))), f"\n@@{index}@@\n", zone)

    current = 0
    for line in zone.splitlines():
        marker = re.fullmatch(r"@@(\d+)@@", line.strip())
        if marker:
            current = int(marker.group(1))
            continue
        line = ROLE_WORDS_RE.sub("|", ATTORNEY_RE.sub("|", line))
        for person in re.findall(PERSON, line):
            person = squash(person)
            if person not in attorney_names and person not in signers[current]:
                signers[current].append(person)
    return signers


def extract(text: str) -> dict:
    principals = _principals(text)
    attorneys = _attorneys(text)
    signers = _signers(text, [p["nazwa"] for p in principals], {a["imie_nazwisko"] for a in attorneys})
    return {
        "mocodawca": [
            {"data": principal, "podpisujacy": [{"imie_nazwisko": name} for name in names]}
            for principal, names in zip(principals, signers)
        ],
        "pelnomocnicy": attorneys,
    }
