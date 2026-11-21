"""Read the people named by embedded approval signatures on a power of attorney."""

import ctypes
import re
from pathlib import Path

import pypdfium2 as pdfium
from asn1crypto import cms

from .common import LOWER, UPPER, squash

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


def signed_names(path: Path) -> list[str]:
    names = []
    try:
        with pdfium.PdfDocument(path) as doc:
            for index in range(pdfium.raw.FPDF_GetSignatureCount(doc)):
                obj = pdfium.raw.FPDF_GetSignatureObject(doc, index)
                size = pdfium.raw.FPDFSignatureObj_GetContents(obj, None, 0)
                if not 0 < size <= MAX_SIGNATURE_BYTES:
                    continue
                buffer = ctypes.create_string_buffer(size)
                if pdfium.raw.FPDFSignatureObj_GetContents(obj, buffer, size) == size:
                    names.extend(_certificate_names(buffer.raw))
    except (OSError, ValueError, TypeError, KeyError, IndexError, pdfium.PdfiumError):
        # Unsupported optional signature data must leave the ordinary extraction intact.
        pass
    return list(dict.fromkeys(names))


def add_certificate_signers(path: Path, record: dict, text: str) -> None:
    principals = record["mocodawca"]
    if not principals or re.search(r"(?im)pełnomocnictwo przyjmuję|akt notarialny|^\s*za zgodność z oryginałem", text):
        return
    attorneys = {_identity(a["imie_nazwisko"]) for a in record["pelnomocnicy"] if a["imie_nazwisko"]}
    for name in signed_names(path):
        identity = _identity(name)
        if identity in attorneys:
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
        elif not owners and len(principals) == 1 and principals[0]["data"]["typ"] == "osoba_prawna":
            principals[0]["podpisujacy"].append({"imie_nazwisko": name})


def _identity(name: str | None) -> tuple[str, str] | None:
    words = (name or "").casefold().split()
    return (words[0], words[-1]) if len(words) >= 2 else None
