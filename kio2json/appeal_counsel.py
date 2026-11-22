"""Bind filing declarations and signature contacts to the appellant who made the filing."""

import re
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium

from .appeal_charges import FILING
from .common import EMAIL_RE, PERSON, squash
from .personal_names import nominative

_TITLE = r"(?:adw\.|adwokat(?:ka|a)?|r\.\s*pr\.|radc[ayę]\s+prawn(?:y|a|ego))"
_LAWYER = re.compile(rf"(?i:{_TITLE})\s+({PERSON})\b")
_NAME = re.compile(PERSON)
_FIRM_LABEL = re.compile(r"(?i)^(?:nazwa kancelarii|kancelaria|pracodawca)\s*:\s*")
_NAME_LABEL = re.compile(r"(?i)^imię i nazwisko(?: pełnomocnika)?\s*:\s*")
_FIRM = re.compile(r"(?i)^(?:kancelaria\b|biuro prawne\b)")
_PARTNERSHIP = re.compile(r"\b(?:partners|partnerzy|wspólnicy|spółka partnerska|sp\.\s*p\.)\s*$", re.IGNORECASE)
_MAIL = re.compile(r"(?i)^(?:adres (?:poczty elektronicznej|e-mail)|e[- ]?mail|kontakt)(?: pełnomocnika)?\s*:")
_CONTACT = re.compile(r"(?i)^(?:ul\.|al\.|\d{2}-\d{3}|tel\.|fax\b|www\.|adres kancelarii\b)")
_ATTACHMENT = re.compile(r"(?im)^\s*(?:[IVX]+[.)]\s*)?(?:wykaz |spis )?załącznik(?:i|ów)\s*[:：.]?\s*$")
_OTHER = re.compile(
    r"\b(?:zamawiającego|przystępującego|przeciwnika|interwenienta|zarządu|prokurent\w*)\b", re.IGNORECASE
)
_ROLE = r"pełnomocni(?:k(?:a|iem)?|czk(?:a|i|ą))(?:\s+procesow\w+)?"
_ROLE_EVIDENCE = re.compile(rf"(?i)\b(?:{_ROLE}|pełnomocnictw\w*)\b")
_SIGNATURE = re.compile(r"(?i)^(?:podpis(?:ano|ał[ao]?)?|podpis elektroniczny|z poważaniem)\s*[:.,-]?\s*")


def before_attachments(text: str) -> str:
    return _ATTACHMENT.split(text, maxsplit=1)[0]


def partnership_name(line: str) -> str | None:
    """A partnership designation distinguishes a firm value from another personal name."""
    return line if len(line) <= 120 and line[:1].isupper() and _PARTNERSHIP.search(line) else None


