"""Bounded, pixel-supported corrections for an already localized identifier."""

import re
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from time import monotonic

import pdfplumber
import pypdfium2 as pdfium
from pdfplumber.utils.exceptions import PdfminerException
from stdnum import iban
from stdnum.pl import nip, pesel, regon

from .ocr_budget import remaining_ms
from .pdf_text import OCR_DPI, WordBox, _language_dir

LENGTHS = {"nip": (10,), "regon": (9, 14), "pesel": (11,), "krs": (10,)}
CHECKS = {"nip": nip.is_valid, "regon": regon.is_valid, "pesel": pesel.is_valid}
ACCOUNT_KEYS = {"na_rachunek", "z_rachunku"}


@dataclass
class Cell:
    parent: dict
    field: str
    original: str
    words: list[WordBox]


def shape(field: str, value: str) -> bool:
    if field in ACCOUNT_KEYS:
        if re.fullmatch(r"[0-9]{26}", value):
            return True
        if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", value) or "XX" in value[4:]:
            return False
        # Validate structure separately so a truncated or masked IBAN can never
        # qualify for retention merely because both readings agree on its text.
        probe = value[:2] + iban.calc_check_digits(value) + value[4:]
        return iban.is_valid(probe, check_country=False)
    return value.isascii() and value.isdigit() and len(value) in LENGTHS[field]


def valid(field: str, value: str) -> bool:
    if not shape(field, value):
        return False
    if field in ACCOUNT_KEYS:
        account = value if value[:2].isalpha() else "PL" + value
        return iban.is_valid(account, check_country=False) and account[2:4] == iban.calc_check_digits(account)
    # KRS has no checksum. The existing register agreement pass owns this field.
    return field == "krs" or CHECKS[field](value)


def candidates(field: str, original: str, symbols: list) -> tuple[str, ...]:
    """Use Tesseract's mode-2 costs (smaller is better). Abstain on excess ambiguity."""
    kept = (original,)
    if valid(field, original) or not shape(field, original):
        return kept
    if any(not choices for choices in symbols):
        return kept
    symbols = [choices for choices in symbols if not choices[0][0].isspace()]
    if field in LENGTHS:
        symbols = [choices for choices in symbols if choices[0][0] != "-"]
    while symbols and symbols[-1][0][0] in (".", ",", ";", ":"):
        symbols.pop()
    if len(symbols) != len(original):
        return kept
    slots = []
    disputes = 0
    for index, (char, choices) in enumerate(zip(original, symbols, strict=True)):
        best, cost = choices[0]
        if char.isalpha() or (original[:2].isalpha() and index < 2):
            if best != char:
                return kept
            slots.append((char,))
            continue
        if best not in "0123456789" or len(best) != 1 or cost > 18:
            return kept
        digits = tuple(dict.fromkeys(g for g, c in choices if len(g) == 1 and g in "0123456789" and c <= cost + 7))
        if set(digits) != {char}:
            disputes += 1
            if disputes > 2:
                return kept
        slots.append(digits)
    result = dict.fromkeys(kept)
    for chars in product(*slots):
        result["".join(chars)] = None
        if len(result) > 8:
            return kept
    return tuple(result)


def _read(api, crop, field, original, timeout):
    from tesserocr import RIL, iterate_level

    api.SetImage(crop)
    api.SetSourceResolution(OCR_DPI)
    if not timeout or not api.Recognize(timeout=timeout):
        return (original,), False
    it = api.GetIterator()
    if it is None or it.Empty(RIL.WORD):
        return (original,), False
    symbols = []
    for word in iterate_level(it, RIL.WORD):
        symbols.extend(word.GetBestLSTMSymbolChoices() or [])
    beam = candidates(field, original, symbols)
    # Independently confirm every glyph before retaining a legible, invalid
    # account that the primary checksum normalizer discarded.
    ink = [s for s in symbols if s and not s[0][0].isspace()]
    clear = (
        all(symbols)
        and "".join(s[0][0] for s in ink) == original
        and all(s[0][1] <= 10 and all(cost > s[0][1] + 7 for _, cost in s[1:]) for s in ink)
    )
    return beam, clear


def _crop(pdf, path, cell):
    words = cell.words
    index = words[0].page - 1
    bounds = (
        min(w.x0 for w in words) - 2,
        min(w.y0 for w in words) - 2,
        max(w.x1 for w in words) + 2,
        max(w.y1 for w in words) + 2,
    )
    with ExitStack() as stack:
        page = pdf[index]
        stack.callback(page.close)
        media = page.get_mediabox()
        if media[:2] == (0, 0) and page.get_cropbox() == media and page.get_rotation() == 0:
            # Render only the cell. A full-page bitmap for every field can
            # exhaust the incremental budget before recognition starts.
            width, height = page.get_size()
            x0, y0, x1, y1 = bounds
            margins = (max(x0, 0), max(height - y1, 0), max(width - x1, 0), max(y0, 0))
            bitmap = page.render(scale=OCR_DPI / 72, crop=margins, grayscale=True)
            stack.callback(bitmap.close)
            return bitmap.to_pil().copy()
    # Preserve pdfplumber's exact page coordinate transform for unusual page boxes.
    with pdfplumber.open(path) as doc:
        page = doc.pages[index]
        x0, y0, x1, y1 = bounds
        left, top, right, bottom = page.bbox
        return (
            page.crop((max(x0, left), max(y0, top), min(x1, right), min(y1, bottom)))
            .to_image(resolution=OCR_DPI)
            .original
        )


def verify_cells(path: Path, locate, record: dict, boxes: list[WordBox], *, data_dir: str | None = None) -> None:
    deadline = monotonic() + 2.0

    def timeout():
        return remaining_ms(max(0, int(1000 * (deadline - monotonic()))))

    if not timeout():
        return
    cells = locate(record, boxes)
    occurrences = Counter((id(cell.parent), cell.field) for cell in cells)
    eligible = [c for c in cells if occurrences[id(c.parent), c.field] == 1 and not valid(c.field, c.original)]
    if not eligible or not timeout():
        return
    from tesserocr import PSM, PyTessBaseAPI

    try:
        with (
            pdfium.PdfDocument(path) as pdf,
            PyTessBaseAPI(path=data_dir or _language_dir(), lang="pol", psm=PSM.SINGLE_LINE) as api,
        ):
            if not api.SetVariable("lstm_choice_mode", "2"):
                return
            for cell in eligible:
                if not timeout():
                    break
                crop = _crop(pdf, path, cell)
                readings, clear = _read(api, crop, cell.field, cell.original, timeout())
                if not timeout():
                    break
                hits = [v for v in readings if valid(cell.field, v)]
                if clear and cell.field in ACCOUNT_KEYS and not hits:
                    cell.parent[cell.field] = cell.original
                elif len(hits) == 1:
                    value = hits[0]
                    old = cell.parent[cell.field]
                    cell.parent[cell.field] = (
                        int(value) if isinstance(old, int) and not value.startswith("0") else value
                    )
    except (OSError, RuntimeError, ValueError, PdfminerException, pdfium.PdfiumError):
        return
