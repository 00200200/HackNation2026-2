"""Read the people named by embedded approval signatures on a power of attorney."""

import ctypes
import re
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import pypdfium2 as pdfium
from asn1crypto import cms
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import LIT, PSException

from .common import LOWER, UPPER, squash
from .personal_names import compatible_names
from .power_of_attorney import GRANT, NAMED_SIGNATURE, OTHER_ROLE

PERSON_NAME = re.compile(rf"[{UPPER}][{LOWER}-]+(?: [{UPPER}][{LOWER}-]+){{1,3}}")
MAX_SIGNATURE_BYTES = 4 * 1024 * 1024


def _certificate_names(payload: bytes) -> list[str]:
    info = cms.ContentInfo.load(payload)
    if info["content_type"].native != "signed_data":
        return []
    content = info["content"]
    # Timestamp tokens name a time-stamping authority. Approval signatures cover document data.
    if content["encap_content_info"]["content_type"].native != "data":
        return []
    certs = [entry.chosen for entry in content["certificates"] if entry.name == "certificate"]
    names = []
    for signer in content["signer_infos"]:
        sid = signer["sid"]
        for cert in certs:
            if sid.name == "issuer_and_serial_number":
                match = sid.chosen["issuer"] == cert.issuer and sid.chosen["serial_number"].native == cert.serial_number
            else:
                match = sid.chosen.native == cert.key_identifier
            if not match:
                continue
            subject = cert.subject.native
            given, surname = subject.get("given_name"), subject.get("surname")
            if not isinstance(given, str) or not isinstance(surname, str):
                continue
            name = squash(subject.get("common_name") or "")
            if not (
                name.casefold().startswith(given.casefold() + " ")
                and name.casefold().endswith(" " + surname.casefold())
            ):
                name = squash(given + " " + surname)
            if name.isupper():
                name = name.title()
            if PERSON_NAME.fullmatch(name):
                names.append(name)
    return names


def _visible_order(path: Path, certificates: dict[bytes, list[str]]) -> list[str]:
    """Read left to right only when all approvals are visible in one row on the first page."""
    with path.open("rb") as stream:
        page = next(PDFPage.get_pages(stream, maxpages=1), None)
        if page is None or page.rotate:
            return []
        widgets = []
        for ref in resolve1(page.annots) or ():
            widget = resolve1(ref)
            if not isinstance(widget, dict) or widget.get("Subtype") != LIT("Widget") or widget.get("F", 0) & 35:
                continue
            value = resolve1(widget.get("V"))
            payload = value.get("Contents") if isinstance(value, dict) else None
            if not isinstance(payload, bytes) or len(payload) > MAX_SIGNATURE_BYTES:
                continue
            signature = sha256(payload).digest()
            if signature not in certificates:
                continue
            rect = resolve1(widget.get("Rect"))
            if not isinstance(rect, list) or len(rect) != 4 or len(certificates[signature]) != 1:
                return []
            x0, y0, x1, y1 = rect
            if x0 >= x1 or y0 >= y1:
                return []
            widgets.append((x0, x1, y0, y1, signature))
    if len(widgets) != len(certificates) or {w[4] for w in widgets} != certificates.keys():
        return []
    widgets.sort()
    if max(w[2] for w in widgets) >= min(w[3] for w in widgets):
        return []
    if any(left[1] > right[0] for left, right in pairwise(widgets)):
        return []
    return [certificates[w[4]][0] for w in widgets]


def signed_names(path: Path) -> list[str]:
    certificates = {}
    try:
        with pdfium.PdfDocument(path) as doc:
            for index in range(pdfium.raw.FPDF_GetSignatureCount(doc)):
                obj = pdfium.raw.FPDF_GetSignatureObject(doc, index)
                if _non_issuer_approval(obj):
                    continue
                size = pdfium.raw.FPDFSignatureObj_GetContents(obj, None, 0)
                if not 0 < size <= MAX_SIGNATURE_BYTES:
                    continue
                buffer = ctypes.create_string_buffer(size)
                if pdfium.raw.FPDFSignatureObj_GetContents(obj, buffer, size) != size:
                    continue
                payload = buffer.raw
                if names := _certificate_names(payload):
                    certificates[sha256(payload).digest()] = names
        if len(certificates) > 1 and (ordered := _visible_order(path, certificates)):
            return list(dict.fromkeys(ordered))
    except (OSError, ValueError, TypeError, KeyError, IndexError, PSException, pdfium.PdfiumError):
        # Unsupported optional signature data must leave the ordinary extraction intact.
        pass
    return list(dict.fromkeys(name for names in certificates.values() for name in names))


def add_certificate_signers(path: Path, record: dict, text: str) -> None:
    principals = record["mocodawca"]
    if not principals or NON_ISSUER_SIGNATURE.search(text):
        return
    attorneys = {name for a in record["pelnomocnicy"] if (name := _identity(a["imie_nazwisko"]))}
    names = signed_names(path)
    if not names:
        return
    eligible = _issuer_approvals(path, text, principals, names)
    for name in names:
        identity = _identity(name)
        if not identity or any(compatible_names(attorney, identity) for attorney in attorneys):
            continue
        owners = [
            p
            for p in principals
            if _identity(p["data"]["imie_nazwisko"]) == identity
            or any(_identity(s["imie_nazwisko"]) == identity for s in p["podpisujacy"])
        ]
        if len(owners) == 1:
            people = owners[0]["podpisujacy"]
            for signer in people:
                if _identity(signer["imie_nazwisko"]) == identity:
                    signer["imie_nazwisko"] = name
                    break
            else:
                people.append({"imie_nazwisko": name})
        elif not owners and name in eligible:
            principals[0]["podpisujacy"].append({"imie_nazwisko": name})


