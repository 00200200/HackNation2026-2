"""Appeal to KIO -> OdwolanieKIO, Odwolujacy[], Zamawiajacy[], ZamowieniePubliczne."""

import re

from .appeal_charges import prose_action
from .common import ATTORNEY_RE, DATE, EMAIL_RE, LOWER, PERSON, UPPER, find_date, registry_ids, squash, to_iso

# Canonical descriptions from data/uzp/oczekiwane-json/czynnosc_powod_id_dict.md.
REASONS = {
    1: "Decyzja o odrzuceniu oferty",
    2: "Ogłoszenie wyboru oferty",
    3: "Decyzja o wykluczeniu wykonawcy",
    4: "Publikacja specyfikacji warunków zamówienia (SWZ)",
    5: "Modyfikacja treści SWZ",
    6: "Odpowiedzi/wyjaśnienia do SWZ",
    7: "Zaniechanie odrzucenia oferty",
    8: "Zaniechanie wykluczenia wykonawcy",
    9: "Decyzja o unieważnieniu postępowania",
    10: "Zaniechanie unieważnienia postępowania",
    11: "Opis przedmiotu zamówienia (OPZ)",
    12: "Projektowane postanowienia umowy",
}
# First match wins, so omissions ("zaniechał ...") come before the acts they negate.
REASON_RULES = [
    (10, r"zaniecha\w*\s+unieważnieni|nie\s+unieważnił"),
    (7, r"zaniecha\w*\s+odrzuceni|nie\s+odrzucił"),
    (8, r"zaniecha\w*\s+wykluczeni|nie\s+wykluczył"),
    (9, r"unieważni"),
    (3, r"wyklucz"),
    (1, r"odrzuc"),
    (6, r"odpowiedzi|wyjaśnie"),
    (5, r"modyfik|zmienił\s+treść"),
    (11, r"opis\w*\s+przedmiot|\bopz\b"),
    (12, r"postanowie\w+\s+umowy|projekt\w*\s+umowy|wz[oó]r\w*\s+umowy"),
    (4, r"specyfikacj|\bswz\b"),
    (2, r"wyb[oó]r\w*\s+(?:naj\w+\s+)?ofert|najkorzystniejsz"),
]

SECTION_RE = re.compile(r"^(Zamawiaj[ąa]cy|Odwo[łl]uj[ąa]cy|Wykonawca)\s*[:(](.*)$", re.IGNORECASE)
ADDRESS_RE = re.compile(r"^(?:ul\.|al\.|pl\.|os\.|\d{2}\s*[-–—]\s*\d{3}\b)|^[^,]{2,40},\s*(?:ul\.|al\.)", re.IGNORECASE)
ID_LINE_RE = re.compile(r"\b(?:KRS|NIP|REGON)\b")
_PLACE = rf"[{UPPER}][{LOWER}]+(?:[ \-][{UPPER}][{LOWER}]+){{0,2}}"
PLACE_DATE_RE = re.compile(
    rf"^(?:[—–|] *)?({_PLACE}),?\s+(?:(?:dnia|dn\.)\s+)?({DATE})(?:\s*(?:r\.|roku))?\s*$", re.MULTILINE
)
PARTIES_END_RE = re.compile(
    r"^(?:reprezentowan|adres do korespondencji|tel\.|dotyczy|Prezes Krajowej|Krajowa Izba|Wartość|Wpis|Działając)",
    re.IGNORECASE,
)
# The sentence must open with these words: the same phrase inside a subordinate clause
# ("mimo że Zamawiający w dniu ...") describes some other act.
ACTION_RE = re.compile(rf"(?:^|(?<=[.;:] ))Zamawiający\s+w\s+dniu\s+({DATE})")
ALLEGATIONS_START_RE = re.compile(r"Zaskarżonym\s+czynnościom|Zarzut\s+nr\s+1\b")
FIRST_ITEM_RE = re.compile(r"polegających\s+na:\s*1\)\s*(.+?);")
FIRST_ALLEGATION_RE = re.compile(r"Zarzut\s+nr\s+1\b(.+?)(?=Zarzut\s+nr\s+2|$)")
STATUTE_DATE_RE = re.compile(rf"\b(?:ustaw\w*|rozporządzeni\w*|dyrektyw\w*)\s+z\s+dnia\s+{DATE}", re.IGNORECASE)


# Nested fields belong to the current party. Any other labelled line starts
# another section, even if its role is unknown to our output schema.
PARTY_FIELD = re.compile(
    r"^(?:KRS|NIP|REGON|reprezentowan\w* przez|adres do korespondencji|tel\.|e-mail)\b", re.IGNORECASE
)
SECTION_LABEL = re.compile(r"^[^\W\d_][\w ()./-]{0,80}:")
BODY_HEADING = re.compile(r"^(?:uzasadnienie|dowody|żądania|zarzuty|zarzut nr \d+|wnioski|załączniki)\b", re.IGNORECASE)


