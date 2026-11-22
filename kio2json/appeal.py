"""Appeal to KIO -> OdwolanieKIO, Odwolujacy[], Zamawiajacy[], ZamowieniePubliczne."""

import re

from .appeal_charges import ACTS, CHARGE, FILING, NEXT_ITEM, act_date, first_sentence, prose_action, sentences
from .common import ATTORNEY_RE, DATE, EMAIL_RE, LOWER, PERSON, UPPER, registry_ids, squash, to_iso
from .personal_names import nominative, same_nominal_form

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

APPELLANT_LABEL = r"Odwo[łl]uj[ąa]cy"
EXPLICIT_APPELLANT = re.compile(rf"(?im)^[ \t]*{APPELLANT_LABEL}[ \t]*[:(]")
# A standalone role heading opens the same party card as a colon-labelled field.
FORM_ROLE = re.compile(
    r"(?im)^[ \t]*(?:(?P<appellant>odwo[łl]uj[ąa]cy)|(?P<authority>zamawiaj[ąa]cy))[ \t]*(?::[ \t]*|$)"
)
SECTION_RE = re.compile(rf"^(Zamawiaj[ąa]cy|{APPELLANT_LABEL}|Wykonawca)\s*[:(]", re.IGNORECASE)
ADDRESS_RE = re.compile(r"^(?:ul\.|al\.|pl\.|os\.|\d{2}\s*[-–—]\s*\d{3}\b)|^[^,]{2,40},\s*(?:ul\.|al\.)", re.IGNORECASE)
INLINE_STREET = re.compile(r",\s*(?:ul|al|os|pl)\.", re.IGNORECASE)
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
FIRST_CHARGE_HEADING = re.compile(
    r"(?im)^[ \t]*(?:zarzut (?:pierwszy|(?:nr )?1|I)|pierwszy zarzut)[ \t]*[:.)–—-]?[ \t]*$"
)
AUTHORITY_ACT = re.compile(
    rf"^zamawiaj[ąa]cy\s*(?:(?:w dniu|dnia)\s+({DATE})\s*(?:roku|r\.?)?\s*)?"
    r"(?=(?:nie\s+)?(?:odrzucił|wykluczył|unieważnił|zaniechał|wybrał|dokonał|ogłosił|"
    r"opublikował|udzielił|przedstawił|udostępnił|zmienił|zmodyfikował)\b)",
    re.IGNORECASE,
)
# After a reporting verb, the grammatical object names the act. A later
# mention of a bid in a sentence about a different object is insufficient.
REPORTING_VERB = re.compile(r"^(?:dokonał|ogłosił|opublikował|udzielił|przedstawił|udostępnił)\s+", re.IGNORECASE)
ACTION_OBJECTS = {
    **ACTS,
    2: rf"(?:{ACTS[2]}|wybrał\s+(?:najkorzystniejsz\w*\s+)?ofert\w*)",
    3: r"wyklucz\w*\s+(?:wykonawc|odwołując|przedsiębiorc|oferent)\w*",
    5: r"(?:z?modyfik\w*|zmian\w*|zmienił)\s+(?:(?:treś[ćc]i?|postanowieni\w*)\s+)?(?:si?wz\b|specyfikacj\w*)",
    12: rf"(?:projektowan\w*\s+)?(?:{ACTS[12]})",
}
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
BODY_HEADING = re.compile(
    r"^(?:[IVXLCDM]+[.)]\s+)?(?:odpowiedź zamawiającego|stan faktyczny|okoliczności sprawy|uzasadnienie|dowody|żądania|zarzuty|zarzut nr \d+|wnioski|(?P<attachments>załączniki))\b",
    re.IGNORECASE,
)


# Only the grammatical head can name the owner. A genitive after "rachunek" or
# "pełnomocnik" describes someone else's account or counsel.
CARD_HEAD = r"(?:dane(?: identyfikacyjne| teleadresowe)?|(?:pełna )?nazwa(?: i (?:adres|siedziba))?|oznaczenie)"
_FILER = r"(?:(?:wykonawca|podmiot) (?:wnosz|składaj)[ąa]cy|strona (?:wnosz|składaj)[ąa]ca) odwo[łl]anie"
# Inflect the role and its modifier together. A description such as "conducting
# the proceedings" identifies the buyer only when it modifies the party noun.
_PROCEEDING = r"post[ęe]powanie(?: o udzielenie zam[óo]wienia(?: publicznego)?)?"


