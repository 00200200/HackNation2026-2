"""Appeal to KIO -> OdwolanieKIO, Odwolujacy[], Zamawiajacy[], ZamowieniePubliczne."""

import re

from .common import ATTORNEY_RE, DATE, EMAIL_RE, LOWER, UPPER, find_date, registry_ids, squash, to_iso

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

SECTION_RE = re.compile(r"^(Zamawiający|Odwołujący)\s*[:(](.*)$", re.IGNORECASE)
ADDRESS_RE = re.compile(r"^(?:ul\.|al\.|pl\.|os\.|\d{2}-\d{3}\b)")
ID_LINE_RE = re.compile(r"\b(?:KRS|NIP|REGON)\b")
_PLACE = rf"[{UPPER}][{LOWER}]+(?:[ \-][{UPPER}][{LOWER}]+){{0,2}}"
PLACE_DATE_RE = re.compile(rf"^({_PLACE}),?\s+(?:(?:dnia|dn\.)\s+)?({DATE})(?:\s*(?:r\.|roku))?\s*$", re.MULTILINE)
PARTIES_END_RE = re.compile(
    r"^(?:reprezentowan|adres do korespondencji|tel\.|dotyczy|Prezes Krajowej|Krajowa Izba|Wartość|Wpis|Działając)",
    re.IGNORECASE,
)
# The sentence must open with these words: the same phrase inside a subordinate clause
# ("mimo że Zamawiający w dniu ...") describes some other act.
ACTION_RE = re.compile(rf"(?:^|(?<=[.;:] ))Zamawiający\s+w\s+dniu\s+({DATE})")
# A full stop after a word of three letters or more, or a doubled one after "sp.j..".
SENTENCE_END_RE = re.compile(rf"(?:(?<=[{UPPER}{LOWER})]{{3}})\.|\.\.)\s+(?=[{UPPER}])")
ALLEGATIONS_START_RE = re.compile(r"Zaskarżonym\s+czynnościom|Zarzut\s+nr\s+1\b")
FIRST_ITEM_RE = re.compile(r"polegających\s+na:\s*1\)\s*(.+?);")
FIRST_ALLEGATION_RE = re.compile(r"Zarzut\s+nr\s+1\b(.+?)(?=Zarzut\s+nr\s+2|$)")
CHARGE_END_RE = re.compile(r"[;!?]|(?<=[\w]{3})\.(?<!art\.)(?<!ust\.)(?<!pkt\.)(?<!lit\.)\s+", re.IGNORECASE)
STATUTE_DATE_RE = re.compile(rf"\b(?:ustaw\w*|rozporządzeni\w*|dyrektyw\w*)\s+z\s+dnia\s+{DATE}", re.IGNORECASE)


def _parties(lines: list[str]) -> dict[str, list[dict]]:
    """Party blocks from the header: a name, then an address line, then a KRS/NIP/REGON line."""
    parties = {"Zamawiający": [], "Odwołujący": []}
    section = None
    in_wrapped_label = False
    sublabel = ""
    name_lines = []

    def finish_name():
        if section and name_lines:
            parties[section].append(
                {"nazwa": squash(" ".join(name_lines)), "sublabel": sublabel, "krs": None, "nip": None, "regon": None}
            )
        name_lines.clear()

    for line in map(str.strip, lines):
        label = SECTION_RE.match(line)
        if label:
            finish_name()
            section, sublabel = label.group(1).capitalize(), ""
            inline_name = line.split(":", 1)[1].strip() if ":" in line else ""
            name_lines = [inline_name] if inline_name else []
            in_wrapped_label = ":" not in line
            continue
        if section is None:
            continue
        if in_wrapped_label:
            in_wrapped_label = not line.endswith(":")
            continue
        heading = re.sub(r"\s", "", line).upper()
        if PARTIES_END_RE.match(line) or heading == "ODWOŁANIE" or PLACE_DATE_RE.match(line):
            finish_name()
            section = None
        elif line.endswith(":"):
            if re.match(r"\d+[).]", line):
                finish_name()
                sublabel = line
            elif name_lines:
                name_lines = []  # tail of a label that wrapped onto this line
            else:
                section = None  # a block for some other party
        elif ADDRESS_RE.match(line) or ID_LINE_RE.search(line):
            finish_name()
            if parties[section] and ID_LINE_RE.search(line):
                entity = parties[section][-1]
                for key, value in registry_ids(line).items():
                    entity[key] = entity[key] or value
        elif "@" in line or (
            parties[section]
            and not name_lines
            and sublabel == parties[section][-1]["sublabel"]
            and any(parties[section][-1][k] for k in ("krs", "nip", "regon"))
            and re.fullmatch(r"[\w+%©®.-]+\.[a-zA-Z]{2,}", line)
        ):
            finish_name()
        elif line:
            name_lines.append(line)
    finish_name()
    return parties


