"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

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