def _ends_party(line: str) -> bool:
    if PARTY_FIELD.match(line) or line.lower().endswith("składzie:"):
        return False
    return bool(
        SECTION_LABEL.match(line) or BODY_HEADING.match(line) or squash(line).replace(" ", "").upper() == "ODWOŁANIE"
    )


def _first_sentence(text: str) -> str:
    """Stop at sentence punctuation, keeping dots inside citations, dates and company names."""
    for stop in re.finditer(r"[;!?]|\.(?=\s|$)", text):
        if stop[0] == ".":
            before = text[: stop.start()]
            after = text[stop.end() :].lstrip()
            if re.search(r"\b(?:art|ust|pkt|lit|poz|nr|im|ul|św|al|Dz|sygn)$", before, re.IGNORECASE):
                continue
            if after and after[0].islower() and re.search(r"\b(?:sp|o|j|k|p|a|r)$", before, re.IGNORECASE):
                continue
            if re.search(r"\bsp$", before, re.IGNORECASE) and re.match(r"(?:z|j|k|p)\b", after, re.IGNORECASE):
                continue
        return text[: stop.start()]
    return text


CONTACT = re.compile(
    r"^(?:tel(?:efon)?[./ :]|fax|faks|e-?mail|www[.,]|https?://|kontakt\b|osoba do kontaktu)|@", re.IGNORECASE
)
MEMBER = re.compile(r"^(\d+)[.)]\s*(.*)")
MEMBER_ROLE = re.compile(r"\((?:lider|członek|partner)\b[^)]*\)", re.IGNORECASE)
LEAD_FOR = re.compile(r"^prowadząc\w*\s+postępowanie.*(?:na rzecz|w imieniu)", re.IGNORECASE)
CONSORTIUM = re.compile(r"(?:wspólnie|konsorcjum).*[:：]$", re.IGNORECASE)


def _parties(lines: list[str]) -> dict[str, list[dict]]:
    """Keep one name per labelled party or numbered member, through intervening contact lines."""
    parties = {"Zamawiający": [], "Odwołujący": []}
    role = None
    entity = None
    name_lines = []
    sublabel = ""
    wrapped_label = False

    def finish_name():
        nonlocal entity
        if not name_lines:
            return
        name = squash(" ".join(name_lines))
        markers = MEMBER_ROLE.findall(name)
        name = MEMBER_ROLE.sub("", name)
        name = re.split(r",?\s+(?:ul\.|al\.|os\.|pl\.)\s+", name, maxsplit=1, flags=re.IGNORECASE)[0]
        if role == "Odwołujący" or "oddział" not in name.casefold():
            name = re.split(r"\s+z siedzibą\b", name, maxsplit=1, flags=re.IGNORECASE)[0]
        name = name.rstrip(" ,;")
        if name:
            entity = {
                "nazwa": name,
                "sublabel": " ".join([sublabel, *markers]),
                "krs": None,
                "nip": None,
                "regon": None,
            }
            parties[role].append(entity)
        name_lines.clear()

    for line in map(str.strip, lines):
        if label := SECTION_RE.match(line):
            finish_name()
            role = "Zamawiający" if label[1].casefold().startswith("zamawiaj") else "Odwołujący"
            sublabel, entity = "", None
            wrapped_label = ":" not in line
            line = line.partition(":")[2].strip()
            if re.search(r"wspólnie|konsorcjum", line, re.IGNORECASE) and not MEMBER_ROLE.search(line):
                wrapped_label = not line.endswith(":")
                continue
            if not line:
                continue
        if not role or not line:
            continue
        if wrapped_label:
            wrapped_label = not line.endswith(":")
            continue
        if role == "Zamawiający" and LEAD_FOR.match(line):
            finish_name()
            if entity:
                entity["sublabel"] += " prowadzący"
            continue
        if member := MEMBER.match(line):
            finish_name()
            sublabel, entity = member[1], None
            line = member[2]
            if line.endswith(":"):
                sublabel = line
            elif line:
                name_lines.append(line)
            continue
        if (label or sublabel) and re.search(r",\s*(?:ul|al|os|pl)\.", line, re.IGNORECASE) and entity is None:
            name_lines.append(line)
            finish_name()
        elif CONTACT.search(line) or ADDRESS_RE.match(line) or ID_LINE_RE.search(line):
            id_label = ID_LINE_RE.search(line)
            if id_label and entity is None and (name := line[: id_label.start()].strip(" ,;")):
                name_lines.append(name)
            finish_name()
            if entity and ID_LINE_RE.search(line):
                for key, value in registry_ids(line).items():
                    entity[key] = entity[key] or value
        elif PARTIES_END_RE.match(line) or _ends_party(line) or PLACE_DATE_RE.match(line):
            finish_name()
            role = None
        elif CONSORTIUM.search(line):
            name_lines.clear()
        elif entity is None:
            name_lines.append(line)
    finish_name()
    return parties


