"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

from stdnum.pl import nip

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


def _company_data(name: str, details: str) -> dict:
    ids = registry_ids(re.sub(r"\bKRŚ\b", "KRS", details))
    long_krs = re.search(r"(?is)Rejestru Sądowego.{0,190}?pod numerem\s+(\d{10})(?!\d)", details)
    return {
        "imie_nazwisko": None,
        "krs": ids["krs"] or (long_krs[1] if long_krs else None),
        "nazwa": name,
        "nip": ids["nip"],
        "typ": "osoba_prawna",
    }


def _declared_officers(text: str) -> list[tuple[dict, str]]:
    grant = GRANT.search(text)
    if not grant:
        return []
    declaration = re.search(r"(?i)\b(?:my\s+)?niżej podpisani\s*:", text[: grant.start()])
    if not declaration:
        return []
    rows = re.split(r"(?m)^\s*\d+[.)]\s+", text[declaration.end() : grant.start()])[1:]
    officers = []
    for row in rows:
        officer = re.match(rf"({PERSON})\s*[-–—,]\s*(?i:{SIGNER_ROLE_RE.pattern})\s+", row)
        company = COMPANY_RE.match(row, officer.end()) if officer else None
        if company:
            officers.append((_company_data(squash(company[1]), row[company.end() :]), squash(officer[1])))
    return officers


def _issuer_identifiers(text: str, principal: dict) -> None:
    # Letterheads and address footers can carry the IDs omitted by the grant.
    # Connect one bounded block to the grant by its KRS or the same company name.
    name = re.sub(LEGAL_FORM + r"$", "", principal["nazwa"]).strip().casefold()
    lines = text.splitlines()
    candidates = set()
    for i, line in enumerate(lines):
        candidate = registry_ids(line)["nip"]
        if not candidate or not nip.is_valid(candidate):
            continue
        block = " ".join(lines[max(0, i - 2) : i + 3])
        if (principal["krs"] and registry_ids(block)["krs"] == principal["krs"]) or (
            name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", block.casefold())
        ):
            candidates.add(candidate)
    if len(candidates) == 1:
        principal["nip"] = candidates.pop()


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
        # A court maintaining the registry is part of this company's identity clause.
        between = re.sub(r"(?i)(Rejestru Sądowego)\s+prowadzon\w+ przez Sąd", r"\1, Sąd", between)
        between = re.sub(r"(?i)(Rejestru Sądowego\s+pod numerem)\s+KR[SŚ]\s*:", r"\1", between)
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
        name = _company_name(match.group(1))
        principals.setdefault(name, _company_data(name, details[: ID_WINDOW * 2]))
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
    titled = rf"(?i:adw\.|r\.\s?pr\.|adwokat\w*|radc\w+\s+prawn\w+)\s+({PERSON})"
    plain = (
        rf"(?i:{GRANT.pattern}\s*(?:niniejszym\s+)?(?:pełnomocnictwa\s*)?[:–-]?\s*(?:panią?|panu|pana)?\s*)"
        rf"({PERSON})(?=\s*(?:[.,(;]|$|(?i:numer PESEL|PESEL|pełnomocnictwa|do\b|legitymuj)))"
    )
    labelled = rf"(?im:^\s*pełnomocnik\s*:\s*)({PERSON})"
    matches = sorted(
        ((m, kind) for kind, pattern in enumerate((titled, plain, labelled)) for m in re.finditer(pattern, text)),
        key=lambda item: item[0].start(),
    )
    ids = {}
    for index, (match, kind) in enumerate(matches):
        next_start = matches[index + 1][0].start() if index + 1 < len(matches) else len(text)
        pesel = re.search(r"(?i:PESEL):?\s*(\d{11})(?!\d)", text[match.end() : min(next_start, match.end() + 60)])
        name = squash(match[1])
        number = pesel[1] if pesel else None
        if number and number in ids:
            if kind != 2:
                continue
            attorneys.pop(ids[number], None)
        if number:
            ids[number] = name
        attorneys.setdefault(name, {"imie_nazwisko": name, "pesel": number})
    return list(attorneys.values())


SIGNER_ROLE_RE = re.compile(
    r"(?:Prezes|Wiceprezes|Członek|Prokurent|Dyrektor|Wspólnik|Właściciel|Komplementariusz)"
    r"(?: (?:Zarządu|Generalny))?",
    re.IGNORECASE,
)


