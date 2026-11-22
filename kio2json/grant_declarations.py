"""Read the parties in a scanned grant's declaration, before its list of powers."""

import re
from collections.abc import Collection

from .common import LOWER, PERSON, UPPER, registry_ids, squash
from .personal_names import compatible_names
from .power_of_attorney import COMPANY_RE, GRANT, GRANTOR, LEGAL_FORM, SIGNER_ROLE_RE, _identity_clause

HEADING = re.compile(r"(?im)^[ \t]*pełnomocnictwo(?: procesowe)?[ \t]*$")
APPOINTMENT = re.compile(rf"(?i:{GRANT.pattern}\s+pełnomocnictwa)\s*:")
SCOPE = re.compile(r"\bdo\s+(?:reprezentowania|działania|występowania|zastępowania)\b", re.IGNORECASE)
MEMBER = re.compile(
    rf"(?m)^[ \t]*(?:\d+[.)][ \t]*)?([{UPPER}][\w&'’-]*(?:[ \t]+[\w&'’-]+)*?\s+{LEGAL_FORM})"
    r"\s+(?i:z\s+siedzibą\s+w)\b"
)
REPRESENTATION = re.compile(r"\breprezentowan\w*\s+przez\s*:?\s*", re.IGNORECASE)
OFFICER = re.compile(rf"({PERSON})\s*[-–—,(]\s*(?i:{SIGNER_ROLE_RE.pattern})\b", flags=0)
PERSONAL = re.compile(rf"(?i:\bja,?\s+(?:niżej\s+)?podpisan[ay](?:/[ay])?\s+)({PERSON})\b")
# Keep the index mapping to the printed text, including accents in company names.
FOLD = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
LONG_FORM = re.compile(r"\bspolka\s+z\s+ograniczona\s+odpowiedzialnoscia\b", re.IGNORECASE)
LIST_NAME = re.compile(
    rf"(?:^[ \t]*|\boraz\s+)(?:[0-9lI]+[.)]\s*|[•–—-]\s+)?"
    rf"([{UPPER}{LOWER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?[ \t]+[{UPPER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?)"
    r"(?=\s|[,.(-]|$)",
    re.MULTILINE,
)
DETAIL = re.compile(
    r"\s*(?:\([^()]*\)|[-–—]\s*(?:adwokat|radca\s+prawny|pracownik)\b[^();]*)?\s*[,.;]?\s*", re.IGNORECASE
)


def check_ocr_trade_names(record: dict, pages: list[str], ocr_pages: Collection[int]) -> None:
    """A proprietor's name embedded in an OCR-only trade name must agree on diacritics."""
    for row in record["mocodawca"]:
        data = row["data"]
        if data["typ"] != "osoba_fizyczna" or not data["nazwa"] or not data["imie_nazwisko"]:
            continue
        firm = data["nazwa"].casefold()
        owner = data["imie_nazwisko"].casefold()
        matches = list(re.finditer(rf"(?<!\w){re.escape(owner.translate(FOLD))}(?!\w)", firm.translate(FOLD)))
        if not matches or any(firm[m.start() : m.end()] == owner for m in matches):
            continue
        printed_firm = re.compile(rf"(?<!\w){re.escape(firm)}(?!\w)")
        sources = {i in ocr_pages for i, page in enumerate(pages, 1) if printed_firm.search(squash(page).casefold())}
        if sources == {True}:
            data["nazwa"] = None


def _legal_forms(text: str) -> str:
    def restore(match: re.Match) -> str:
        source = text[match.start() : match.end()]
        canonical = "spółka z ograniczoną odpowiedzialnością"
        return canonical.capitalize() if source[0].isupper() else canonical

    folded = text.translate(FOLD)
    for match in reversed(list(LONG_FORM.finditer(folded))):
        text = text[: match.start()] + restore(match) + text[match.end() :]
    return text


def _representatives(block: str) -> list[dict]:
    marker = REPRESENTATION.search(block)
    if not marker:
        return []
    # A speck at the right margin can split the halves of a wrapped name.
    section = re.sub(r"[ \t]+[.|][ \t]*\n", "\n", block[marker.end() :])
    section = re.split(r"\(\s*dalej\b|\b(?:zamawiający|pełnomocnik)\s*:", section, flags=re.IGNORECASE)[0]
    people = dict.fromkeys(squash(m[1]) for m in OFFICER.finditer(section))
    return [{"imie_nazwisko": name} for name in people]


def _grantors(declaration: str) -> list[dict]:
    individual = PERSONAL.search(declaration)
    if individual and re.search(
        r"prowadząc\S*\s+działalność\s+gospodarczą", declaration[individual.end() :], re.IGNORECASE
    ):
        name = squash(individual[1])
        data = {
            "imie_nazwisko": name,
            "krs": None,
            "nazwa": None,
            "nip": registry_ids(declaration)["nip"],
            "typ": "osoba_fizyczna",
        }
        return [{"data": data, "podpisujacy": [{"imie_nazwisko": name}]}]
    text = _legal_forms(declaration)
    members = list(MEMBER.finditer(text))
    records = []
    for i, member in enumerate(members):
        block = text[member.end() : members[i + 1].start() if i + 1 < len(members) else None]
        reps = REPRESENTATION.search(block)
        if not reps:
            return []
        ids = registry_ids(block[: reps.start()])
        data = {
            "imie_nazwisko": None,
            "krs": ids["krs"],
            "nazwa": squash(member[1]),
            "nip": ids["nip"],
            "typ": "osoba_prawna",
        }
        records.append({"data": data, "podpisujacy": _representatives(block)})
    return records