def _identity(name: str | None) -> str | None:
    words = (name or "").casefold().split()
    return f"{words[0]} {words[-1]}" if len(words) >= 2 else None


NON_ISSUER_SIGNATURE = re.compile(
    r"(?im)pełnomocnictwo przyjmuję|akt notarialny|^[ \t]*(?:za zgodność z oryginałem|"
    r"(?:poświadczam|potwierdzam|zaświadczam)\s+(?:za\s+)?zgodność\b)"
)
WITNESS = r"(?:świadek|świadk\w*|witness(?:es|ed|ing)?)\b"
WITNESS_SIGNATURE = re.compile(
    r"^[ \t]*(?:świadek|świadkowie|witness(?:es)?)\b"
    rf"|\b(?:podpis\w*|w charakterze|jako|w obecności|signed as(?: a)?)\s+{WITNESS}",
    re.IGNORECASE | re.MULTILINE,
)
COPY_REASON = re.compile(
    r"(?i)\b(?:true|certified) copy\b|\bcopy certification\b|\b(?:poświadczeni\w*|potwierdzeni\w*|za) "
    r"zgodnoś(?:ć|ci)\b"
)


def _non_issuer_approval(obj) -> bool:
    size = pdfium.raw.FPDFSignatureObj_GetReason(obj, None, 0)
    if not size:
        return False
    if size > 8192:
        return True
    buffer = ctypes.create_string_buffer(size)
    if pdfium.raw.FPDFSignatureObj_GetReason(obj, buffer, size) != size:
        return True
    reason = buffer.raw.decode("utf-16-le", errors="replace")
    return bool(COPY_REASON.search(reason) or re.search(rf"\b{WITNESS}", reason, re.IGNORECASE))


def _issuer_approvals(path: Path, text: str, principals: list[dict], names: list[str]) -> set[str]:
    if len(principals) != 1 or principals[0]["data"]["typ"] != "osoba_prawna":
        return set()
    company = principals[0]["data"]["nazwa"]
    grant = GRANT.search(text)
    # An unnamed corporate representative cannot be inferred if the document also names a witness role.
    if not company or not grant or WITNESS_SIGNATURE.search(text):
        return set()
    if (
        len(names) == 1
        and not principals[0]["podpisujacy"]
        and grant[0].casefold().endswith(("m", "my"))
        and re.search(
            rf"\bw imieniu\s+(?:spółki\s+)?{re.escape(company)}(?!\w)", squash(text[: grant.start()]), re.IGNORECASE
        )
    ):
        return set(names)
    if re.search(r"(?m)^[ \t]*[.…]{4,}[. …\t]*$", text[grant.end() :]):
        return _approvals_on_signature_lines(path, company)
    return set()


def _issuer_rules(page, company: str) -> list:
    from pdfplumber.utils import extract_words, obj_to_bbox

    active = False
    rules = []
    for line in page.extract_text_lines():
        text = line["text"]
        if GRANT.search(text):
            active = True
        elif NAMED_SIGNATURE.match(text):
            active = NAMED_SIGNATURE.sub("", text).strip(" :").casefold() == company.casefold()
        elif WITNESS_SIGNATURE.search(text) or OTHER_ROLE.match(text) or re.match(r"(?i)^pełnomocni(?:k|cy)\b", text):
            active = False
        elif active and re.fullmatch(r"[.…\s]{6,}", text):
            rules.extend(obj_to_bbox(word) for word in extract_words(line["chars"]))
    return rules


def _approvals_on_signature_lines(path: Path, company: str) -> set[str]:
    """A visible approval must overlap a printed execution line after the granting clause."""
    import pdfplumber
    from pdfminer.pdftypes import resolve1
    from pdfminer.psparser import LIT, PSException
    from pdfplumber.utils import get_bbox_overlap, obj_to_bbox
    from pdfplumber.utils.exceptions import PdfminerException

    people = set()
    try:
        with pdfplumber.open(path) as doc:
            for page in doc.pages:
                if not page.annots:
                    continue
                rules = _issuer_rules(page, company)
                for annot in page.annots:
                    field = annot["data"]
                    if field.get("FT") != LIT("Sig") or field.get("F", 0) & 35:
                        continue
                    if not any(get_bbox_overlap(obj_to_bbox(annot), rule) for rule in rules):
                        continue
                    value = resolve1(field.get("V"))
                    payload = value.get("Contents") if isinstance(value, dict) else None
                    if isinstance(payload, bytes) and 0 < len(payload) <= MAX_SIGNATURE_BYTES:
                        people.update(_certificate_names(payload))
    except (OSError, ValueError, TypeError, KeyError, IndexError, PSException, PdfminerException):
        pass
    return people