def _buyer_modifier(ending: str) -> str:
    return (
        rf"(?:zamawiaj[ąa]c{ending}|(?:prowadz|przeprowadzaj|organizuj)[ąa]c{ending} {_PROCEEDING}|"
        rf"udzielaj[ąa]c{ending} zam[óo]wienia(?: publicznego)?)"
    )


_BUYER_NOM = (
    rf"(?:podmiot {_buyer_modifier('y')}|(?:instytucja|jednostka|strona) {_buyer_modifier('a')}|"
    r"organizator post[ęe]powania)"
)
_BUYER_GEN = (
    rf"(?:podmiotu {_buyer_modifier('ego')}|(?:instytucji|jednostki|strony) {_buyer_modifier('ej')}|"
    r"organizatora post[ęe]powania|zamawiaj[ąa]cego)"
)
_JOINT = rf"(?:wsp[óo]lni zamawiaj[ąa]cy|zamawiaj[ąa]cy wsp[óo]lnie|(?:podmioty|jednostki|instytucje) (?:wsp[óo]lnie )?{_buyer_modifier('e')})"
_JOINT_GEN = rf"(?:zamawiaj[ąa]cych(?: wsp[óo]lnie)?|(?:podmiot[óo]w|jednostek|instytucji) (?:wsp[óo]lnie )?{_buyer_modifier('ych')})"
_BUYER_LEAD = rf"zamawiaj[ąa]cy (?:prowadz[ąa]cy {_PROCEEDING}|wiod[ąa]cy)|lider zamawiaj[ąa]cych"
_LEADS_PROCEEDING = re.compile(r"\b(?:(?:prowadz|przeprowadzaj)[ąa]c(?:y|a|ego|ej)|wiod[ąa]cy|lider)\b", re.IGNORECASE)
_CARD_WORDING = (
    rf"(?:(?P<appellant>{CARD_HEAD} odwo[łl]uj[ąa]cego|{_FILER}|"
    rf"{CARD_HEAD} (?:wykonawcy|podmiotu) (?:wnosz|składaj)[ąa]cego odwo[łl]anie)|"
    rf"(?P<authority>{CARD_HEAD} (?:{_BUYER_GEN}|{_JOINT_GEN})|{_BUYER_NOM}|{_JOINT}|{_BUYER_LEAD}|"
    rf"zamawiaj[ąa]cy[ \t]*\({CARD_HEAD}\)))"
)
CARD_ROLE = re.compile(rf"^{_CARD_WORDING}(?:[ \t]*:[ \t]*|[ \t]*$)", re.IGNORECASE)
# In a flat transcript the caption in the adjacent column can follow immediately.
PARALLEL_CARD = re.compile(rf"^{_CARD_WORDING}(?=[: \t]|$)", re.IGNORECASE | re.MULTILINE)
_OTHER_CARD = re.compile(
    r"^(?:(?:pełnomocnik|rachunek|odpowiedź) zamawiającego|wybrany wykonawca|wykonawca wybrany|wykonawca, którego ofertę wybrano|"
    r"(?:dane )?(?:przystępując(?:y|ego)|uczestnik(?:a)?(?: postępowania)?))(?:\s*:|$)",
    re.IGNORECASE,
)
_QUOTE_INTRO = re.compile(
    r'^(?:cytat\b|[„«"]$)|[„«]\s*$|\b(?:wskazał|napisał|podał|stwierdził|przytoczono|zacytowano)\w*\s*:\s*(?:[„«"]|$)',
    re.IGNORECASE,
)
_ORGANIZATION = re.compile(
    r"(?i:\b(?:sp\.\s*(?:z|j|k)\b|s\.a\.|spółka (?:akcyjna|jawna|komandytowa|z ograniczoną)|konsorcjum\b))|"
    rf"^(?i:gmina|miasto|powiat|województwo|starostwo|sąd|urząd|ministerstwo|szpital|uniwersytet|muzeum|związek|zarząd)\s+[{UPPER}]"
)


def _ends_party(line: str) -> bool:
    if PARTY_FIELD.match(line) or line.lower().endswith("składzie:"):
        return False
    return bool(
        CARD_ROLE.fullmatch(line)
        or SECTION_LABEL.match(line)
        or _OTHER_CARD.match(line)
        or BODY_HEADING.match(line)
        or squash(line).replace(" ", "").upper() == "ODWOŁANIE"
    )


