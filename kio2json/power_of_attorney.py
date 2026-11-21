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


GRANT = re.compile(r"\b(?:udziela(?:m|my|ją)?|ustanawia(?:m|my|ją)?|upoważnia(?:m|my|ją)?)\b", re.IGNORECASE)
GRANTOR = re.compile(
    r"\b(?:mocodawc[ąa](?:\s+jest)?|działając\s+w\s+imieniu)\b|^wykonawcy wspólnie\b[^:]*\bkonsorcjum\)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
OTHER_ROLE = re.compile(
    r"\b(?:zamawiając(?:y|ym)(?:\s+jest)?|prowadzon\w+\s+przez|postępowanie\s+prowadzi)\b"
    r"|^[ \t]*(?!mocodawc|konsorcjum|KRS\b|NIP\b|REGON\b)[^\W\d_][\w /-]{0,60}(?: \([^():]*\))?:",
    re.IGNORECASE | re.MULTILINE,
)


def _principals(text: str) -> list[dict]:
    grant = GRANT.search(text)
    text = text[: grant.start()] if grant else text
    if not grant and not GRANTOR.search(text):
        return []
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
        previous_end = companies[index - 1].end() if index else 0
        context = text[previous_end : match.start()]
        # A new explicit subject takes precedence over an earlier proceeding clause.
        declarations = list(GRANTOR.finditer(context))
        if declarations:
            context = context[declarations[-1].end() :]
        if OTHER_ROLE.search(context) or OTHER_ROLE.match(match[1]):
            continue
        following = companies[index + 1] if index + 1 < len(companies) else None
        between = text[match.end() : following.start() if following else len(text)]
        details = OTHER_ROLE.split(between, maxsplit=1)[0]
        explicit = declarations or GRANTOR.search(match[1])
        if not explicit:
            if not grant:
                continue
            # The subject immediately precedes the grant. A further company must
            # either be a coordinated grantor or belong to a different role.
            if following and not (
                OTHER_ROLE.search(between)
                or OTHER_ROLE.match(following[1])
                or re.search(r"(?:\bi|\boraz|;\s*\d+\))\s*$", between)
            ):
                continue
        ids = registry_ids(details[:ID_WINDOW])
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
    # The appointment may be printed in a labelled table before the grant verb.
    # A later participant, proceeding or signature block cannot appoint anyone.
    appointment = []
    active = False
    for line in text.splitlines():
        if GRANT.search(line) or re.search(r"\bpełnomocni(?:k|cy)\b", line, re.IGNORECASE):
            active = True
        elif not re.match(r"^(?:pełnomocnictwa|PESEL|nr wpisu|(?:na )?listę)\b", line.strip(), re.IGNORECASE) and (
            OTHER_ROLE.match(line.strip()) or SIGNATURE_LINE_RE.search(line)
        ):
            active = False
        appointment.append(line if active else "|")
    text = "\n".join(appointment)
    matches = list(ATTORNEY_RE.finditer(text))
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pesel = re.search(r"PESEL:?\s*(\d{11})(?!\d)", text[match.end() : min(next_start, match.end() + 60)])
        name = squash(match.group(1))
        attorneys.setdefault(name, {"imie_nazwisko": name, "pesel": pesel.group(1) if pesel else None})
    return list(attorneys.values())


def _signers(text: str, principal_names: list[str], attorney_names: set[str], *, from_line: int = 0) -> list[list[str]]:
    """Attach each signature to its explicit heading, including the heading before the first rule."""
    signers = [[] for _ in principal_names]
    first = SIGNATURE_LINE_RE.search(text)
    if not first or not principal_names:
        return signers
    heading = re.compile(r"^(?:W imieniu|Za)\s+", re.IGNORECASE)
    # Before the first signature rule, only the immediately preceding heading belongs
    # to the signature area. Names or role qualifiers sometimes wrap onto the next line.
    prefix = text[: first.start()].rstrip().splitlines()
    start = next(
        (i for i in range(len(prefix) - 1, max(-1, len(prefix) - 4), -1) if heading.match(prefix[i].strip())),
        len(prefix),
    )
    lines = prefix[start:] + text[first.start() :].splitlines()
    # A mixed document can use earlier dotted lines as context for a native page.
    first_candidate = len(prefix) - start + max(0, from_line - text.count("\n", 0, first.start()))
    current = 0 if len(principal_names) == 1 else None
    for index, line in enumerate(lines):
        if heading.match(line.strip()):
            heading_text = line.strip()
            if index + 1 < len(lines) and not SIGNATURE_LINE_RE.search(lines[index + 1]):
                heading_text += " " + lines[index + 1].strip()
            named = [i for i, name in enumerate(principal_names) if name.casefold() in squash(heading_text).casefold()]
            current = named[0] if len(named) == 1 else None
            continue
        if re.match(r"^pełnomocnictwo przyjmuję", line, re.IGNORECASE):
            break
        if current is None or index < first_candidate:
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
    return _record(principals, attorneys, signers)


def _record(principals: list[dict], attorneys: list[dict], signers: list[list[str]]) -> dict:
    return {
        "mocodawca": [
            {"data": principal, "podpisujacy": [{"imie_nazwisko": name} for name in names]}
            for principal, names in zip(principals, signers)
        ],
        "pelnomocnicy": attorneys,
    }
