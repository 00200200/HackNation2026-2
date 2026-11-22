"""Reread a checksum-invalid account in its printed receipt field."""

import re
from itertools import pairwise
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from PIL import ImageFilter

from .accounts import account_matches, valid_account
from .ocr_budget import CROP_TIMEOUT_MS, RereadExpired, remaining_ms, require_remaining_ms
from .pdf_text import OCR_DPI, WordBox, _language_dir

# Account nouns survive OCR more reliably than the adjoining party labels.
_ACCOUNT_LABEL = re.compile(r"\b(?:rachun\w{1,4}|kont[oa]|iban)(?: +[^\W\d_]+)?[ .:]*$", re.IGNORECASE)


def _number_boxes(words: list[WordBox], label: str, token: str) -> list[WordBox]:
    # The preceding label word ties the crop to this occurrence, including when
    # another field (e.g. a reference) happens to print the same digits.
    tokens = [label, *token.split()]
    matches = []
    for i, word in enumerate(words):
        if word.text != label:
            continue
        span = words[i : i + len(tokens)]
        if [w.text for w in span] != tokens:
            continue
        digits = list(span[2:] if re.fullmatch(r"[A-Za-z]{2}", tokens[1]) else span[1:])
        if all(b.x0 >= a.x1 and abs(a.y0 - b.y0) <= max(a.y1 - a.y0, b.y1 - b.y0) for a, b in pairwise(digits)):
            matches.append(digits)
    return matches[0] if len(matches) == 1 else []


def _read_crops(path: Path, groups: list[list[WordBox]]) -> list[set[str]]:
    from tesserocr import PSM, PyTessBaseAPI

    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        require_remaining_ms()
        image = page.to_image(resolution=OCR_DPI)
    require_remaining_ms()
    left, top = image.bbox[:2]
    readings = []
    with PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.SINGLE_LINE) as api:
        for group in groups:
            letters = any(c.isalpha() for w in group for c in w.text.removeprefix("PL"))
            alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" if letters else "0123456789"
            api.SetVariable("tessedit_char_whitelist", alphabet)
            require_remaining_ms()
            bounds = (
                (min(w.x0 for w in group) - left - 2) * image.scale,
                (min(w.y0 for w in group) - top - 2) * image.scale,
                (max(w.x1 for w in group) - left + 2) * image.scale,
                (max(w.y1 for w in group) - top + 2) * image.scale,
            )
            crop = image.original.crop(bounds).convert("L")
            candidates = set()
            for variant in (crop, crop.filter(ImageFilter.MedianFilter(3))):
                api.SetImage(variant)
                api.SetSourceResolution(OCR_DPI)
                if api.Recognize(timeout=require_remaining_ms(CROP_TIMEOUT_MS)):
                    candidates.add("".join(api.GetUTF8Text().split()))
            readings.append(candidates)
    return readings


def recover_account_crops(path: Path, pages: list[str], boxes: list[WordBox]) -> list[str]:
    """Replace one misread digit only when the crop yields one checksum-valid reading."""
    if not pages or not boxes:
        return pages
    words = [w for w in boxes if w.page == 1]
    targets = []
    for line in re.finditer(r"[^\n]+", pages[0]):
        for match in account_matches(line[0]):
            raw = "".join(match[1].split())
            prefix = line[0][: match.start()].rstrip()
            if valid_account(raw) or not _ACCOUNT_LABEL.search(prefix):
                continue
            span = _number_boxes(words, prefix.split()[-1], match[0])
            if span:
                targets.append((line.start() + match.start(1), match[1], raw, span))
    if not 1 <= len(targets) <= 2 or not remaining_ms(1):
        return pages
    text = pages[0]
    try:
        readings = _read_crops(path, [span for _, _, _, span in targets])
    except (OSError, RuntimeError, ValueError, PdfminerException, RereadExpired):
        # An optional reread can fail after the primary receipt was read successfully.
        return pages
    for (offset, printed, raw, _), candidates in zip(targets, readings, strict=True):
        country = raw[:2] if raw[:2].isalpha() else ""
        # Crops can exclude a separately printed country code or read only the
        # digits in PL-prefixed fields. Never change the printed country.
        readings_with_prefix = {country + c if country and len(c) == len(raw) - 2 else c for c in candidates}
        valid = {
            c
            for c in readings_with_prefix
            if len(c) == len(raw) and c.upper().startswith(country.upper()) and valid_account(c)
        }
        if len(valid) == 1:
            candidate = valid.pop()
            # Tesseract's account whitelist reads letters in uppercase. Retain
            # each printed letter's case when the readings agree on that glyph.
            corrected_number = [a if a.upper() == b.upper() else b for a, b in zip(raw, candidate, strict=True)]
            if sum(a != b for a, b in zip(raw, corrected_number, strict=True)) == 1:
                digits = iter(corrected_number)
                corrected = "".join(c if c.isspace() else next(digits) for c in printed)
                text = text[:offset] + corrected + text[offset + len(printed) :]
    return [text, *pages[1:]] if text != pages[0] else pages