CONTACT = re.compile(
    r"^(?:(?:tel(?:efon)?|fax|faks|e-?mail|kontakt|osoba do kontaktu)\s*(?::|\.?\s*[+(]?\d[\d ().-]{5,}\b)|www[.,]|https?://)|@",
    re.IGNORECASE,
)
MEMBER = re.compile(r"^(\d+)[.)]\s*(.*)")
MEMBER_ROLE = re.compile(r"\((?:lider|członek|partner)\b[^)]*\)", re.IGNORECASE)
AUTHORITY_LEAD_MARK = re.compile(rf"\((?:zamawiaj[ąa]cy )?(?:prowadz[ąa]cy {_PROCEEDING}|wiod[ąa]cy)\)", re.IGNORECASE)
LEAD_FOR = re.compile(
    r"^(?:prowadząc\w*\s+postępowanie.*(?:na rzecz|w imieniu)|"
    r"działając\w*\s+(?:we?\s+(?:własnym imieniu|imieniu (?:własnym|swoim))\s+(?:i|oraz)\s+)?na rzecz\s*:)",
    re.IGNORECASE,
)
CONSORTIUM = re.compile(r"\b(?:wspólnie|konsorcjum)\b", re.IGNORECASE)


def party_evidence(rows: list[str], *, numbered: bool = False) -> bool:
    """A name and local address/register, or an explicit organization name, support a card."""
    rows = [r.strip() for r in rows if r.strip()]
    if not rows:
        return False
    if numbered and (member := MEMBER.match(rows[0])):
        end = next((i for i, row in enumerate(rows[1:], 1) if MEMBER.match(row)), len(rows))
        rows = [row for row in [member[2], *rows[1:end]] if row]
        if not rows:
            return False
    if (identifier := ID_LINE_RE.search(rows[0])) and identifier.start() and any(registry_ids(rows[0]).values()):
        # An inline registry field is evidence for the name printed to its left.
        rows = [rows[0][: identifier.start()].rstrip(" ,;"), rows[0][identifier.start() :], *rows[1:]]
    first = rows[0]
    if (
        CARD_ROLE.match(first)
        or _ends_party(first)
        or CONTACT.search(first)
        or re.match(r"(?i)^(?:adw\.|r\.\s?pr\.|radca prawny|adwokat)\s", first)
    ):
        return False
    if (
        not first
        or not (first[0].isupper() or CONSORTIUM.search(first))
        or (ADDRESS_RE.match(first) and not INLINE_STREET.search(first))
        or ID_LINE_RE.match(first)
    ):
        return False
    for index, line in enumerate(rows):
        if index and (_ends_party(line) or CARD_ROLE.match(line) or PARTIES_END_RE.match(line)):
            break
        if _ORGANIZATION.search(line) or ADDRESS_RE.match(line) or any(registry_ids(line).values()):
            return True
    return False


def party_header_end(line: str) -> bool:
    return bool(BODY_HEADING.match(line) or _QUOTE_INTRO.search(line))


def _party_header(header: str) -> tuple[str, set[int]]:
    lines = header.splitlines()
    leads = set()
    changed = False
    for index, line in enumerate(lines):
        line = line.strip()
        if party_header_end(line):
            if changed:
                return "\n".join(lines[:index]), leads
            break
        if (label := CARD_ROLE.match(line)) and party_evidence(
            [line[label.end() :], *lines[index + 1 : index + 6]], numbered=bool(label["authority"])
        ):
            name = "Odwołujący" if label["appellant"] else "Zamawiający"
            if label["authority"] and _LEADS_PROCEEDING.search(label["authority"]):
                leads.add(index)
            lines[index] = name + ": " + line[label.end() :]
            changed = True
    return ("\n".join(lines) if changed else header), leads


def _unquoted_party_text(text: str) -> str:
    """Keep signature and filing evidence outside an explicitly quoted statement."""
    kept = []
    closing = None
    for line in text.splitlines():
        if closing:
            if closing in line:
                closing = None
            continue
        if _QUOTE_INTRO.search(line.strip()):
            opener = re.search(r'[„«"]', line)
            if opener is None:
                break  # The quotation has no printed closing delimiter.
            closing = {"„": "”", "«": "»", '"': '"'}[opener[0]]
            if closing in line[opener.end() :]:
                closing = None
            continue
        kept.append(line)
    return "\n".join(kept)


def _party_role(label: str, explicit_appellant: bool) -> str | None:
    if label.casefold().startswith("zamawiaj"):
        return "Zamawiający"
    if explicit_appellant and label.casefold() == "wykonawca":
        return None
    return "Odwołujący"


