"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

from stdnum.pl import nip

from .common import ATTORNEY_RE, DATE, PERSON, UPPER, registry_ids, squash

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
SIGNATURE_LINE_RE = re.compile(r"\.{10,}|_{5,}|[─━—]{4,}")
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


SIGNATURE_HEADING = re.compile(
    r"(?:Mocodawca|Podpis(?: mocodawcy)?)(?::?\s+Pełnomocnictwo przyjmuję)?:?", re.IGNORECASE
)
NAMED_SIGNATURE = re.compile(r"^(?:W imieniu|Za)\s+", re.IGNORECASE)


# The operative clause may finish on wrapped lines or a dated closing.
LIST_MARKER = re.compile(r"^(?:(?:[a-z]|[0-9]{1,2})[).,]|[-*•.»«–—+]|e) +", re.IGNORECASE)
GRANT_CLAUSE = re.compile(
    r"(?:(?:(?:w tym|oraz) )?do )?"
    r"(?:zastępowania|składania|udzielania|wniesienia|cofnięcia|odbioru|zasięgania|reprezentowania)\b"
    r"|opłata skarbowa od pełnomocnictwa",
    re.IGNORECASE,
)
DATELINE = re.compile(rf"(?:Data\s+|[{UPPER}][\w -]+,\s*)?{DATE}", re.IGNORECASE)
STAMP_PLACE = re.compile(r"miejsce na pieczęć firmową[ .]*", re.IGNORECASE)


def _directly_after_grant(lines: list[str], index: int, principals: list[str]) -> bool:
    if len(principals) != 1:
        return False
    if index and re.fullmatch(r"Z poważaniem,?", lines[index - 1], re.IGNORECASE):
        index -= 1
    if index and DATELINE.fullmatch(lines[index - 1]):
        index -= 1
    if not index:
        return False
    # Rejoin the final sentence before testing its opening. A wrapped contact
    # heading can put a grant-related noun at the beginning of a physical line.
    start = index - 1
    while start and not LIST_MARKER.match(lines[start]):
        previous = lines[start - 1]
        # A lawyer's title, a case reference, and a quoted procurement name
        # commonly wrap in the middle of the operative sentence.
        continuation = (
            re.search(r"\b(?:adw|pr)\.$", previous, re.IGNORECASE)
            or (previous.casefold().endswith("postępowania:") and re.match(r"[A-Z0-9./-]*\d", lines[start]))
            or (lines[start].startswith("„") and previous.casefold().endswith("postępowaniu"))
            or (
                re.match(r"\d|(?:NIP|KRS|REGON)\b", lines[start], re.IGNORECASE)
                and re.search(r"(?:\bNIP|\bKRS|\d,)$", previous, re.IGNORECASE)
            )
        )
        if not continuation:
            if previous.endswith((".", ":", ";")):
                break
            if not lines[start][0].islower() and not re.search(r"\b(?:do|w|i|z|oraz|przez)$", previous, re.IGNORECASE):
                break
        start -= 1
    sentence = " ".join(lines[start:index])
    action = GRANT.search(sentence)
    if (
        action
        and (action.start() == 0 or GRANTOR.match(sentence) or sentence.casefold().startswith(principals[0].casefold()))
        and re.match(r"\s+(?:pełnomocni\w*|do|reprezentowan\w*)\b", sentence[action.end() :], re.IGNORECASE)
    ):
        return True
    if (
        start
        and lines[start - 1].endswith(":")
        and not re.search(
            r"zakres pełnomocnictwa|pełnomocnictwo obejmuje|(?:w szczególności|pełnomocnikom|umocowanie) do:$",
            lines[start - 1],
            re.IGNORECASE,
        )
    ):
        return False
    return sentence.endswith(".") and bool(GRANT_CLAUSE.match(LIST_MARKER.sub("", sentence)))


def _signature_owner(heading: str, following: str, principals: list[str]) -> int | None:
    heading = NAMED_SIGNATURE.sub("", heading)
    candidates = [heading, squash(heading + " " + following)]
    owners = []
    for i, name in enumerate(principals):
        company = re.escape(name.rstrip(".")) + r"\.?"
        pattern = rf"{company}(?: +(?:Za|W imieniu) +{company})?(?:\s*(?:\([^()]*\)|[–-] .+))?:?"
        if any(re.fullmatch(pattern, candidate, re.IGNORECASE) for candidate in candidates):
            owners.append(i)
    return owners[0] if len(owners) == 1 else None