def _undotted_signers(text: str, principals: list[str], attorneys: set[str]) -> list[list[str]]:
    """Read the trailing signature block. A title or an explicit grantor heading must support the names."""
    names = [[] for _ in principals]
    signature = []
    for raw in reversed(text.splitlines()):
        line = raw.strip(" :.")
        if not line or line.casefold() == "miejsce na pieczęć firmową":
            continue
        if line.casefold().startswith(("za ", "w imieniu ")):
            declared = re.sub(r"^(?:za|w imieniu) ", "", line.casefold())
            matches = [i for i, name in enumerate(principals) if declared == name.casefold().rstrip(".")]
            signature.append(("principal", matches[0] if len(matches) == 1 else None))
        elif re.fullmatch(
            r"(?:Mocodawca|Podpis(?: mocodawcy)?)(?::?\s+Pełnomocnictwo przyjmuję)?", line, re.IGNORECASE
        ):
            signature.append(("heading", None))
        elif re.fullmatch(r"Pełnomocnictwo przyjmuję", line, re.IGNORECASE):
            signature.append(("acceptance", None))
        elif SIGNER_ROLE_RE.sub("", line).strip() == "":
            signature.append(("role", None))
        else:
            line = ATTORNEY_RE.sub("", line).strip()
            if not line:
                continue
            if not re.fullmatch(rf"{PERSON}(?: +{PERSON})*", line):
                break
            signature.append(("names", re.findall(PERSON, line)))
    current = 0 if len(principals) == 1 else None
    pending = []
    headed = False
    for kind, value in reversed(signature):
        if kind in ("principal", "heading", "acceptance"):
            pending.clear()
            headed = kind != "acceptance"
            if kind == "principal":
                current = value
            elif kind == "acceptance":
                current = None
        elif kind == "names":
            pending.extend(value)
        if current is not None and pending and (headed or kind == "role"):
            for person in pending:
                if person not in attorneys and person not in names[current]:
                    names[current].append(person)
            pending.clear()
    return names


def _signers(text: str, principal_names: list[str], attorney_names: set[str]) -> list[list[str]]:
    """Attach each signature to its explicit heading, including the heading before the first rule."""
    signers = [[] for _ in principal_names]
    first = SIGNATURE_LINE_RE.search(text)
    if not first:
        return _undotted_signers(text, principal_names, attorney_names)
    if not principal_names:
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
        if current is None or index < len(prefix) - start:
            continue
        line = ROLE_WORDS_RE.sub("|", ATTORNEY_RE.sub("|", line))
        for person in re.findall(PERSON, line):
            person = squash(person)
            if person not in attorney_names and person not in signers[current]:
                signers[current].append(person)
    return signers


STAMP = re.compile(r"(?i)^(?:podpis(?:ano|any|ana) (?:elektronicznie )?przez|signed (?:electronically )?by)\s*[:：]\s*")
FOOTER = re.compile(r"(?i)(?:^tel[.:]|^https?://|\bul\.\s|\b(?:NIP|REGON)\s*[:\d]|\w@\w)")


def _stamp_signers(text: str, principal: str, attorneys: set[str]) -> list[str | None]:
    names = []
    lines = text.splitlines()
    core = re.sub(LEGAL_FORM + r"$", "", principal).strip().casefold()
    headed = False
    for i, raw in enumerate(lines):
        line = raw.strip(" |")
        if re.match(r"(?i)^pełnomocnictwo przyjmuję", line):
            break
        if FOOTER.search(line):
            headed = False
        if re.match(r"(?i)^(?:za|w imieniu) ", line):
            headed = bool(core and re.match(rf"(?i)^(?:za|w imieniu) {re.escape(core)}(?:\s|$)", line))
        if re.fullmatch(r"(?i)podpis(?: mocodawcy)?\s*:\s*\[?nieczytelny\]?", line):
            names.append(None)
        marker = STAMP.match(line)
        if not marker and not (headed and SIGNER_ROLE_RE.fullmatch(line)):
            continue
        following = ([line[marker.end() :]] if marker else []) + lines[i + 1 : i + 4]
        for candidate in following:
            candidate = candidate.strip(" |")
            if FOOTER.search(candidate) or STAMP.match(candidate) or SIGNER_ROLE_RE.fullmatch(candidate):
                break
            if re.fullmatch(PERSON, candidate):
                if candidate not in attorneys and candidate not in names:
                    names.append(candidate)
                break
    return names


def extract(text: str) -> dict:
    officers = _declared_officers(text)
    principals = [p for p, _ in officers] if officers else _principals(text)
    attorneys = _attorneys(text)
    attorney_names = {a["imie_nazwisko"] for a in attorneys}
    signers = _signers(text, [p["nazwa"] for p in principals], attorney_names)
    if officers:
        for (_, name), people in zip(officers, signers):
            if name not in people:
                people.append(name)
    elif len(principals) == 1:
        principal = principals[0]
        if principal["typ"] == "osoba_prawna" and principal["nip"] is None:
            _issuer_identifiers(text, principal)
        for name in _stamp_signers(text, principal["nazwa"], attorney_names):
            if name is None or name not in signers[0]:
                signers[0].append(name)
    return {
        "mocodawca": [
            {"data": principal, "podpisujacy": [{"imie_nazwisko": name} for name in names]}
            for principal, names in zip(principals, signers)
        ],
        "pelnomocnicy": attorneys,
    }