def _regional_name(name: str, lead: str) -> str:
    """Use the lead's printed nominative for the same institution in a different locality."""
    member = re.fullmatch(r"(.+?) (w|we) (.+)", name)
    model = re.fullmatch(r"(.+?) (?:w|we) .+", lead)
    if member and model:
        words, exemplar = member[1].split(), model[1].split()
        if len(words) == len(exemplar) and all(
            left == right or same_nominal_form(left, right) for left, right in zip(words, exemplar, strict=True)
        ):
            return f"{model[1]} {member[2]} {member[3]}"
    return name


def _parties(
    lines: list[str],
    ocr_mail_lines: frozenset[int],
    explicit_appellant: bool,
    *,
    inflected: bool = False,
    lead_rows: set[int] | frozenset[int] = frozenset(),
) -> dict[str, list[dict]]:
    """Keep one name per labelled party or numbered member, through intervening contact lines."""
    parties = {"Zamawiający": [], "Odwołujący": []}
    role = None
    entity = None
    name_lines = []
    sublabel = ""
    wrapped_label = False
    in_body = False

    def finish_name():
        nonlocal entity
        if not name_lines:
            return
        name = squash(" ".join(name_lines))
        markers = MEMBER_ROLE.findall(name)
        if role == "Zamawiający" and AUTHORITY_LEAD_MARK.search(name):
            markers.append("prowadzący")
            name = AUTHORITY_LEAD_MARK.sub("", name)
        name = MEMBER_ROLE.sub("", name)
        name = re.split(r",?\s+(?:ul\.|al\.|os\.|pl\.)\s+", name, maxsplit=1, flags=re.IGNORECASE)[0]
        # A registered seat may be inserted before a separately delimited branch designation.
        name = re.sub(
            r",?\s+z siedzibą\b.*?(?=[,–—-]\s*(?:oddział|filia|delegatura)\b|$)", "", name, flags=re.IGNORECASE
        )
        name = name.rstrip(" ,;")
        if name and role == "Zamawiający" and sublabel.isdigit() and parties[role]:
            lead = parties[role][0]
            if "prowadzący" in lead["sublabel"]:
                name = _regional_name(name, lead["nazwa"])
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

    for index, line in enumerate(map(str.strip, lines)):
        # Electronic cover sheets can list attachments before their explicit party cards.
        boundary = BODY_HEADING.match(line)
        if _QUOTE_INTRO.search(line) or (boundary and (not boundary["attachments"] or role or any(parties.values()))):
            in_body = True
            if role == "Zamawiający":
                finish_name()
                role = None
        # A marginal lead marker between consecutive members belongs to the preceding card.
        if (
            role == "Zamawiający"
            and sublabel.isdigit()
            and (
                (index in lead_rows and FORM_ROLE.fullmatch(line))
                or (CARD_ROLE.fullmatch(line) and _LEADS_PROCEEDING.search(line))
            )
            and index + 1 < len(lines)
            and (following := MEMBER.match(lines[index + 1].strip()))
            and len(sublabel) <= 6
            and following[1] == str(int(sublabel) + 1)
        ):
            finish_name()
            if entity:
                entity["sublabel"] += " prowadzący"
            continue
        if _OTHER_CARD.match(line) or CARD_ROLE.match(line):
            finish_name()
            role = None
            continue
        if label := SECTION_RE.match(line):
            finish_name()
            role = _party_role(label[1], explicit_appellant)
            if in_body and role == "Zamawiający":
                role = None
                continue
            sublabel, entity = "prowadzący" if index in lead_rows else "", None
            wrapped_label = ":" not in line
            line = line.partition(":")[2].strip()
            if not line:
                continue
        if not role or not line:
            continue
        if wrapped_label:
            wrapped_label = not line.endswith(":")
            continue
        if (
            role == "Zamawiający"
            and not (name_lines or entity)
            and (nested := re.match(r"nazwa zamawiającego:\s*(.+)", line, re.IGNORECASE))
        ):
            name_lines.append(nested[1])
            continue
        if role == "Zamawiający" and LEAD_FOR.match(line):
            finish_name()
            if entity:
                entity["sublabel"] += " prowadzący"
            continue
        if member := MEMBER.match(line):
            # The numbered row supplies the evidence that the preceding text introduces a list.
            if (
                not sublabel
                and CONSORTIUM.search(" ".join(name_lines))
                and not MEMBER_ROLE.search(" ".join(name_lines))
            ):
                name_lines.clear()
            finish_name()
            sublabel, entity = member[1], None
            line = member[2]
            if _OTHER_CARD.match(line):
                role = None
                continue
            if line.endswith(":"):
                sublabel = line
                continue
            # Read a member's inline name and register with the ordinary value-row parser.
            if not ID_LINE_RE.search(line):
                if line:
                    name_lines.append(line)
                continue
        if entity is None and (label or sublabel or (inflected and not name_lines)) and INLINE_STREET.search(line):
            name_lines.append(line)
            finish_name()
            if entity and ID_LINE_RE.search(line):
                entity.update({key: value for key, value in registry_ids(line).items() if value})
        elif CONTACT.search(line) or ADDRESS_RE.match(line) or ID_LINE_RE.search(line):
            id_label = ID_LINE_RE.search(line)
            if id_label and entity is None and (name := line[: id_label.start()].strip(" ,;")):
                name_lines.append(name)
            finish_name()
            if entity and ID_LINE_RE.search(line):
                for key, value in registry_ids(line).items():
                    entity[key] = entity[key] or value
        elif (
            role == "Zamawiający"
            and sublabel.isdigit()
            and index + 2 < len(lines)
            and re.fullmatch(r"\s*\d+\s*/\s*\d+\s*", lines[index + 1])
            and (following := MEMBER.match(lines[index + 2].strip()))
            and len(sublabel) <= 6
            and following[1] == str(int(sublabel) + 1)
        ):
            # A printed footer before the page counter interrupts a continuing list.
            finish_name()
        elif index in ocr_mail_lines and entity and not name_lines and any(entity[k] for k in ("krs", "nip", "regon")):
            continue
        elif label or (CONSORTIUM.search(line) and line.endswith((":", "："))):
            name_lines.append(line)
        elif PARTIES_END_RE.match(line) or _ends_party(line) or CHARGE.search(line) or PLACE_DATE_RE.match(line):
            finish_name()
            role = None
        elif entity is None:
            name_lines.append(line)
    finish_name()
    return parties


