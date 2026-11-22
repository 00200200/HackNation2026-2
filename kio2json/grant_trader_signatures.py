"""Read a proprietor's execution of a mandate separately from its acceptance or certification."""

import re

from .common import PERSON, squash
from .grant_traders import CONTACT_CAPTION, UNDERSIGNED
from .personal_names import compatible_names, nominative

PROPRIETOR = r"przedsiębiorcy|właściciel(?:a|ki)"
REPRESENTATIVE = (
    r"(?:przedstawiciel(?:a|ki)|pełnomocni(?:ka|czki))\s+(?:mocodawcy|przedsiębiorcy)"
    r"|osoby (?:uprawnionej|upoważnionej) do reprezent(?:acji|owania) (?:mocodawcy|przedsiębiorcy)"
)
ON_BEHALF = r"(?:z upoważnienia|w imieniu) (?:mocodawcy|przedsiębiorcy)(?: podpisa[łl]a?)?"
ISSUER_CAPTION = rf"(?:(?:czytelny )?podpis (?:mocodawcy|{REPRESENTATIVE})|{ON_BEHALF})"
ISSUER_RESUMES = re.compile(rf"^[ (]*{ISSUER_CAPTION}\b", re.IGNORECASE)
FOREIGN_EXECUTION = re.compile(
    r"\b(?:pełnomocnictwo przyjmuję|przyjmuję pełnomocnictwo|przyjęcie pełnomocnictwa|za zgodność z oryginałem)\b"
    r"|^\W*(?:poświadcz(?:am|a|enie|ono)|potwierdz\w* zgodność|świadek|świadkowie|notariusz|odbiorca|"
    r"podpis (?:świadka|pełnomocnika|odbiorcy|przyjmującego)"
    r"|(?:dane )?(?:kontrahent[a]?|zamawiając(?:y|ego)|uczestni(?:k|ka))(?=\s*:|$))\b",
    re.IGNORECASE,
)
PARTY_DETAILS = re.compile(
    rf"^(?:{CONTACT_CAPTION}|(?:dane )?pełnomocni(?:ka?|ków|cy|czka|czki))(?:\s*:|$)", re.IGNORECASE
)
OWNER_CAPTION = re.compile(rf"^[ (]*(?:czytelny )?podpis (?:{PROPRIETOR})\b", re.IGNORECASE)
CAPTION = re.compile(
    rf"(?P<proxy>{ISSUER_CAPTION})|podpisa[łl]a?|(?:czytelny )?podpis(?: (?:{PROPRIETOR}))?",
    re.IGNORECASE,
)
RULE = re.compile(r"[._…─━— ]{4,}")


def issuer_signature_text(text: str, principals: list[dict], grant: re.Match | None) -> str:
    """Mask foreign signing sections while retaining line provenance for mixed-page readers."""
    if len(principals) != 1 or principals[0]["typ"] != "osoba_fizyczna" or not grant:
        return text
    section = "issuer"
    lines = []
    for line in text[grant.end() :].splitlines(keepends=True):
        row = line.strip()
        if ISSUER_RESUMES.match(row) or (section == "details" and OWNER_CAPTION.match(row)):
            section = "issuer"
        elif FOREIGN_EXECUTION.search(row):
            section = "foreign"
        elif section == "issuer" and PARTY_DETAILS.match(row):
            section = "details"
        lines.append(line if section == "issuer" else re.sub(r"\S+", "|", line))
    return text[: grant.end()] + "".join(lines)


def add_trader_signers(text: str, grant: re.Match, owner: str, attorneys: set[str], people: list) -> None:
    declaration = squash(text[: grant.start()])
    subject = re.search(rf"(?i:\b{UNDERSIGNED}[, ]+)({PERSON})\b", declaration)
    if subject:
        name = subject[1]
        representation = re.match(rf"(?i:[, ]+działając[ay]? w imieniu )({PERSON})\b", declaration[subject.end() :])
        signs_for_owner = representation and (
            nominative(representation[1], "gen") == owner or compatible_names(representation[1], owner)
        )
        if (name == owner or signs_for_owner) and name not in people and name not in attorneys:
            people.append(name)

    lines = [line.strip() for line in text[grant.end() :].splitlines() if line.strip() and not RULE.fullmatch(line)]
    for index, line in enumerate(lines):
        caption = CAPTION.match(line.lstrip("("))
        if caption:
            value = line.lstrip("(")[caption.end() :].strip(" ):–—-")
            if not value:
                # A signature caption can be printed above or below the actual name.
                adjacent = lines[index + 1 : index + 2]
                if index and (index < 2 or not lines[index - 2].endswith(":")):
                    adjacent = [lines[index - 1], *adjacent]
                names = [row for row in adjacent if re.fullmatch(PERSON, row.title() if row.isupper() else row)]
                value = names[0] if len(names) == 1 else ""
        elif (
            index == len(lines) - 1
            and index > 0
            and re.fullmatch(
                rf"{re.escape(owner)}(?:\s*[-–—,(]\s*(?:właściciel(?:ka)?|przedsiębiorca)\)?)?", line, re.IGNORECASE
            )
            and lines[index - 1].endswith(".")
            and all(row[0].islower() and not row.endswith((".", ":")) for row in lines[: index - 1])
        ):
            # The trader's repeated, isolated name closes the (possibly wrapped) granting sentence.
            value = owner
        else:
            continue
        name = value.title() if value.isupper() else value
        if name.casefold() == owner.casefold():
            name = owner
        elif not (caption and caption["proxy"] and re.fullmatch(PERSON, name) and nominative(name, "nom") == name):
            continue
        if name not in people and not any(
            a and len(a.split()) == len(name.split()) and compatible_names(a, name) for a in attorneys
        ):
            people.append(name)
