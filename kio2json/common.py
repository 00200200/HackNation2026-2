"""Patterns and normalizers shared by the per-class extractors."""

import re
from datetime import date

UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
LOWER = "a-ząćęłńóśźż"

PARTY_LABELS = {
    "appellant": r"odwo[łl]uj[ąa]cy|(?:wykonawca|podmiot) wnosz[ąa]cy odwo[łl]anie",
    "authority": r"zamawiaj[ąa]cy",
    "principal": r"mocodawc[ay]",
    "appointee": r"pełnomocni(?:k|cy)",
    "representation": r"(?:reprezentowan|zastępowan)\w* przez(?: pełnomocnika)?",
    "counsel": r"pełnomocnik odwołującego",
    "other": r"adresat|uczestnik(?: postępowania)?|poświadczający|za zgodność(?: z oryginałem)?",
    "signer": r"podpisuj[ąa]c[ya]|podpis(?:y)?(?: mocodawc(?:y|ów))?",
}

MONTHS = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]


def date_pattern(separator: str) -> str:
    # Native dates use adjacent digits. OCR can insert whitespace after the printed separator.
    return (
        rf"(?<!\d)(?:\d{{4}}{separator}\d{{2}}{separator}\d{{2}}|"
        rf"\d{{1,2}}{separator}\d{{1,2}}{separator}\d{{4}}|"
        rf"\d{{1,2}}\s+(?i:{'|'.join(MONTHS)})\s+\d{{4}})(?!\d)"
    )


DATE = date_pattern(r"[-/.]")
DATE_RE = re.compile(DATE)

ROMAN_MONTHS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
# Receipt exports also print dates with a Roman month between day and year.
RECEIPT_DATE = rf"(?:{DATE}|(?<!\w)\d{{1,2}}[ ./-]+(?i:{'|'.join(ROMAN_MONTHS)})[ ./-]+\d{{4}}(?!\w))"
RECEIPT_DATE_RE = re.compile(RECEIPT_DATE)

_NAME_PART = rf"[{UPPER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?"
PERSON = rf"{_NAME_PART}\s+{_NAME_PART}"
ATTORNEY_RE = re.compile(rf"(?:adw\.|r\.\s?pr\.|adwokat\w*|radc\w+\s+prawn\w+)\s+({PERSON})")
EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def to_iso(text: str) -> str | None:
    parts = re.split(r"[./\-\s]+", text.strip().lower())
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    if month.upper() in ROMAN_MONTHS:
        month_number = ROMAN_MONTHS.index(month.upper()) + 1
    else:
        month_number = MONTHS.index(month) + 1 if month in MONTHS else int(month)
    try:
        return date(int(year), month_number, int(day)).isoformat()
    except ValueError:
        return None


def find_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    return to_iso(match.group()) if match else None


def registry_ids(text: str) -> dict[str, str | None]:
    """First KRS, NIP and REGON printed in the text; None when a number is absent."""
    krs = re.search(r"KRS:?\s*(?:nr\s*)?(\d{10})(?!\d)", text)
    nip = re.search(r"NIP:?\s*(?:PL\s?)?(\d(?:[ \-]?\d){9})(?!\d)", text)
    regon = re.search(r"REGON:?\s*(\d{14}|\d{9})(?!\d)", text)
    return {
        "krs": krs.group(1) if krs else None,
        "nip": re.sub(r"\D", "", nip.group(1)) if nip else None,
        "regon": regon.group(1) if regon else None,
    }