COUNSEL_LABEL = re.compile(r"^pełnomocnik\s+odwołującego\s*:", re.IGNORECASE)
APPOINTMENT = re.compile(r"(?:reprezentowan|zastępowan)\w*\s+prze[zż]\s*(?:pełnomocnika\s*)?:?", re.IGNORECASE)


EMPLOYER_LABEL = re.compile(
    r"^(?:pracodawca|kancelaria|(?:z |nazwa )kancelarii|adres do korespondencji)\s*:[ \t]*(.*)", re.IGNORECASE
)
FIRM_NAME = re.compile(r"^(?:kancelaria|biuro prawne)\b", re.IGNORECASE)


def _prose_parties(text: str, parties: dict) -> None:
    """Fill missing roles only from a clause that actually files the appeal."""
    for clause in sentences(squash(text)):
        filing = FILING.search(clause)
        if not filing:
            continue
        roles = {
            "Odwołujący": r"\bw imieniu\s+(?:spółki\s+)?",
            "Zamawiający": r"\b(?:wobec czynności zamawiającego|postępowani\w* prowadzon\w* przez)\s+",
        }
        for role, cue in roles.items():
            if parties[role]:
                continue
            match = re.search(cue, clause, re.IGNORECASE)
            if not match:
                continue
            name = re.split(
                r"[,;:]|\s+(?:wobec|wnosz\w*|wnosi|składa\w*|jako|z siedzibą|w postępowaniu)\b",
                clause[match.end() :],
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()
            if name and name[0].isupper():
                parties[role].append({"nazwa": name, "sublabel": "", "nip": None, "krs": None, "regon": None})


def _employer(after: str) -> str | None:
    details = after.splitlines()
    for i, line in enumerate(details):
        field = EMPLOYER_LABEL.match(line)
        value = field[1].strip() if field else line.strip()
        if field:
            for following in details[i + 1 :]:
                if SECTION_LABEL.match(following) or CONTACT.search(following) or ID_LINE_RE.search(following):
                    break
                if ADDRESS_RE.match(following) and not re.search(r",\s*(?:ul\.|al\.)", following, re.IGNORECASE):
                    break
                if re.search(r"(?:^|\s)(?:ul\.|al\.|pl\.|os\.)", value, re.IGNORECASE):
                    break
                value = squash(value + " " + following)
        candidate = re.split(
            r",?\s+(?:ul\.|al\.|pl\.|os\.|z siedzibą)(?:\s|$)", value, maxsplit=1, flags=re.IGNORECASE
        )[0]
        if not candidate or SECTION_LABEL.match(candidate) or ADDRESS_RE.match(candidate) or CONTACT.search(candidate):
            continue
        if FIRM_NAME.match(candidate) or (field and (candidate != value or not field[0].lower().startswith("adres"))):
            return candidate.rstrip(" ,;")
    return None


def _representative(header: str, text: str, appellant_name: str, explicit_appellant: bool) -> dict | None:
    """Look for a mandate belonging to the appellant or the signature on the appeal."""
    lines = []
    appellant = False
    for line in map(str.strip, header.splitlines()):
        if label := SECTION_RE.match(line):
            appellant = _party_role(label[1], explicit_appellant) == "Odwołujący"
        elif _OTHER_CARD.match(line):
            appellant = False
        elif COUNSEL_LABEL.match(line):
            appellant = True
        elif _ends_party(line) and not (
            CONTACT.search(line)
            or APPOINTMENT.match(line)
            or EMPLOYER_LABEL.match(line)
            or re.search(r"\b(?:KRS|NIP|REGON)\b", line.partition(":")[0])
        ):
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
        rf"(?im)^[ \t]*pełnomocnik(?: odwołującego)?[ \t]*\n(?:[^\n]*\d[^\n]*\n)?(?-i:({PERSON}))[ \t]*$", text
    )
    principal = rf"(?:odwołującego|{re.escape(appellant_name)})(?!\w)"
    mandate = any(
        FILING.search(clause)
        and re.search(rf"\b(?:w imieniu (?:spółki )?|jako pełnomocnik ){principal}", clause, re.IGNORECASE)
        and re.search(r"\b(?:pełnomocnictw\w*|pełnomocnik|radca prawny|adwokat)\b", clause, re.IGNORECASE)
        for clause in sentences(squash(text))
    )
    if not (intro or after or signature or mandate):
        return None
    appointment = []
    for line in after.splitlines():
        if EMPLOYER_LABEL.match(line) or SECTION_LABEL.match(line):
            break
        appointment.append(line)
    if re.search(r"\b(?:prezes\w*|człon\w* zarządu|prokurent\w*)\b", " ".join(appointment[:2]), re.IGNORECASE):
        return None
    appointment_text = squash(" ".join(appointment))
    attorney = ATTORNEY_RE.search(appointment_text)
    employee = re.match(rf"(?i:pracownika\s+(?:panią\s+|pana\s+)?)({PERSON})\b", appointment_text, re.IGNORECASE)
    if attorney is None and intro:
        attorney = re.match(
            rf"(?i:(?:pracownika\s+)?(?:panią\s+|pana\s+)?(?:adw\.\s+)?)({PERSON})(?=[.,\s(]|$)",
            appointment_text,
        )
    name = squash(attorney[1]) if attorney else signature[1] if signature else None
    if attorney and intro and APPOINTMENT.fullmatch(intro[0]):
        if not ATTORNEY_RE.match(appointment_text) and re.match(
            r"[, ]*właściciel\w*\s+(?:firmy|przedsiębiorstwa)\b", appointment_text[attorney.end() :], re.IGNORECASE
        ):
            return None
        name = nominative(name, "acc") or name
    firm = _employer(after)
    if employee and attorney:
        firm = appellant_name
    elif not firm and attorney:
        # An inline firm may wrap before the street address.
        inline = re.match(
            r"\s*,\s*((?:kancelaria|biuro prawne)\b[^:;@]{1,160}?),\s*(?:ul|al|pl)\.",
            squash(after)[attorney.end() :],
            re.IGNORECASE,
        )
        if inline:
            firm = inline[1]
    if not firm and signature:
        # A signed appeal may carry the law firm's name in its letterhead.
        letterhead = re.split(r"(?im)^\s*(?:odwołanie|odwołujący|zamawiający)\b", text, maxsplit=1)[0]
        firms = [line.strip() for line in letterhead.splitlines() if FIRM_NAME.match(line.strip())]
        if len(firms) == 1:
            firm = firms[0]
    mail = EMAIL_RE.search(after)
    return {
        "imie_nazwisko": name,
        "nazwa": squash(firm) if firm else None,
        "mail": mail.group() if mail else None,
    }