def _representative(text: str) -> dict | None:
    """The appellant's first-named attorney, the firm in the correspondence address, and its e-mail."""
    # Restrict correspondence details to the appellant's own party block.
    lines = []
    appellant = False
    for line in text.splitlines():
        label = SECTION_RE.match(line.strip())
        if label:
            appellant = label.group(1).casefold() == "odwołujący"
        elif (
            re.match(r"\s*(?:Wykonawca wybrany|dotyczy)", line, re.IGNORECASE)
            or squash(line).replace(" ", "").upper() == "ODWOŁANIE"
        ):
            appellant = False
        if appellant:
            lines.append(line)
    text = "\n".join(lines)
    intro = re.search(r"reprezentowan\w*\s+przez:?", text, re.IGNORECASE)
    if not intro:
        return None
    after = text[intro.end() :]
    attorney = ATTORNEY_RE.search(after[:300])
    firm = re.search(r"adres do korespondencji:\s*(.+?),\s*(?:ul\.|al\.|pl\.|os\.)", after[:600], re.DOTALL)
    mail = EMAIL_RE.search(after[:800])
    return {
        "imie_nazwisko": squash(attorney.group(1)) if attorney else None,
        "nazwa": squash(firm.group(1)) if firm else None,
        "mail": mail.group() if mail else None,
    }


def _reason(passage: str) -> int | None:
    passage = passage.lower()
    return next((reason for reason, pattern in REASON_RULES if re.search(pattern, passage)), None)


def _challenged_action(text: str) -> tuple[str | None, int | None]:
    """Use a dated first charge, otherwise its introductory account of the challenged act."""
    flat = squash(text)
    charge = FIRST_ALLEGATION_RE.search(flat)
    opening = CHARGE_END_RE.split(charge.group(1), maxsplit=1)[0] if charge else ""
    reason = _reason(opening)
    day = find_date(STATUTE_DATE_RE.sub("", opening))
    if reason and day:
        return day, reason

    introduction = ALLEGATIONS_START_RE.split(flat, maxsplit=1)[0]
    for action in reversed(list(ACTION_RE.finditer(introduction))):
        sentence = SENTENCE_END_RE.split(introduction[action.start() :], maxsplit=1)[0]
        action_reason = _reason(sentence)
        if action_reason:
            return to_iso(action.group(1)), action_reason
    item = FIRST_ITEM_RE.search(introduction)
    if item:
        item_opening = SENTENCE_END_RE.split(item.group(1), maxsplit=1)[0]
        item_reason = _reason(item_opening)
        if item_reason:
            return find_date(item_opening), item_reason
    return None, reason


def _procurement(text: str) -> dict:
    bzp = re.search(r"(\d{4})/BZP\s?(\d{8}(?:/\d{2})?)", text)
    ted = re.search(r"(?P<year>\d{4})/S\s*\d{3}-(?P<number>\d{6})", text) or re.search(
        r"(?<![\d/\-])(?P<number>\d{6})-(?P<year>\d{4})(?!\d)", text
    )
    reference = re.search(
        r"(?:nr|numer)\s+(?:referencyjny(?:\s+sprawy)?|postępowania|sprawy):?\s*(\S+)", text
    ) or re.search(r"postępowani[ea]\s+(?:nr|numer)\s+(\S+)", text)
    title = re.search(r"pn\.:?\s*„(.+?)”", text, re.DOTALL) or re.search(
        r"dotyczy.*?„(.+?)”", text, re.DOTALL | re.IGNORECASE
    )
    return {
        "numer_bzp": f"{bzp.group(1)}/BZP{bzp.group(2)}" if bzp else None,
        "numer_postepowania": reference.group(1).rstrip(",.;)") if reference else None,
        "numer_ted": f"{ted['number']}-{ted['year']}" if ted else None,
        "tytul": squash(title.group(1)) if title else None,
    }


def extract(text: str) -> dict:
    header = text.split("Działając w imieniu", 1)[0]
    parties = _parties(header.splitlines())
    place_date = PLACE_DATE_RE.search(header)
    action_date, reason = _challenged_action(text)
    representative = _representative(header)

    appellants = parties["Odwołujący"]
    leader = next((a for a in appellants if "lider" in a["sublabel"].lower()), appellants[0] if appellants else None)
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
