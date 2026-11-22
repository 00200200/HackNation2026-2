"""Recover bank document text when page segmentation loses word boundaries or a paragraph."""

import re
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from . import bank_transfer
from .classify import (
    CONFIRMATION_HEADING,
    COVER_HEADING,
    DETAIL_CAPTION,
    POLISH_FOLD,
    PRINTED_AMOUNT,
    UNRELATED_HEADING,
    _nonexecuted,
)
from .ocr_budget import REREAD_PAGE_TIMEOUT_SECONDS, require_remaining_ms
from .pdf_text import _language_dir

BANK = re.compile(r"\bbank(?:\s|$)", re.IGNORECASE)
# A number directly following lowercase prose, or a number running into the next word.
JOINED = re.compile(r"[a-ząćęłńóśźż]\d+[.,-]\d|\d{2}[a-ząćęłńóśźż]")


def _bank_header(text: str, *, letter_only: bool) -> bool:
    header = text.splitlines()[:12]
    return any(BANK.search(line) for line in header) and any(
        CONFIRMATION_HEADING.match(line.strip())
        or (
            not letter_only
            and (
                bank_transfer.HISTORY_HEADING.match(line.strip())
                or DETAIL_CAPTION.fullmatch(line.strip().casefold().translate(POLISH_FOLD))
            )
        )
        for line in header
    )


def restore_receipt_spacing(page, text: str) -> str:
    if not JOINED.search(text) or not _bank_header(text, letter_only=False):
        return text
    # A PDF can position successive font runs without an actual space character.
    spaced = page.extract_text(x_tolerance=2) or ""
    if "".join(spaced.split()) == "".join(text.split()) and len(JOINED.findall(spaced)) < len(JOINED.findall(text)):
        return spaced
    return text


def missing_letter_body(text: str) -> bool:
    if not _bank_header(text, letter_only=True) or PRINTED_AMOUNT.search(text):
        return False
    lines = [line.strip() for line in text.splitlines()]
    return not (
        _nonexecuted(lines)
        or bank_transfer.payment_denied(text)
        or any(UNRELATED_HEADING.match(line) or COVER_HEADING.match(line) for line in lines)
    )


def read_letter_body(path: Path) -> list[str]:
    """A single paragraph pass can recover body text ignored as background by automatic segmentation."""
    from tesserocr import PSM, PyTessBaseAPI

    require_remaining_ms()
    try:
        with pdfplumber.open(path) as doc:
            image = doc.pages[0].to_image(resolution=200).original
            with (
                image,
                image.convert("L") as gray,
                PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.SINGLE_BLOCK) as api,
            ):
                api.SetImage(gray)
                api.SetSourceResolution(200)
                if api.Recognize(timeout=require_remaining_ms(1000 * REREAD_PAGE_TIMEOUT_SECONDS)):
                    return [api.GetUTF8Text()]
    except (OSError, PdfminerException, RuntimeError):
        pass
    return []