def _reason(passage: str) -> int | None:
    passage = passage.lower()
    return next((reason for reason, pattern in REASON_RULES if re.search(pattern, passage)), None)


def _form_action(text: str) -> tuple[str | None, int] | None:
    # Form fields describe the same first act only within their own section.
    action = re.search(r"(?im)^(?:zaskarżona|kwestionowana|skarżona) czynność[ \t]*:[ \t]*(.+)$", text)
    if (
        action
        and not (CHARGE.search(text, 0, action.start()) or NEXT_ITEM.search(text, 0, action.start()))
        and (reason := _reason(action[1]))
    ):
        date_field = rf"(?im)^data (?:zaskarżonej |kwestionowanej |skarżonej )?czynności[ \t]*:[ \t]*({DATE})[ \t]*$"
        lines = text.splitlines()
        row = text[: action.start()].count("\n")
        dates = [m[1] for line in lines[max(0, row - 1) : row + 2] if (m := re.fullmatch(date_field, line))]
        return to_iso(dates[0]) if len(dates) == 1 else None, reason
    return None


def _opening_account(text: str) -> tuple[str | None, int | None] | None:
    """Read a buyer's decision immediately above the first allegation heading."""
    heading = FIRST_CHARGE_HEADING.search(text)
    if not heading or CHARGE.search(text, 0, heading.start()):
        return None
    introduction = text[: heading.start()]
    if form := _form_action(introduction):
        return form
    rows = introduction.rstrip().splitlines()[-3:]
    for index in reversed(range(len(rows))):
        passage = squash(" ".join(rows[index:]))
        if not (actor := AUTHORITY_ACT.match(passage)):
            continue
        # A nearby report dates only its own object, even if the first charge
        # expressly challenges a different decision.
        clauses = sentences(passage[actor.end() :])
        obj = REPORTING_VERB.sub("", next(clauses), count=1)
        reason = (
            None
            if any(clauses)
            else next((key for key, cue in ACTION_OBJECTS.items() if re.match(cue, obj, re.IGNORECASE)), None)
        )
        first_charge = first_sentence(squash(text[heading.end() :]))
        for key, cue in ACTS.items():
            if re.match(cue, first_charge, re.IGNORECASE):
                if (day := act_date(first_charge, key)) or key != reason:
                    return day, key
                break
        return to_iso(actor[1]) if actor[1] and reason else None, reason
    return None