def _contact_block(rows, *, allow_bare: bool):
    person = firm = mail = None
    parts = (part for row in rows for part in re.split(r"(?i)[,;|]\s*(?=kancelaria\b|biuro prawne\b|e-?mail\s*:)", row))
    for row in parts:
        line = _SIGNATURE.sub("", row).strip(" :–-")
        if not line:
            continue
        if _OTHER.search(line):
            break
        firm_label = _FIRM_LABEL.match(line)
        if firm_label or _FIRM.match(line) or partnership_name(line):
            if firm:
                break
            if firm_label:
                line = line[firm_label.end() :]
            firm = re.split(r",?\s+(?:ul\.|al\.|e-?mail:)|\s*\|", line, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,")
        elif lawyer := _LAWYER.match(line):
            proposed = lawyer[1]
            if person and proposed != person:
                break
            person = proposed
        elif (name_label := _NAME_LABEL.match(line)) and _NAME.fullmatch(line[name_label.end() :]):
            if person and person != line[name_label.end() :]:
                break
            person = line[name_label.end() :]
        elif re.fullmatch(_TITLE, line, re.IGNORECASE):
            allow_bare = True
        elif allow_bare and not person and _NAME.fullmatch(line):
            person = line
        elif EMAIL_RE.fullmatch(address := _MAIL.sub("", line).strip(" .")):
            if not (person or firm) or (mail and mail != address):
                break
            mail = address
        elif not _CONTACT.match(line):
            break
    return {"imie_nazwisko": person, "nazwa": firm, "mail": mail}


def _stationery(lines, person):
    """Only a repeated full identity can connect separate stationery to the signature."""
    for i, row in enumerate(lines):
        if re.match(r"(?i)^(?:odwoła[nń]|odwołujący|zamawiający|prezes krajowej)", row):
            break
        if _FIRM.match(row):
            office = _contact_block(lines[i : i + 6], allow_bare=False)
            if person and office["imie_nazwisko"] == person:
                return office
    return {}


def filing_counsel(text: str, principal: str, existing: dict | None) -> dict | None:
    """Supplement the existing party card only with an explicitly owned local record."""
    lines = [squash(s) for s in text.splitlines() if s.strip()]
    owner = rf"(?:strony odwołującej(?: się)?|odwołując(?:ego|ej)|(?:spółki\s+)?{re.escape(principal)})(?!\w)"
    role = re.compile(rf"(?i)^(?:podpis\s+)?(?:{_ROLE}\s+{owner}|{owner}\s+reprezentuje)\s*[:–,-]?\s*")
    behalf = re.compile(rf"(?i)^(?:(?:działając|działam)\s+)?(?:za|w imieniu(?: i na rzecz)?)\s+{owner}")
    capacity = re.compile(rf"(?i)^(?:(?:działając|działam)\s+)?jako\s+{_ROLE}\s+{owner}")
    declaration = re.compile(
        rf"(?i)^(?:odwołując[ya]|{re.escape(principal)})\s+"
        rf"(?:(?:jest\s+)?(?:reprezentowan|zastępowan)\w*|działa|(?:wnosi|składa)\s+(?:niniejsze\s+)?odwołanie)\s+"
        rf"przez\s+(?:{_ROLE}\s*:?\s*|(?={_TITLE}\s))"
    )
    authorized_agent = re.compile(
        rf"(?i)^przedstawiciel(?:ka)?\s+{owner}\s+(?:działając\w*\s+)?(?:umocowan\w*|na podstawie|na mocy|zgodnie z)\s+"
        r"(?:[\w.]+\s+){0,3}pełnomocnictw\w*\b"
    )
    records = []
    signed_filing = False
    for i, row in enumerate(lines):
        if re.match(r"(?i)^(?:odpowiedź|stanowisko|pełnomocnik|podpis)\s+(?:zamawiającego|przystępującego)\b", row):
            signed_filing = False
        if _OTHER.search(row) or re.search(r'(?i)\b(?:nie|cytat|dawny|były)\b|[„«"]', row):
            continue
        binding = role.match(row)
        acting = behalf.match(row)
        filing = declaration.match(row)
        closing = _SIGNATURE.fullmatch(row) if signed_filing else None
        marker = binding or acting or filing or capacity.match(row) or authorized_agent.match(row) or closing
        if not marker:
            continue
        if not closing and FILING.search(row) and _ROLE_EVIDENCE.search(row):
            signed_filing = True
        tail = row[marker.end() :].strip(" ,:–-")
        downstream = lines[i + 1 : i + 7]
        if not tail and downstream and _OTHER.search(downstream[0]):
            continue
        first = tail if _LAWYER.match(tail) or _NAME.fullmatch(tail) else ""
        if binding and not first and i and _LAWYER.fullmatch(lines[i - 1]):
            first = lines[i - 1]
        contact = _contact_block([first, *downstream], allow_bare=bool(binding))
        name = contact["imie_nazwisko"]
        if closing and not name:
            continue
        if (acting or (binding and "reprezentuje" in marker[0].casefold())) and not (
            name or (FILING.search(row) and _ROLE_EVIDENCE.search(row))
        ):
            continue
        if name and filing:
            contact["imie_nazwisko"] = nominative(name, "acc") or name
        if name and not all(contact.values()):
            office = _stationery(lines[:i], name)
            contact = {key: value or office.get(key) for key, value in contact.items()}
        records.append(contact)
    if not records:
        return existing
    # A flag-only declaration may precede the actual signature. Fill a missing
    # leaf only if the blocks agree on the person and the value.
    result = dict(existing or dict.fromkeys(("imie_nazwisko", "nazwa", "mail")))
    names = {rec["imie_nazwisko"] for rec in records if rec["imie_nazwisko"]}
    if result["imie_nazwisko"]:
        records = [rec for rec in records if rec["imie_nazwisko"] == result["imie_nazwisko"]]
    elif len(names) > 1:
        return result
    elif names:
        records = [rec for rec in records if rec["imie_nazwisko"] in names]
    for key, previous in result.items():
        candidates = {rec[key] for rec in records if rec[key]}
        if not previous and len(candidates) == 1:
            result[key] = candidates.pop()
    return result


def final_native_page(path: Path, retained: int) -> str:
    """Read one bounded native text layer beyond the retained pages."""
    try:
        with pdfium.PdfDocument(path) as document:
            if len(document) <= retained:
                return ""
            with closing(document[len(document) - 1]) as page, closing(page.get_textpage()) as layer:
                if not 0 < layer.count_chars() <= 20000:
                    return ""
                return layer.get_text_bounded().replace("\r", "")
    except (OSError, ValueError, pdfium.PdfiumError):
        return ""


def signature_block(text: str) -> str:
    # The final page may still be argument or an exhibit.
    # A closing must be on its own line and introduce the last signature block.
    rows = [line.strip() for line in before_attachments(text).splitlines() if line.strip()][-12:]
    for i, row in enumerate(rows):
        if _SIGNATURE.fullmatch(row) or re.match(r"(?i)^podpis pełnomocni", row):
            return "\n".join(rows[i:])
    return ""