COUNSEL_LABEL = re.compile(r"^pełnomocnik\s+odwołującego\s*:", re.IGNORECASE)
APPOINTMENT = re.compile(r"reprezentowan\w*\s+prze[zż]\s*:?", re.IGNORECASE)


def _representative(header: str, text: str) -> dict | None:
    """Look for a mandate belonging to the appellant or the signature on the appeal."""
    lines = []
    appellant = False
    for line in map(str.strip, header.splitlines()):
        if label := SECTION_RE.match(line):
            appellant = not label[1].casefold().startswith("zamawiaj")
        elif COUNSEL_LABEL.match(line):
            appellant = True
        elif not (CONTACT.search(line) or APPOINTMENT.match(line)) and _ends_party(line):
            appellant = False
        if appellant:
            lines.append(line)
    block = "\n".join(lines)
    intro = re.search(r"(?im)^pełnomocnik\s+odwołującego\s*:", block) or APPOINTMENT.search(block)
    if intro:
        after = block[intro.end() :].strip()
    elif titled := re.search(r"(?im)^(?:adw\.|r\.\s?pr\.|radca prawny|adwokat)\s+", block):
        after = block[titled.start() :]
    else:
        after = ""
    signature = re.search(
        rf"(?im)^\s*pełnomocnik(?: odwołującego)?\s*\n(?:[^\n]*\d[^\n]*\n)?(?-i:({PERSON}))[ \t]*$", text
    )
    mandate = re.search(
        r"na podstawie (?:udzielonego mi|załączonego) pełnomocnictwa,?\s+(?:wnoszę|składam)\s+odwołanie",
        squash(text),
        re.IGNORECASE,
    )
    if not (intro or after or signature or mandate):
        return None
    appointment = []
    for line in after.splitlines():
        if SECTION_LABEL.match(line) and not re.search(r"z kancelarii:\s*$", line, re.IGNORECASE):
            break
        appointment.append(line)
    if re.search(r"\b(?:prezes\w*|człon\w* zarządu|prokurent\w*)\b", " ".join(appointment[:2]), re.IGNORECASE):
        return None
    appointment_text = " ".join(appointment)
    attorney = ATTORNEY_RE.search(appointment_text)
    if attorney is None and intro:
        attorney = re.match(rf"({PERSON})(?=[,\s(]|$)", appointment_text)
    firm = re.search(
        r"(?:adres do korespondencji|z kancelarii):\s*(.+?)(?=,?\s+(?:ul\.|al\.|pl\.|os\.|z siedzibą)|\nadres)",
        after[:600],
        re.IGNORECASE | re.DOTALL,
    )
    if not firm:
        firm = re.search(r"(?m)^((?:[A-ZĄĆĘŁŃÓŚŹŻ -]+\n)?[Kk]ancelaria[^\n]*)", after)
    mail = EMAIL_RE.search(after)
    return {
        "imie_nazwisko": squash(attorney[1]) if attorney else signature[1] if signature else None,
        "nazwa": squash(firm[1]) if firm else None,
        "mail": mail.group() if mail else None,
    }


def _reason(passage: str) -> int | None:
    passage = passage.lower()
    return next((reason for reason, pattern in REASON_RULES if re.search(pattern, passage)), None)


def _challenged_action(text: str) -> tuple[str | None, int | None]:
    """Use a dated first charge, otherwise its introductory account of the challenged act."""
    flat = squash(text)
    charge = FIRST_ALLEGATION_RE.search(flat)
    opening = _first_sentence(charge.group(1)) if charge else ""
    reason = _reason(opening)
    dated_act = re.split(
        r",?\s+(?:o czym|odwołanie|pismo (?:wniesiono|nadano))\b", opening, maxsplit=1, flags=re.IGNORECASE
    )[0]
    day = find_date(STATUTE_DATE_RE.sub("", dated_act))
    if reason and day:
        return day, reason

    introduction = ALLEGATIONS_START_RE.split(flat, maxsplit=1)[0]
    for action in reversed(list(ACTION_RE.finditer(introduction))):
        sentence = _first_sentence(introduction[action.start() :])
        action_reason = _reason(sentence)
        if action_reason:
            if (
                reason
                and reason != action_reason
                and re.match(
                    r"^[\s:–—-]*(?:odrzuceni|wykluczeni|zaniechani|unieważnieni|wybór)", opening, re.IGNORECASE
                )
            ):
                return None, reason
            return to_iso(action.group(1)), action_reason
    item = FIRST_ITEM_RE.search(introduction)
    if item:
        item_opening = _first_sentence(item.group(1))
        item_reason = _reason(item_opening)
        if item_reason:
            return find_date(item_opening), item_reason
    if charge or reason:
        return None, reason
    return prose_action(text)