def _challenged_action(text: str) -> tuple[str | None, int | None]:
    """Use a dated first charge, otherwise its introductory account of the challenged act."""
    flat = squash(text)
    charge = FIRST_ALLEGATION_RE.search(flat)
    opening = first_sentence(charge.group(1)) if charge else ""
    reason = _reason(opening)
    day = act_date(STATUTE_DATE_RE.sub("", opening), reason) if reason else None
    if reason and day:
        return day, reason

    if not reason and (account := _opening_account(text)) is not None:
        return account

    introduction = ALLEGATIONS_START_RE.split(flat, maxsplit=1)[0]
    for action in reversed(list(ACTION_RE.finditer(introduction))):
        sentence = first_sentence(introduction[action.start() :])
        action_reason = _reason(
            re.split(r",\s*(?:a|ale|lecz|natomiast|po czym|mimo że)\b", sentence, maxsplit=1, flags=re.IGNORECASE)[0]
        )
        if action_reason:
            explicit = opening.lstrip(" :–—-")
            for charge_reason, pattern in ACTS.items():
                if charge_reason != action_reason and re.match(pattern, explicit, re.IGNORECASE):
                    return None, charge_reason
            return to_iso(action.group(1)), action_reason
    item = FIRST_ITEM_RE.search(introduction)
    if item:
        item_opening = first_sentence(item.group(1))
        item_reason = _reason(item_opening)
        if item_reason:
            return act_date(item_opening, item_reason), item_reason
    if charge:
        # An argument section may repeat the heading after the actual numbered allegations.
        earlier = CHARGE.search(flat, 0, charge.start())
        if (
            reason is None
            and earlier
            and (
                earlier[0].lower() == "zarzucam"
                or re.search(r"\bodwołujący\s*$", flat[: earlier.start()], re.IGNORECASE)
            )
            and (first := prose_action(text))[1] is not None
        ):
            return first
        return None, reason
    return _form_action(text) or prose_action(text)


