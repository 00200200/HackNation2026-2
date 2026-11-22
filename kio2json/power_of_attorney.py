"""Power of attorney -> mocodawca[] (each with its own podpisujacy[]) and pelnomocnicy[]."""

import re

from rapidfuzz.distance import Levenshtein
from stdnum.pl import nip

from .common import ATTORNEY_RE, EMAIL_RE, PERSON, UPPER, registry_ids, squash
from .personal_names import compatible_names, resolve_attorneys

LEGAL_FORM = (
    r"(?i:(?:sp\.|spółka)\s?z\s?o\.\s?o(?:\.|(?=\s+z siedzibą))(?:\s?sp\.\s?k(?:\.|(?=\s+z siedzibą)))?|S\.\s?A\.|sp\.\s?k\.|sp\.\s?j\.|sp\.\s?p\.|s\.c\."
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

    text = re.sub(r"(?i)(\bpod (?:numerem|nr) )KR\$(?=\s*:?\s*\d{10}\b)", r"\1KRS", text)
    return re.sub(r"\b[A-ZĄĆĘŁŃÓŚŹŻ]{3}\b(?=\s*:\s*\d{10}(?!\d))", normalize, text)


def _identity_clause(details: str) -> str:
    for boundary in OTHER_ROLE.finditer(details):
        # A court can maintain the register named earlier in the same identity clause.
        if REGISTER.search(details, 0, boundary.end()) and re.match(
            r"\s+sąd\w*\b", details[boundary.end() :], re.IGNORECASE
        ):
            continue
        if re.search(
            r"\b(?:rejestru|rejestrze)\s+przedsiębiorców\s+(?:pod (?:nr|numerem) KRS:|prowadzonego przez)$",
            squash(details[: boundary.end()]),
            re.IGNORECASE,
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
            after = re.sub(r"\bm\.\s*st\.", "miasta stołecznego", clause[register.end() :], flags=re.IGNORECASE)
            section = REGISTRY_END.split(after, maxsplit=1)[0]
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


def _declared_officers(declaration: str, *, known_issuers: set[str] | None = None) -> list[tuple[dict, str]]:
    officers = []
    for entry in ENTRY_BOUNDARY.split(declaration):
        # An officer title is often capitalized and otherwise looks like part of a company name.
        without_roles = SIGNER_ROLE_RE.sub(lambda m: "|" * len(m[0]), entry)
        companies = list(COMPANY_RE.finditer(without_roles))
        if len(companies) != 1:
            continue
        company = companies[0]
        name = _company_name(company[1])
        if (
            known_issuers is not None
            and name not in known_issuers
            and not re.search(r"\breprezentowan\w*\s+przez\b", entry[company.end() :], re.IGNORECASE)
        ):
            continue
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
            officers.append((_company_data(name, entry[company.end() :]), person))
    return officers


def _issuer_identifiers(text: str, principal: dict) -> None:
    # A tax number must share an identity block with this company's name or register number.
    def core(name: str) -> str:
        return re.sub(LEGAL_FORM + r"$", "", name).strip().casefold()

    company = core(principal["nazwa"])
    name_pattern = re.compile(rf"(?<!\w){re.escape(company)}(?!\w)", re.IGNORECASE)
    krs = principal["krs"]
    lines = text.splitlines()
    # Consecutive registry rows in the letterhead may precede the first legible issuer name.
    heading = MANDATE_TITLE.search(text)
    header_rows = text.count("\n", 0, heading.start()) if heading else 0
    candidates = set()
    pending = set()
    owner = None
    anchor = 0
    for i, line in enumerate(lines):
        ids = registry_ids(line)
        if not ids["krs"] and (
            number := re.search(r"\bKRS\s+pod (?:numerem|nr)\s+(\d{10})(?!\d)", line, re.IGNORECASE)
        ):
            ids["krs"] = number[1]
        names = {core(_company_name(m[1])) for m in COMPANY_RE.finditer(line)}
        role = OTHER_ROLE.search(line) if not re.match(r"https?://", line, re.IGNORECASE) else None
        other_company = names - {company} or (krs and ids["krs"] and ids["krs"] != krs)
        if other_company or re.search(r"\b(?:zamawiając\w*|odbiorc\w*|pełnomocnik\w*)\s*:", line, re.IGNORECASE):
            header_rows = 0
        foreign = role or other_company
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
        if not number or not nip.is_valid(number) or (owner is False and not (registry_line and i < header_rows)):
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
    original = text
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
    addressed = (
        rf"(?i:{GRANT.pattern}\s+pełnomocnictwa\s+do reprezentowania\s+[^,:.]{{1,55}}:\s*(?:pani|panu)\s+)({PERSON})"
    )
    appointment_field = (
        rf"(?im:^[ \t]*(?:niniejszym )?{GRANT.pattern} (?:pełnomocnictwa )?"
        r"do (?:reprezentowania|działania|występowania)\b[^:\n]{0,100}:[ \t]*\n[ \t]*)"
        rf"({PERSON})(?=[ \t]*(?:$|\n|,|\bPESEL\b))"
    )
    matches = sorted(
        (
            (m, kind)
            for kind, pattern in enumerate((titled, plain, labelled, addressed, appointment_field))
            for m in re.finditer(pattern, text)
        ),
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
                if (pesel and number == pesel) or ((not number or not pesel) and compatible_names(name, label))
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
    return resolve_attorneys(original, list(people.values()))


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
    r"(?:Mocodawca|Podpis(?: (?:przedstawiciela )?mocodawcy)?)(?::?\s+Pełnomocnictwo przyjmuję)?:?", re.IGNORECASE
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
        owner = current
        if FOOTER.search(line) or re.search(r"\b(?:Sąd Rejonowy|Wydział Gospodarczy)\b", line):
            current = None
            # Keep consecutive signature slots under the same heading, then stop at the contact block.
            printed = SIGNATURE_WITH_EMAIL.fullmatch(line.strip())
            if not printed:
                continue
            following = lines[index + 1].strip() if index + 1 < len(lines) else ""
            if SIGNATURE_LINE_RE.fullmatch(following) or SIGNATURE_WITH_EMAIL.fullmatch(following):
                current = owner
            line = printed[1]
        if owner is None or index < first_candidate:
            continue
        line = ROLE_WORDS_RE.sub("|", ATTORNEY_RE.sub("|", line))
        for person in re.findall(PERSON, line):
            person = squash(person)
            if person not in attorney_names and person not in signers[owner]:
                signers[owner].append(person)
    return signers


STAMP = re.compile(r"(?i)^(?:podpis(?:ano|any|ana) (?:elektronicznie )?przez|signed (?:electronically )?by)\s*[:：]\s*")
SIGNATURE_WITH_EMAIL = re.compile(rf"({PERSON})(?:[ \t]+|[ \t]*[,;(][ \t]*){EMAIL_RE.pattern}\)?[.]?")
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
        if not marker and i and re.fullmatch(PERSON, name := lines[i - 1].strip()):
            # A printed caption, name and position form one explicit signature block.
            caption = lines[i - 2].strip() if i >= 2 else ""
            if (
                re.fullmatch(r"podpis (?:przedstawiciela )?mocodawcy:?", caption, re.IGNORECASE)
                and not SIGNER_ROLE_RE.fullmatch(name)
                and name not in attorneys
                and name not in signers[owner]
            ):
                signers[owner].append(name)
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


MANDATE_TITLE = re.compile(r"(?im)^\s*pełnomocnictwo(?: procesowe| szczególne)?(?: nr\.? [\w/-]+)?[ \t]*$")
CIVIL_PARTNERS = re.compile(
    rf"(?i:my,?\s+niżej\s+podpisan[ie],?\s+)({PERSON}(?:\s+(?:i|oraz)\s+{PERSON})+),"
    r"\s*(?i:wspólnic[yz]\w*\s+spółki\s+cywilnej)\s+([^,;:]+?)\s+(?i:z\s+siedzibą)\b"
)


def grant_parties(text: str) -> tuple[list[dict], list[tuple[dict, str]]]:
    heading = MANDATE_TITLE.search(text)
    body = text[heading.end() :] if heading else text
    grant = GRANT.search(body)
    partners = CIVIL_PARTNERS.search(body, 0, grant.start()) if grant else None
    if partners:
        people = [squash(name) for name in re.findall(PERSON, partners[1])]
        data = [
            {"imie_nazwisko": name, "krs": None, "nazwa": squash(partners[2]), "nip": None, "typ": "osoba_fizyczna"}
            for name in people
        ]
        return data, []
    principals = _principals(body) or _principals(text)
    officers = _declared_officers(body[: grant.start()]) if grant else []
    if heading and grant:
        # An explicit issuer row may precede the title, alongside unrelated letterhead.
        prefix = text[: heading.start()]
        earlier = _principals(prefix) if GRANTOR.search(prefix) else []
        if earlier:
            ordered = {p["nazwa"]: p for p in earlier}
            for principal in principals:
                issuer = ordered.setdefault(principal["nazwa"], principal)
                for key in ("krs", "nip"):
                    issuer[key] = issuer[key] or principal[key]
            principals = list(ordered.values())
        names = {p["nazwa"] for p in principals}
        officers = _declared_officers(prefix, known_issuers=names) + officers
    if not principals and grant:
        # A grant made before the issuer's identity can name it in the representation clause.
        on_behalf = re.match(
            r"[\s\S]{0,220}?\bdo (?:działania|korzystania|występowania) w imieniu\s+",
            body[grant.end() :],
            re.IGNORECASE,
        )
        if on_behalf:
            tail = body[grant.end() + on_behalf.end() :]
            company = COMPANY_RE.match(tail)
            if company and re.search(
                r"\(dalej\s*:\s*[„\"](?:Wykonawca|Mocodawca)", tail[company.end() :][:140], re.IGNORECASE
            ):
                principals = [_company_data(_company_name(company[1]), tail[company.end() :])]
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
    # On a compact form the signature fields immediately follow the named issuer
    # and its register numbers. Stop ownership at the next unrelated line.
    owner = None
    for line in map(str.strip, text.splitlines()):
        if line in principal_names:
            owner = principal_names.index(line)
        elif owner is not None and re.match(r"^(?:KRS|NIP|REGON)\b", line, re.IGNORECASE):
            continue
        elif owner is not None and (
            m := re.fullmatch(rf"(?i:podpis(?: mocodawcy)?|podpisa[łl]a?)\s*:\s*({PERSON})", line)
        ):
            if m[1] not in signers[owner]:
                signers[owner].append(m[1])
        else:
            owner = None
    for principal, name in officers:
        people = signers[principal_names.index(principal["nazwa"])]
        if name not in people:
            people.append(name)
    _add_stamp_signers(text, principal_names, {a["imie_nazwisko"] for a in attorneys}, signers)
    for principal, people in zip(principals, signers, strict=True):
        if principal["typ"] == "osoba_fizyczna" and principal["imie_nazwisko"] and CIVIL_PARTNERS.search(text):
            people[:] = [principal["imie_nazwisko"]]
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


def _card_people(lines: list[str]) -> list[dict]:
    """Each new name needs a complete labelled slot or an explicitly listed entry."""
    result = []
    person = re.compile(rf"(?:(?:\d+[.)]|[•–-])\s+)?(?:(?:adw\.|r\.\s*pr\.)\s+)?({PERSON})[,;]?")
    for index, line in enumerate(lines):
        if match := person.fullmatch(line):
            if index and not re.match(r"^(?:\d+[.)]|[•–-])\s+", line):
                break
            result.append({"imie_nazwisko": match[1], "pesel": None})
        elif result and (pesel := re.fullmatch(r"PESEL\s*:?\s*(\d{11})", line, re.IGNORECASE)):
            result.append({"imie_nazwisko": result[-1]["imie_nazwisko"], "pesel": pesel[1]})
        else:
            break
    return result


def _merge_card_people(existing, printed, *, with_pesel):
    for person in printed:
        name = person["imie_nazwisko"]
        matches = [p for p in existing if (p["imie_nazwisko"] or "").casefold() == name.casefold()]
        if len(matches) == 1 and with_pesel and not matches[0]["pesel"]:
            matches[0]["pesel"] = person["pesel"]
        elif not matches and all(
            p["imie_nazwisko"]
            and not (len(p["imie_nazwisko"].split()) == 2 and compatible_names(p["imie_nazwisko"], name))
            and not (with_pesel and person["pesel"] and p["pesel"] == person["pesel"])
            for p in existing
        ):
            existing.append(person if with_pesel else {"imie_nazwisko": name})


def apply_grant_blocks(record, blocks, text):
    """A signature inherits the identified principal of its column, never a global list position."""
    if not blocks or NOTARIAL_HEADING.search(text):
        return
    owners = {}
    printed_people = []
    for block in blocks:
        if block.role == "appointee":
            printed_people.extend(_card_people(block.lines))
        elif block.role == "principal" and block.lines:
            lines = block.lines
            if lines[0].casefold() == "osoba prawna":
                lines = lines[1:]
            identity = re.split(r"\b(?:KRS|NIP|REGON)\b", squash(" ".join(lines)), maxsplit=1)[0].strip(" ,;")
            identity = re.sub(r"^\d+[.)]\s+", "", identity)
            if not COMPANY_RE.fullmatch(identity):
                continue
            data = _company_data(identity, "\n".join(lines))
            rows = record["mocodawca"]
            matches = [r for r in rows if (r["data"]["nazwa"] or "").casefold() == identity.casefold()]
            if len(matches) == 1 and all(
                not data[k] or not matches[0]["data"][k] or data[k] == matches[0]["data"][k] for k in ("krs", "nip")
            ):
                owner = matches[0]
                for key in ("krs", "nip"):
                    owner["data"][key] = owner["data"][key] or data[key]
            elif not matches and all(
                r["data"]["nazwa"]
                and not any(data[k] and r["data"][k] == data[k] for k in ("krs", "nip"))
                and identity.casefold() not in r["data"]["nazwa"].casefold()
                and r["data"]["nazwa"].casefold() not in identity.casefold()
                for r in rows
            ):
                owner = {"data": data, "podpisujacy": []}
                rows.append(owner)
            else:
                continue
            owners[block.order] = owner
    for block in blocks:
        if block.role == "signature_owner":
            identity = squash(" ".join(block.lines)).strip(" :").casefold()
            matches = [r for r in record["mocodawca"] if (r["data"]["nazwa"] or "").casefold() == identity]
            if len(matches) == 1:
                owners[block.order] = matches[0]
    by_name, by_id = {}, {}
    for person in [*record["pelnomocnicy"], *printed_people]:
        if person["imie_nazwisko"] and person["pesel"]:
            name = person["imie_nazwisko"].casefold()
            by_name.setdefault(name, set()).add(person["pesel"])
            by_id.setdefault(person["pesel"], set()).add(name)
    people = []
    for person in printed_people:
        ids = by_name.get(person["imie_nazwisko"].casefold(), set())
        if len(ids) <= 1 and all(len(by_id[number]) == 1 for number in ids):
            people.append({**person, "pesel": next(iter(ids), None)})
    _merge_card_people(record["pelnomocnicy"], people, with_pesel=True)
    for block in blocks:
        if block.role == "signer" and block.parent in owners:
            _merge_card_people(owners[block.parent]["podpisujacy"], _card_people(block.lines), with_pesel=False)