def _signers(text: str, principals: list[str], attorneys: set[str]) -> list[list[str]]:
    signers = [[] for _ in principals]
    single = 0 if len(principals) == 1 else None
    current = single
    expect_name = False
    signed = False
    lines = [clean for raw in text.splitlines() if (clean := STAMP_PLACE.sub("", raw).strip())]
    for index, line in enumerate(lines):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if NAMED_SIGNATURE.match(line):
            current = _signature_owner(line, following, principals)
            expect_name, signed = True, False
            continue
        if SIGNATURE_HEADING.fullmatch(line):
            current, expect_name, signed = single, True, False
            continue
        if re.match(r"^Pełnomocnictwo przyjmuję\b", line, re.IGNORECASE):
            break
        remaining = ATTORNEY_RE.sub("", line).strip()
        if SIGNATURE_LINE_RE.search(remaining) and not SIGNATURE_LINE_RE.sub("", remaining).strip(" ."):
            # A rule on an unrelated form field belongs to that field. A new
            # rule in a signature block can introduce a second signer.
            if not (expect_name or signed):
                current = single if _directly_after_grant(lines, index, principals) else None
            expect_name, signed = True, False
            continue
        if re.fullmatch(r"[. ]+", line) or SIGNER_ROLE_RE.sub("", line).strip() == "":
            continue
        # A wrapped principal or its parenthesized consortium qualifier.
        if (
            expect_name
            and index
            and NAMED_SIGNATURE.match(lines[index - 1])
            and SIGNATURE_LINE_RE.search(following)
            and _signature_owner(lines[index - 1], line, principals) is not None
        ):
            continue

        title = SIGNER_ROLE_RE.search(remaining)
        inline_role = title and not remaining[title.end() :].strip(" )")
        if inline_role:
            remaining = remaining[: title.start()].rstrip(" ,(–—-")
        if re.fullmatch(rf"{PERSON}(?: +{PERSON})*", remaining):
            if not expect_name:
                role = inline_role or (following and SIGNER_ROLE_RE.sub("", following).strip() == "")
                previous_role = signed and SIGNER_ROLE_RE.sub("", lines[index - 1]).strip() == ""
                if not (previous_role and role):
                    current = single if role and _directly_after_grant(lines, index, principals) else None
            if current is not None:
                for person in re.findall(PERSON, remaining):
                    if person not in attorneys and person not in signers[current]:
                        signers[current].append(person)
                expect_name, signed = False, True
                continue
        current, expect_name, signed = single, False, False
    return signers


STAMP = re.compile(r"(?i)^(?:podpis(?:ano|any|ana) (?:elektronicznie )?przez|signed (?:electronically )?by)\s*[:：]\s*")
FOOTER = re.compile(r"(?i)(?:^tel[.:]|^https?://|\bul\.\s|\b(?:NIP|REGON)\s*[:\d]|\w@\w)")


def _add_stamp_signers(text: str, principals: list[str], attorneys: set[str], signers: list[list]) -> None:
    single = 0 if len(principals) == 1 else None
    owner = single
    headed = False
    cores = [re.sub(LEGAL_FORM + r"$", "", name).strip().casefold() for name in principals]
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.lstrip(" |.").rstrip(" |")
        if re.match(r"(?i)^pełnomocnictwo przyjmuję", line):
            break
        if SIGNATURE_HEADING.fullmatch(line):
            owner, headed = single, True
            continue
        if NAMED_SIGNATURE.match(line):
            name = NAMED_SIGNATURE.sub("", line).strip(" :")
            core = re.sub(LEGAL_FORM + r"$", "", name).strip().casefold()
            owner = cores.index(core) if cores.count(core) == 1 else None
            headed = owner is not None
            continue
        if re.fullmatch(r"(?i)podpis(?: mocodawcy)?\s*:\s*\[?nieczytelny\]?", line):
            if owner is not None:
                signers[owner].append(None)
            continue
        marker = STAMP.match(line)
        if not marker and (FOOTER.search(line) or OTHER_ROLE.match(line)):
            owner, headed = None, False
        if owner is None or not (marker or (headed and SIGNER_ROLE_RE.fullmatch(line))):
            continue
        if not marker and i and re.fullmatch(PERSON, lines[i - 1].strip()):
            continue
        following = ([line[marker.end() :]] if marker else []) + lines[i + 1 : i + 4]
        for candidate in following:
            candidate = candidate.strip(" |")
            if (
                NAMED_SIGNATURE.match(candidate)
                or SIGNATURE_LINE_RE.search(candidate)
                or FOOTER.search(candidate)
                or OTHER_ROLE.match(candidate)
                or STAMP.match(candidate)
                or SIGNER_ROLE_RE.fullmatch(candidate)
            ):
                break
            if re.fullmatch(PERSON, candidate):
                if candidate not in attorneys and candidate not in signers[owner]:
                    signers[owner].append(candidate)
                break


def extract(text: str) -> dict:
    officers = _declared_officers(text)
    issuers = {}
    for data, _ in officers:
        issuer = issuers.setdefault(data["nazwa"], data.copy())
        for key in ("krs", "nip"):
            if issuer[key] is None:
                issuer[key] = data[key]
    principals = list(issuers.values()) if officers else _principals(text)
    attorneys = _attorneys(text)
    attorney_names = {a["imie_nazwisko"] for a in attorneys}
    principal_names = [p["nazwa"] for p in principals]
    signers = _signers(text, principal_names, attorney_names)
    for principal, name in officers:
        people = signers[principal_names.index(principal["nazwa"])]
        if name not in people:
            people.append(name)
    if len(principals) == 1:
        principal = principals[0]
        if principal["typ"] == "osoba_prawna" and principal["nip"] is None:
            _issuer_identifiers(text, principal)
    _add_stamp_signers(text, principal_names, attorney_names, signers)
    return {
        "mocodawca": [
            {"data": principal, "podpisujacy": [{"imie_nazwisko": name} for name in names]}
            for principal, names in zip(principals, signers)
        ],
        "pelnomocnicy": attorneys,
    }
