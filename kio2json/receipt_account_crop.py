"""Reread a checksum-invalid Polish account in its printed receipt field."""

import re
from itertools import pairwise
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from PIL import ImageFilter
from stdnum import iban

from .ocr_accounts import ACCOUNT_RE
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
        digits = [w for w in span[1:] if w.text != "PL"]
        if all(b.x0 >= a.x1 and abs(a.y0 - b.y0) <= max(a.y1 - a.y0, b.y1 - b.y0) for a, b in pairwise(digits)):
            matches.append(digits)
    return matches[0] if len(matches) == 1 else []


def _read_crops(path: Path, groups: list[list[WordBox]]) -> list[set[str]]:
    from tesserocr import PSM, PyTessBaseAPI

    with pdfplumber.open(path) as pdf:
        image = pdf.pages[0].to_image(resolution=OCR_DPI)
    left, top = image.bbox[:2]
    readings = []
    with PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.SINGLE_LINE) as api:
        api.SetVariable("tessedit_char_whitelist", "0123456789")
        for group in groups:
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
                if api.Recognize(timeout=2000):
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
        for match in ACCOUNT_RE.finditer(line[0]):
            raw = "".join(match[1].split())
            prefix = line[0][: match.start()].rstrip()
            if iban.is_valid("PL" + raw) or not _ACCOUNT_LABEL.search(prefix):
                continue
            span = _number_boxes(words, prefix.split()[-1], match[0])
            if span:
                targets.append((line.start() + match.start(1), match[1], raw, span))
    if not 1 <= len(targets) <= 2:
        return pages
    text = pages[0]
    try:
        readings = _read_crops(path, [span for _, _, _, span in targets])
    except (OSError, RuntimeError, ValueError, PdfminerException):
        # An optional reread can fail after the primary receipt was read successfully.
        return pages
    for (offset, printed, raw, _), candidates in zip(targets, readings, strict=True):
        valid = {c for c in candidates if re.fullmatch(r"[0-9]{26}", c) and iban.is_valid("PL" + c)}
        if len(valid) == 1:
            candidate = valid.pop()
            if sum(a != b for a, b in zip(candidate, raw, strict=True)) == 1:
                digits = iter(candidate)
                corrected = "".join(next(digits) if c.isdigit() else c for c in printed)
                text = text[:offset] + corrected + text[offset + len(printed) :]
    return [text, *pages[1:]] if text != pages[0] else pages