def _procurement(text: str) -> dict:
    bzp = re.search(r"(\d{4})/BZP\s?(\d{8}(?:/\d{2})?)", text)
    ted = re.search(r"(?P<year>\d{4})/S\s*\d{3}-(?P<number>\d{6})", text) or re.search(
        r"(?<![\d/\-])(?P<number>\d{6})[ \t]*[-–—][ \t]*(?P<year>\d{4})(?!\d)", text
    )
    reference = None
    for label in (
        r"(?:nr|numer)\s+(?:referencyjny(?:\s+sprawy)?|postępowania|zamówienia)|postępowani[uea]\s+(?:nr|numer)",
        r"(?:nr|numer)\s+sprawy|znak(?:\s+sprawy)?",
    ):
        for match in re.finditer(rf"\b(?:{label})\b[:\s]+", text, re.IGNORECASE):
            value = re.match(r"(?=[\w./-]*\d)[\w./-]+", text[match.end() :])
            if value:
                reference = value[0].rstrip(".,")
                break
        if reference:
            break
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
        label = re.search(
            r"(?im)\b(?:(?:nazwa|tytuł|przedmiot) (?:postępowania|zamówienia)|postępowaniu na):[ \t]*", text
        )
        if label:
            rows = text[label.end() :].splitlines()
            if rows and not rows[0].strip():
                rows = rows[1:]
            value = rows[0].strip() if rows else ""
            # Accept lowercase continuations inside a form field bounded by its next label.
            continuation = []
            for row in rows[1:]:
                row = row.strip()
                if SECTION_LABEL.match(row):
                    value = " ".join([value, *continuation])
                    break
                if not row or not row[0].islower() or _ends_party(row) or CONTACT.search(row):
                    break
                continuation.append(row)
            value = re.split(r"[ \t]{2,}(?=[^\W\d_][\w ()./-]{0,80}:)", value, maxsplit=1)[0]
            if value and not SECTION_LABEL.match(value):
                title = re.match(r"(.+?)(?=\s*\((?:nr|numer)\b|,\s*(?:nr|numer|znak)\b|$)", value, re.IGNORECASE)
    return {
        "numer_bzp": f"{bzp.group(1)}/BZP{bzp.group(2)}" if bzp else None,
        "numer_postepowania": reference,
        "numer_ted": f"{ted['number']}-{ted['year']}" if ted else None,
        "tytul": squash(title.group(1)) if title else None,
    }


def _appellant_registry(text: str, leader: dict) -> None:
    """Fill absent IDs from an explicit self-identification naming the same appellant."""
    # A letterhead or registry footer can repeat the appellant's KRS next to
    # its other identifiers. Stop at the next row unless it starts with a tax ID.
    if leader["krs"] and not all(leader[key] for key in ("nip", "regon")):
        anchor = rf"\bKRS(?:[ :]+(?:pod numerem |nr )?){re.escape(leader['krs'])}(?!\d)"
        capital = r"(?:[,; ]+kapitał zakładowy[ :]+[\d .,]+(?:PLN|zł)(?:, udziały wpłacone)?)?"
        tax_id = r"(?:NIP[ :]+(?:PL ?)?\d(?:[ -]?\d){9}|REGON[ :]+(?:\d{14}|\d{9}))(?!\d)"
        block = rf"{anchor}{capital}((?:[ ,;\t]*\n?[ \t]*{tax_id}){{1,2}})"
        candidates = {"nip": set(), "regon": set()}
        for row in re.finditer(block, text, re.IGNORECASE):
            ids = registry_ids(row[1].upper())
            for key, values in candidates.items():
                if ids[key]:
                    values.add(ids[key])
        for key, values in candidates.items():
            if len(values) == 1 and not leader[key]:
                leader[key] = values.pop()
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


def extract(text: str, *, ocr_mail_lines: frozenset[int] = frozenset()) -> dict:
    text = FORM_ROLE.sub(lambda m: "Odwołujący: " if m["appellant"] else "Zamawiający: ", text)
    header = text.split("Działając w imieniu", 1)[0]
    party_header, lead_rows = _party_header(header)
    explicit_appellant = bool(EXPLICIT_APPELLANT.search(party_header))
    parties = _parties(
        party_header.splitlines(),
        ocr_mail_lines,
        explicit_appellant,
        inflected=party_header != header,
        lead_rows=lead_rows,
    )
    party_text = _unquoted_party_text(text) if party_header != header else text
    _prose_parties(party_text, parties)
    place_date = PLACE_DATE_RE.search(header)
    filing_date = re.search(rf"(?im)^data (?:złożenia|wniesienia)(?: odwołania)?:[ \t]*({DATE})", header)
    action_date, reason = _challenged_action(text)

    appellants = parties["Odwołujący"]
    leader = next((a for a in appellants if "lider" in a["sublabel"].lower()), appellants[0] if appellants else None)
    representative = _representative(party_header, party_text, leader["nazwa"], explicit_appellant) if leader else None
    if leader:
        _appellant_registry(party_text, leader)
    authorities = parties["Zamawiający"]
    return {
        "OdwolanieKIO": {
            "data": to_iso(place_date[2]) if place_date else to_iso(filing_date[1]) if filing_date else None,
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