def _appointees(section: str) -> list[dict]:
    # The scope can start with an OCR bullet in the left margin.
    section = re.sub(r"\n[^\w\n]*$", "", section).strip()
    section = re.sub(r"\boraz[ \t]*\n", "oraz ", section)
    mentions = list(LIST_NAME.finditer(section))
    if not mentions or section[: mentions[0].start()].strip():
        return []
    result = []
    for i, match in enumerate(mentions):
        details = section[match.end() : mentions[i + 1].start() if i + 1 < len(mentions) else None]
        if not DETAIL.fullmatch(details):
            return []
        number = re.search(r"\bPESEL\s*:?\s*(\d{11})(?!\d)", details, re.IGNORECASE)
        name = match[1]
        result.append({"imie_nazwisko": name[0].upper() + name[1:], "pesel": number[1] if number else None})
    return result


def _same_grantor(left: dict, right: dict) -> bool:
    if left["typ"] != right["typ"]:
        return False
    if left["typ"] == "osoba_fizyczna":
        return bool(left["imie_nazwisko"] and left["imie_nazwisko"] == right["imie_nazwisko"])
    if left["krs"] and right["krs"]:
        return left["krs"] == right["krs"]
    return left["nazwa"] == right["nazwa"] or bool(left["nazwa"] and right["nazwa"].endswith(" " + left["nazwa"]))


def _merge_grantors(previous: list[dict], members: list[dict]) -> bool:
    for old in previous:
        owners = [member for member in members if _same_grantor(old["data"], member["data"])]
        if len(owners) != 1:
            return False
        owner = owners[0]
        for key in ("krs", "nip", "nazwa"):
            owner["data"][key] = owner["data"][key] or old["data"][key]
        owner["podpisujacy"].extend(s for s in old["podpisujacy"] if s not in owner["podpisujacy"])
    return True


def _merge_attorneys(previous: list[dict], people: list[dict]) -> None:
    for person in people:
        candidates = [
            old
            for old in previous
            if compatible_names(person["imie_nazwisko"], old["imie_nazwisko"])
            and not (old["pesel"] and person["pesel"] and old["pesel"] != person["pesel"])
        ]
        if len(candidates) == 1:
            old = candidates[0]
            same = [p for p in people if compatible_names(p["imie_nazwisko"], old["imie_nazwisko"])]
            if len(same) == 1:
                person["imie_nazwisko"] = old["imie_nazwisko"]
                person["pesel"] = person["pesel"] or old["pesel"]


def read_declaration(page: str, record: dict) -> None:
    heading = HEADING.search(page)
    grant = APPOINTMENT.search(page, heading.end()) if heading else None
    if not grant:
        return
    members = _grantors(page[heading.end() : grant.start()])
    if members and _merge_grantors(record["mocodawca"], members):
        record["mocodawca"] = members
    scope = SCOPE.search(page, grant.end())
    if scope and (people := _appointees(page[grant.end() : scope.start()])):
        _merge_attorneys(record["pelnomocnicy"], people)
        record["pelnomocnicy"] = people


REPRESENTED_COMPANY = re.compile(
    rf"(?i:\bdo\s+reprezentacji)\s+((?:[{UPPER}][\w-]+\s+|[–—-]\s+){{2,12}}?{LEGAL_FORM})"
    r"\s+(?i:z\s+siedzibą)\b"
)


def complete_represented_company(page: str, record: dict) -> None:
    """Restore a cut-off company name from its officer's genitive representation clause."""
    from .personal_names import _analyser

    grant = GRANT.search(page)
    if not grant or len(record["mocodawca"]) != 1:
        return
    data = record["mocodawca"][0]["data"]
    if not data["krs"] or not data["nazwa"]:
        return
    declaration = page[: grant.start()]
    matches = [m for m in REPRESENTED_COMPANY.finditer(declaration) if squash(m[1]).endswith(" " + data["nazwa"])]
    if len(matches) != 1:
        return
    match = matches[0]
    details = declaration[match.end() :]
    for boundary in (COMPANY_RE, GRANTOR):
        if new_party := boundary.search(details):
            details = details[: new_party.start()]
    if registry_ids(_identity_clause(details))["krs"] != data["krs"]:
        return
    head, complement, tail = squash(match[1]).split(" ", 2)

    # A noun with a plural genitive complement changes only its head (e.g. "Zakładu Pomiarów").
    def nouns(word: str, number: str) -> set[str]:
        return {
            lemma.partition(":")[0]
            for _, _, (surface, lemma, tag, labels, _) in _analyser().analyse(word)
            if surface == word
            and tag.startswith(f"subst:{number}:")
            and "gen" in tag.split(":")[2].split(".")
            and "nazwa_pospolita" in labels
        }

    heads = nouns(head, "sg")
    if len(heads) == 1 and nouns(complement, "pl"):
        data["nazwa"] = heads.pop().capitalize() + " " + complement + " " + tail.replace(" — ", " – ")
