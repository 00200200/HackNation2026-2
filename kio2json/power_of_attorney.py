"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

from rapidfuzz.distance import Levenshtein
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


REGISTER = re.compile(r"\brejestr\w*\s+sądow\w*\b", re.IGNORECASE)
ENTRY_NUMBER = re.compile(
    r"\b(?:numer(?:em)?|nr\.?)\s*:?\s*(?:[A-ZĄĆĘŁŃÓŚŹŻ]{2,4}\s*:\s*)?(\d{10})(?!\d)", re.IGNORECASE
)
REGISTRY_END = re.compile(r"\b(?:NIP|REGON|PESEL)\b|[.;](?:\s|$)", re.IGNORECASE)


def normalize_registry_labels(text: str) -> str:
    """Repair a three-letter register label only on OCR text with a labelled ten-digit value."""

    def normalize(match: re.Match) -> str:
        token = match[0]
        return "KRS" if Levenshtein.distance(token, "KRS", score_cutoff=1) <= 1 else token

    return re.sub(r"\b[A-ZĄĆĘŁŃÓŚŹŻ]{3}\b(?=\s*:\s*\d{10}(?!\d))", normalize, text)


def _identity_clause(details: str) -> str:
    for boundary in OTHER_ROLE.finditer(details):
        # A court can maintain the register named earlier in the same identity clause.
        if REGISTER.search(details, 0, boundary.end()) and re.match(
            r"\s+sąd\w*\b", details[boundary.end() :], re.IGNORECASE
        ):
            continue
        if REGISTER.search(boundary[0]):
            continue
        return details[: boundary.start()]
    return details


def _company_data(name: str, details: str) -> dict:
    clause = _identity_clause(details)
    ids = registry_ids(clause[: ID_WINDOW * 2])
    if not ids["krs"]:
        for register in REGISTER.finditer(clause):
            section = REGISTRY_END.split(clause[register.end() :], maxsplit=1)[0]
            number = ENTRY_NUMBER.search(section)
            if number:
                ids["krs"] = number[1]
                break
    return {
        "imie_nazwisko": None,
        "krs": ids["krs"],
        "nazwa": name,
        "nip": ids["nip"],
        "typ": "osoba_prawna",
    }


ENTRY_BOUNDARY = re.compile(
    r"(?:^|[;\n])[ \t]*(?:\(?\d+[.)]|[•*–—-])\s+|\n[ \t]*\n|(?=^\s*Mocodawc[ąa]\s*:)", re.MULTILINE | re.IGNORECASE
)


def _declared_officers(text: str) -> list[tuple[dict, str]]:
    grant = GRANT.search(text)
    if not grant:
        return []
    officers = []
    for entry in ENTRY_BOUNDARY.split(text[: grant.start()]):
        # An officer title is often capitalized and otherwise looks like part of a company name.
        without_roles = SIGNER_ROLE_RE.sub(lambda m: "|" * len(m[0]), entry)
        companies = list(COMPANY_RE.finditer(without_roles))
        if len(companies) != 1:
            continue
        company = companies[0]
        # Remove the company from the search so a capitalized trade name cannot become the officer.
        people = entry[: company.start()] + "|" + entry[company.end() :]
        context = entry[: company.start()]
        declarations = list(GRANTOR.finditer(context))
        if declarations:
            context = context[declarations[-1].end() :]
        if OTHER_ROLE.search(context):
            continue
        for role in SIGNER_ROLE_RE.finditer(people):
            left = re.search(rf"({PERSON})[ \t]*[-–—,(]\s*$", people[: role.start()])
            right = re.match(rf"\s*[-–—,:]?\s*({PERSON})\b", people[role.end() :])
            if bool(left) == bool(right):
                continue
            if role.start() > company.start():
                gap = people[company.start() + 1 : left.start() if left else role.start()]
            else:
                gap = people[role.end() + (right.end() if right else 0) : company.start()]
            if re.search(r"[!?;]|\.\s+[A-ZĄĆĘŁŃÓŚŹŻ]", gap) or OTHER_ROLE.search(gap):
                continue
            person = squash((left or right)[1])
            officers.append((_company_data(_company_name(company[1]), entry[company.end() :]), person))
    return officers


