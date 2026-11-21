"""Read signature blocks from OCR lines in a power of attorney."""

import re
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from . import power_of_attorney
from .common import ATTORNEY_RE, DATE, PERSON, UPPER, squash
from .ocr_budget import remaining_ms
from .pdf_text import WordBox
from .personal_names import nominative
from .power_of_attorney import GRANT, GRANTOR

SIGNATURE_LINE_RE = re.compile(r"\.{10,}|_{5,}|[─━—]{4,}")

SIGNER_ROLE_RE = re.compile(
    r"(?:Prezes|Wiceprezes|Członek|Prokurent|Dyrektor|Wspólnik|Właściciel|Komplementariusz)"
    r"(?: (?:Zarządu|Generalny))?",
    re.IGNORECASE,
)


SIGNATURE_HEADING = re.compile(
    r"(?:Mocodawca|(?:Czytelny )?Podpis(?: (?:mocodawcy|osoby (?:uprawnionej|upoważnionej)"
    r" do (?:reprezentacji|reprezentowania) mocodawcy))?(?: *\(imię i nazwisko\))?)"
    r"(?::?\s+Pełnomocnictwo przyjmuję)?:?",
    re.IGNORECASE,
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
    if re.search(r"\b(?:kontakt|koordynator)\w*", sentence, re.IGNORECASE):
        return False
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
    # The noun “odbioru” can start an ordinary sentence naming a contact.
    # An enumerated power or an explicit scope heading supplies the grant context.
    scoped = LIST_MARKER.match(sentence) or (start and lines[start - 1].endswith(":"))
    if not scoped and not sentence.casefold().startswith("opłata skarbowa od pełnomocnictwa"):
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


def _preceding_dotted_owner(lines: list[str], principals: list[str]) -> int | None:
    """A printed signature rule can continue onto a scanned page."""
    if len(lines) < 2 or not power_of_attorney.SIGNATURE_LINE_RE.fullmatch(lines[-1]):
        return None
    if NAMED_SIGNATURE.match(lines[-2]):
        return _signature_owner(lines[-2], "", principals)
    if len(lines) > 2 and NAMED_SIGNATURE.match(lines[-3]):
        return _signature_owner(squash(lines[-3] + " " + lines[-2]), "", principals)
    if len(principals) == 1 and (
        SIGNATURE_HEADING.fullmatch(lines[-2]) or _directly_after_grant(lines, len(lines) - 1, principals)
    ):
        return 0
    return None


def signers(run: list[str], principals: list[str], attorneys: set[str], prior: list[str]) -> list[list[str]]:
    signers = [[] for _ in principals]
    single = 0 if len(principals) == 1 else None
    # Earlier pages supply grant and acceptance context. Only OCR lines can
    # start an undotted block or supply its name, role and subsequent heading.
    lines = [line.strip() for line in prior if line.strip()]
    if any(re.match(r"^Pełnomocnictwo przyjmuję\b", line, re.IGNORECASE) for line in lines):
        return signers
    first = len(lines)
    current = _preceding_dotted_owner(lines, principals)
    expect_name = current is not None
    signed = False
    lines.extend(clean for raw in run if (clean := STAMP_PLACE.sub("", raw).strip()))
    for index in range(first, len(lines)):
        line = lines[index]
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


def confirmed_scan_signer(page: str, record: dict) -> None:
    """Bind a repeated officer or a split electronic-signature block to a sole grantor."""
    principals = record["mocodawca"]
    if len(principals) != 1:
        return
    grant = GRANT.search(page)
    if not grant:
        return
    signers = principals[0]["podpisujacy"]
    attorneys = {a["imie_nazwisko"] for a in record["pelnomocnicy"]}
    signed = page[grant.end() :]
    split_stamp = re.search(
        rf"(?im:^\W*elektronicznie\s*\n)[ \t]*(\w+)[ \t]+(?i:podpisan[ay]\s+przez)\s*\n[ \t]*({PERSON})\b",
        signed,
    )
    candidates = []
    if split_stamp and split_stamp[2].split()[0] == split_stamp[1]:
        candidates.append(squash(split_stamp[2]))
    declaration = re.search(
        rf"(?i:\bjako)\s+({PERSON})\s*[-–—]\s*(?i:{SIGNER_ROLE_RE.pattern})\b", page[: grant.start()]
    )
    if declaration:
        name = squash(declaration[1])
        if re.search(rf"(?m)^\s*{re.escape(name)}\s*[-–—]\s*(?i:{SIGNER_ROLE_RE.pattern})\b", signed):
            candidates.append(name)
            signers[:] = [s for s in signers if not SIGNER_ROLE_RE.fullmatch(s["imie_nazwisko"] or "")]
    for name in candidates:
        signer = {"imie_nazwisko": name}
        if name not in attorneys and signer not in signers:
            signers.append(signer)


# Below the last sentence of the mandate, each board stamp has its own column.
SCOPE_END = re.compile(
    r"\b(?:odwoławcz|postępowani|zamawiając|wykonawc|pełnomocnictw)\w*\b[^:;.!?]{0,65}\.$", re.IGNORECASE
)
STAMP_END = re.compile(r"za zgodność|pełnomocnictwo przyjmuję|do kontaktu|poświadcza|świadek|notariusz", re.IGNORECASE)


CERTIFICATION = re.compile(r"(?im)^[ \t]*(?:za zgodność z oryginałem|poświadczam zgodność|pełnomocnictwo przyjmuję)\b")


def board_stamp_names(lines: list[WordBox], attorneys: set[str], company: str) -> list[str]:
    if any(CERTIFICATION.match(line.text) for line in lines):
        return []
    ends = [i for i, line in enumerate(lines) if SCOPE_END.search(line.text)]
    if not ends or not GRANT.search(" ".join(line.text for line in lines[: ends[-1] + 1])):
        return []
    closing = lines[ends[-1]]
    stamps = []
    for line in lines[ends[-1] + 1 :]:
        if STAMP_END.search(line.text) or power_of_attorney.FOOTER.search(line.text):
            break
        if NAMED_SIGNATURE.match(line.text):
            owner = NAMED_SIGNATURE.sub("", line.text).strip(" :").casefold()
            if owner not in {company.casefold(), "spółkę", "spółki", "mocodawcę", "mocodawcy"}:
                break
        elif power_of_attorney.OTHER_ROLE.match(line.text) and not SIGNATURE_HEADING.fullmatch(line.text):
            break
        if closing.y1 <= line.y0 <= closing.y1 + 135:
            stamps.append(line)

    names = []
    for title in stamps:
        role, _, board = title.text.lower().strip().partition(" ")
        if (
            role not in {"prezes", "wiceprezes", "członek"}
            or Levenshtein.distance(board.replace("ą", "a"), "zarzadu") > 1
        ):
            continue
        people = []
        for row in stamps:
            if not (0 <= row.y0 - title.y1 <= 3 * (title.y1 - title.y0)):
                continue
            if not title.x0 <= (row.x0 + row.x1) / 2 <= title.x1:
                continue
            name = squash(re.sub(r"\s*/\s*", " ", row.text))
            name = name.title() if name.isupper() else name
            if re.fullmatch(PERSON, name) and nominative(name, "nom") == name:
                people.append(name)
        if len(people) == 1 and people[0] not in attorneys and people[0] not in names:
            names.append(people[0])
    return names


def recover_board_stamp(path: Path, record: dict, page: str) -> None:
    from .rapid_worker import recognize

    principals = record["mocodawca"]
    if len(principals) != 1 or principals[0]["podpisujacy"] or principals[0]["data"]["typ"] != "osoba_prawna":
        return
    if not GRANT.search(page) or power_of_attorney.NOTARIAL_HEADING.search(page) or CERTIFICATION.search(page):
        return
    lines = page.splitlines()
    closing = next((i for i in reversed(range(len(lines))) if SCOPE_END.search(lines[i])), None)
    if closing is None or STAMP_END.search("\n".join(lines[closing + 1 :])):
        return
    timeout = remaining_ms(35_000)
    if not timeout:
        return
    try:
        _, boxes = recognize(path, 1, "lines", timeout=timeout / 1000)
    except (OSError, RuntimeError):
        return
    attorneys = {p["imie_nazwisko"] for p in record["pelnomocnicy"]}
    names = board_stamp_names([WordBox(*box) for box in boxes], attorneys, principals[0]["data"]["nazwa"] or "")
    principals[0]["podpisujacy"] = [{"imie_nazwisko": name} for name in names]