def _procurement(text: str) -> dict:
    bzp = re.search(r"(\d{4})/BZP\s?(\d{8}(?:/\d{2})?)", text)
    ted = re.search(r"(?P<year>\d{4})/S\s*\d{3}-(?P<number>\d{6})", text) or re.search(
        r"(?<![\d/\-])(?P<number>\d{6})[ \t]*[-–—][ \t]*(?P<year>\d{4})(?!\d)", text
    )
    ref_label = re.search(
        r"(?:(?:nr|numer)\s+(?:referencyjny(?:\s+sprawy)?|postępowania|sprawy|zamówienia)|znak(?: sprawy)?)\b[:\s]+",
        text,
        re.IGNORECASE,
    ) or re.search(r"postępowani[uea]\s+(?:nr|numer)\b[:\s]+", text, re.IGNORECASE)
    reference = None
    if ref_label:
        value = text[ref_label.end() :].lstrip()
        if not SECTION_LABEL.match(value):
            reference = re.match(r"(?=\S*\d)[\w./-]+", value)
    title = re.search(r"pn\.:?\s*„([^”]+)”", text)
    if not title and (subject := re.search(r"\bdotyczy\b[ \t]*:?", text, re.IGNORECASE)):
        lines = []
        for line in text[subject.end() :].splitlines():
            if SECTION_LABEL.match(line.strip()):
                break
            lines.append(line)
        title = re.search(r"„([^”]+)”", " ".join(lines))
    if not title:
        title = re.search(
            r'(?:przedmiot(?:em)? (?:zamówienia|jest)|pod nazwą|pn\.)[.:\s]*[„"](.{1,700}?)[”"’\'](?=,|\s|$)',
            text,
            re.IGNORECASE | re.DOTALL,
        )
    if not title:
        title = re.search(
            r"(?:nazwa postępowania:\s*|postępowaniu na:\s*)(.{1,700}?)(?=\s*\((?:nr|numer) sprawy|,\s*ogłoszon)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    return {
        "numer_bzp": f"{bzp.group(1)}/BZP{bzp.group(2)}" if bzp else None,
        "numer_postepowania": reference[0].rstrip(".,") if reference else None,
        "numer_ted": f"{ted['number']}-{ted['year']}" if ted else None,
        "tytul": squash(title.group(1)) if title else None,
    }


def _appellant_registry(text: str, leader: dict) -> None:
    """Fill absent IDs from an explicit self-identification naming the same appellant."""
    flat = squash(text)
    for match in re.finditer(re.escape(leader["nazwa"]), flat, re.IGNORECASE):
        tail = flat[match.end() : match.end() + 550]
        marker = re.search(r"\(dalej(?: jako)?[ :„\"]+odwołujący[”\"]", tail, re.IGNORECASE)
        if marker and not re.search(
            r"(?:zamawiający|pełnomocnik|odwołujący)\s*:", tail[: marker.start()], re.IGNORECASE
        ):
            for key, value in registry_ids(tail[: marker.start()]).items():
                leader[key] = leader[key] or value
            return


def extract(text: str) -> dict:
    header = text.split("Działając w imieniu", 1)[0]
    parties = _parties(header.splitlines())
    place_date = PLACE_DATE_RE.search(header)
    action_date, reason = _challenged_action(text)
    representative = _representative(header, text)

    appellants = parties["Odwołujący"]
    leader = next((a for a in appellants if "lider" in a["sublabel"].lower()), appellants[0] if appellants else None)
    if leader:
        _appellant_registry(text, leader)
    authorities = parties["Zamawiający"]
    return {
        "OdwolanieKIO": {
            "data": to_iso(place_date.group(2)) if place_date else None,
            "czynnosc_dzien": action_date,
            "czynnosc_powod_id": reason,
            "czynnosc_opis": REASONS.get(reason),
            "miejscowosc": place_date.group(1) if place_date else None,
        },
        "Odwolujacy": [
            {
                "krs": leader["krs"],
                "nazwa": leader["nazwa"],
                "nip": leader["nip"],
                "regon": leader["regon"],
                "przez-pelnomocnika": 1 if representative else 0,
                "pelnomocnik": representative or {"imie_nazwisko": None, "nazwa": None, "mail": None},
            }
        ]
        if leader
        else [],
        "Zamawiajacy": [
            {
                "krs": a["krs"],
                "nazwa": a["nazwa"],
                "nip": a["nip"],
                "regon": a["regon"],
                "prowadzacy_postepowanie": None
                if len(authorities) < 2
                else int(bool(re.search(r"prowadząc|lider", a["sublabel"], re.IGNORECASE))),
            }
            for a in authorities
        ],
        "ZamowieniePubliczne": _procurement(text),
    }