def _issuer_identifiers(text: str, principal: dict) -> None:
    # A tax number must share an identity block with this company's name or register number.
    def core(name: str) -> str:
        return re.sub(LEGAL_FORM + r"$", "", name).strip().casefold()

    company = core(principal["nazwa"])
    name_pattern = re.compile(rf"(?<!\w){re.escape(company)}(?!\w)", re.IGNORECASE)
    krs = principal["krs"]
    lines = text.splitlines()
    candidates = set()
    pending = set()
    owner = None
    anchor = 0
    for i, line in enumerate(lines):
        ids = registry_ids(line)
        names = {core(_company_name(m[1])) for m in COMPANY_RE.finditer(line)}
        foreign = OTHER_ROLE.search(line) or names - {company} or (krs and ids["krs"] and ids["krs"] != krs)
        registry_line = any(ids.values()) and not names and not foreign
        if not registry_line:
            pending.clear()
        if foreign:
            owner = False
        elif (company and name_pattern.search(line)) or (krs and ids["krs"] == krs):
            owner, anchor = True, i
            # A register block may print its tax number before the confirmed KRS.
            if krs and ids["krs"] == krs:
                candidates.update(pending)
        elif not line.strip():
            owner = None
        number = ids["nip"]
        if not number or not nip.is_valid(number) or owner is False:
            continue
        if owner and i - anchor <= 2:
            candidates.add(number)
        elif registry_line:
            pending.add(number)
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
        principals.setdefault(name, _company_data(name, between))
    return list(principals.values())


def _attorneys(text: str) -> list[dict]:
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
    mentions = []
    for index, (match, kind) in enumerate(matches):
        next_start = matches[index + 1][0].start() if index + 1 < len(matches) else len(text)
        pesel = re.search(r"(?i:PESEL):?\s*(\d{11})(?!\d)", text[match.end() : min(next_start, match.end() + 60)])
        mentions.append((squash(match[1]), pesel[1] if pesel else None, kind == 2))

    labelled = {(name, number) for name, number, is_label in mentions if is_label}
    resolved = []
    for name, number, is_label in mentions:
        if not is_label:
            candidates = [
                (label, pesel)
                for label, pesel in labelled
                if (pesel and number == pesel) or ((not number or not pesel) and _compatible_names(name, label))
            ]
            if len(candidates) == 1:
                name, labelled_id = candidates[0]
                number = number or labelled_id
        resolved.append((name, number))
    # Two people can share a name. A missing identifier can join only one known identity.
    known = {}
    for name, number in resolved:
        if number:
            known.setdefault(name, set()).add(number)
    people = {}
    for name, number in resolved:
        ids = known.get(name, ())
        if number is None and len(ids) == 1:
            number = next(iter(ids))
        people[name, number] = {"imie_nazwisko": name, "pesel": number}
    return list(people.values())


def _compatible_names(printed: str, labelled: str) -> bool:
    """Check inflection only against an independently printed nominative name."""
    for inflected, nominal in zip(printed.casefold().split(), labelled.casefold().split(), strict=True):
        if inflected == nominal:
            continue
        if nominal.endswith("a"):
            forms = {nominal[:-1] + ending for ending in ("ą", "ę", "ej", "ie", "i", "y")}
            for ending, replacement in (
                ("da", "dzie"),
                ("ta", "cie"),
                ("ka", "ce"),
                ("ga", "dze"),
                ("ra", "rze"),
                ("ła", "le"),
            ):
                if nominal.endswith(ending):
                    forms.add(nominal[: -len(ending)] + replacement)
        elif nominal.endswith(("i", "y")):
            forms = {nominal[:-1] + ending for ending in ("ego", "emu", "iego", "iemu")}
        else:
            forms = {nominal + ending for ending in ("a", "owi", "u")}
        if inflected not in forms:
            return False
    return True


NOTARIAL_HEADING = re.compile(r"(?im)^\s*akt\s+notarialny\s*$")
SIGNED_DEED = re.compile(
    r"(?i)(?<!nie )\b(?:podpisano|podpisali|podpisały|podpisał[ao]?|złożono podpisy)\b(?! przez\b)"
)


# Initials, professional titles and company abbreviations can precede a wrapped name.
DEED_CLAUSE_END = re.compile(
    r"(\n[ \t]*\n|[!?;]|(?<!\b\w)(?<!\badw)(?<!\bpr)(?<!\bdr)(?<!\bmgr)(?<!\bsp)(?<!\bnr)\.(?=\s|$))",
    re.IGNORECASE,
)
REPORTED_INSTRUMENT = re.compile(
    r"\b(?:dokument\w*|akt\w*|pełnomocnictw\w*|uchwał\w*|umow\w*)\b[\s\S]*?\b(?:w|zgodnie z|na mocy) któr\w*\b",
    re.IGNORECASE,
)


def operative_grant_text(text: str) -> str:
    """Exclude reported appointments while keeping line boundaries for mixed-source deeds."""
    heading = NOTARIAL_HEADING.search(text)
    if not heading:
        return text

    def mask(fragment: str) -> str:
        return re.sub(r"\S+", "|", fragment)

    def unquote(match: re.Match) -> str:
        excerpt = match[0]
        return (
            mask(excerpt) if GRANT.search(excerpt) or re.search(r"\bpełnomocni\w*", excerpt, re.IGNORECASE) else excerpt
        )

    body = re.sub(r'„[^”“]*[”“]|«[^»]*»|"[^"]*"', unquote, text[heading.end() :])
    clauses = DEED_CLAUSE_END.split(body)
    for i in range(0, len(clauses), 2):
        clause = clauses[i]
        for action in GRANT.finditer(clause):
            prefix = clause[: action.start()]
            if REPORTED_INSTRUMENT.search(prefix) or re.search(r"\bnie\s*$", prefix, re.IGNORECASE):
                clauses[i] = mask(clause)
                break
    return text[: heading.end()] + "".join(clauses)


def has_notarial_grant(text: str) -> bool:
    if not NOTARIAL_HEADING.search(text):
        return False
    for clause in DEED_CLAUSE_END.split(operative_grant_text(text))[::2]:
        grant = GRANT.search(clause)
        if grant and re.search(r"\bpełnomocni\w*\b", clause[grant.end() :], re.IGNORECASE) and _attorneys(clause):
            return True
    return False


SIGNER_ROLE_RE = re.compile(
    r"(?:Prezes|Wiceprezes|Członek|Prokurent|Dyrektor|Wspólnik|Właściciel|Komplementariusz)"
    r"(?: (?:Zarządu|Generalny))?",
    re.IGNORECASE,
)


SIGNATURE_HEADING = re.compile(
    r"(?:Mocodawca|Podpis(?: mocodawcy)?)(?::?\s+Pełnomocnictwo przyjmuję)?:?", re.IGNORECASE
)
NAMED_SIGNATURE = re.compile(r"^(?:W imieniu|Za)\s+", re.IGNORECASE)


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


def grant_parties(text: str) -> tuple[list[dict], list[tuple[dict, str]]]:
    principals = _principals(text)
    officers = _declared_officers(text)
    if officers:
        issuers = {p["nazwa"]: p for p in principals}
        for data, _ in officers:
            # A capitalized officer title can prefix the same company in the ordinary parser.
            for name in list(issuers):
                role = SIGNER_ROLE_RE.match(name)
                if role and name[role.end() :].strip() == data["nazwa"]:
                    issuer = issuers.pop(name)
                    issuer["nazwa"] = data["nazwa"]
                    issuers.setdefault(issuer["nazwa"], issuer)
            issuer = issuers.setdefault(data["nazwa"], data)
            for key in ("krs", "nip"):
                issuer[key] = issuer[key] or data[key]
        normalized = squash(text)
        principals = sorted(issuers.values(), key=lambda p: normalized.find(p["nazwa"]))
        # A notary records who appeared even if the text contains no evidence of execution.
        if NOTARIAL_HEADING.search(text) and not SIGNED_DEED.search(squash(text[GRANT.search(text).end() :])):
            officers = []
    if len(principals) == 1 and principals[0]["typ"] == "osoba_prawna" and principals[0]["nip"] is None:
        _issuer_identifiers(text, principals[0])
    return principals, officers


def finish_record(
    text: str, principals: list[dict], officers: list[tuple[dict, str]], attorneys: list[dict], signers: list[list]
) -> dict:
    principal_names = [p["nazwa"] for p in principals]
    for principal, name in officers:
        people = signers[principal_names.index(principal["nazwa"])]
        if name not in people:
            people.append(name)
    _add_stamp_signers(text, principal_names, {a["imie_nazwisko"] for a in attorneys}, signers)
    return {
        "mocodawca": [
            {"data": principal, "podpisujacy": [{"imie_nazwisko": name} for name in names]}
            for principal, names in zip(principals, signers)
        ],
        "pelnomocnicy": attorneys,
    }


def extract(text: str) -> dict:
    text = operative_grant_text(text)
    principals, officers = grant_parties(text)
    attorneys = _attorneys(text)
    signers = _signers(text, [p["nazwa"] for p in principals], {a["imie_nazwisko"] for a in attorneys})
    return finish_record(text, principals, officers, attorneys, signers)
