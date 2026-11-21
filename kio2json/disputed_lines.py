"""Verify a damaged, labelled OCR value at its original position on the scanned page."""

import os
import re
from collections import defaultdict
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from itertools import groupby, pairwise
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from rapidfuzz.distance import Levenshtein
from stdnum import iban
from stdnum.pl import nip, pesel, regon

from .common import PERSON, squash
from .ocr_budget import RereadExpired, remaining_ms, require_remaining_ms
from .ocr_grant_register import read_crop
from .ocr_signatures import SIGNATURE_HEADING, SIGNER_ROLE_RE
from .pdf_text import OCR_DPI, WordBox, _language_dir
from .rapid_worker import recognize_crop
from .receipt_title import _line_image, _rows, _slope

_GLYPH = r"[0-9OolISB?%$]"
_LABEL = re.compile(r"\b(NIP|REGON|PESEL|KRS)\b[ .:]*(?:nr\.? +)?(?:PL *)?", re.IGNORECASE)
_ACCOUNT = re.compile(
    r"\b(?:rachun(?:ek|ku)(?: +(?:nadawcy|odbiorcy|płatnika))?|konto|IBAN)[ .:]*(?:PL *)?", re.IGNORECASE
)
_NUMBER = re.compile(rf"{_GLYPH}+(?:[ -]+{_GLYPH}+)*(?![\w*/])")
_LENGTHS = {"NIP": {10}, "REGON": {9, 14}, "PESEL": {11}, "KRS": {10}, "account": {26}}
_CHECKS = {
    "NIP": nip.is_valid,
    "REGON": regon.is_valid,
    "PESEL": pesel.is_valid,
    "account": lambda n: iban.is_valid("PL" + n),
}


@dataclass
class Cell:
    kind: str
    start: int
    end: int
    raw: str
    words: list[WordBox]
    block: bool = False


def _digits(text: str) -> str:
    return re.sub(r"[ -]", "", text)


def _register_evidence(pages: list[str]) -> tuple[set[tuple[str, str]], set[str]]:
    printed = set()
    co_registered = defaultdict(set)
    for page in pages:
        for line in page.splitlines():
            ids = {}
            for label in _LABEL.finditer(line):
                match = _NUMBER.match(line, label.end())
                if match:
                    kind, value = label[1].upper(), _digits(match[0])
                    if kind in ids:
                        break
                    ids[kind] = value
            else:
                for kind, value in ids.items():
                    if kind != "KRS" and _CHECKS[kind](value):
                        printed.add((kind, value))
                        if "KRS" in ids and re.fullmatch(r"[0-9]{10}", ids["KRS"]):
                            co_registered[kind, value].add(ids["KRS"])
    disputed = {number for values in co_registered.values() if len(values) > 1 for number in values}
    return printed, disputed


def _fields(
    text: str, previous: str, following: str, document: str, disputed: set[str]
) -> Iterator[tuple[str, int, int, int]]:
    labels = _ACCOUNT if document == "receipt" else _LABEL
    for match in labels.finditer(text):
        value = _NUMBER.match(text, match.end())
        if value is None or re.match(r"[ \t./:–—-]*(?:[*×•]|[Xx]+\b)", text[value.end() :]):
            continue
        kind = "account" if document == "receipt" else match[1].upper()
        raw = _digits(value[0])
        if min(abs(len(raw) - length) for length in _LENGTHS[kind]) > 1 or sum(c.isdigit() for c in raw) < len(raw) - 2:
            continue
        if (
            raw.isascii()
            and raw.isdigit()
            and len(raw) in _LENGTHS[kind]
            and (raw not in disputed if kind == "KRS" else _CHECKS[kind](raw))
        ):
            continue
        yield kind, match.start(), value.start(), value.end()

    if document != "grant":
        return
    # Accept only a caption explicitly identified by a signature heading or officer role.
    role = SIGNER_ROLE_RE.search(text)
    name = text[: role.start()].rstrip(" –—-,(") if role and role.end() == len(text) else text
    if name == text and not (
        SIGNATURE_HEADING.fullmatch(previous)
        or SIGNER_ROLE_RE.fullmatch(previous)
        or SIGNER_ROLE_RE.fullmatch(following)
    ):
        return
    if re.fullmatch(r"[\w-]{2,30}(?: +[\w-]{2,30}){1,2}", name) and not re.fullmatch(PERSON, name):
        yield "caption", 0, 0, len(name)


def _cells(page: str, rows: list[list[WordBox]], document: str, disputed: set[str]) -> Iterator[Cell]:
    lines = [" ".join(w.text for w in row) for row in rows]
    for i, (line, row) in enumerate(zip(lines, rows, strict=True)):
        previous = lines[i - 1] if i else ""
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if document == "grant" and SIGNATURE_HEADING.fullmatch(previous) and i + 1 < len(rows):
            lower = rows[i + 1]
            if len(row) == len(lower) == 1 and re.fullmatch(PERSON, line + " " + following):
                top, bottom = row[0], lower[0]
                height = max(top.y1 - top.y0, bottom.y1 - bottom.y0)
                block = line + "\n" + following
                if 0 <= bottom.y0 - top.y1 <= height and abs(bottom.x0 - top.x0) <= height and page.count(block) == 1:
                    offset = page.index(block)
                    yield Cell("caption", offset, offset + len(block), block, [top, bottom], block=True)
        for kind, anchor, start, end in _fields(line, previous, following, document, disputed):
            # Match box boundaries, and require a unique occurrence of the labelled row in the transcript.
            # A fused label/value box or a repeated identical row cannot license a local substitution.
            words = []
            span = []
            at = 0
            for word in row:
                stop = at + len(word.text)
                if stop > anchor and at < end:
                    span.append(word)
                if stop > start and at < end:
                    words.append(word)
                at = stop + 1
            if (
                not words
                or words[0].text != line[start:].split()[0]
                or words[-1].text.rstrip(",.;:)") != line[start:end].split()[-1]
            ):
                continue
            if any(b.x0 - a.x1 > 3 * max(a.y1 - a.y0, b.y1 - b.y0) for a, b in pairwise(span)):
                continue
            positions = list(re.finditer(r"(?<!\S)" + re.escape(line) + r"(?!\S)", page))
            if len(positions) == 1:
                offset = positions[0].start()
                yield Cell(kind, offset + start, offset + end, line[start:end], words)


def _decision(cell: Cell, reading: str, second, printed: set[tuple[str, str]]) -> str | None:
    """Both alternatives must be visible on this crop and close to the original glyphs."""
    normalize = squash if cell.kind == "caption" else _digits
    raw, value = normalize(cell.raw), normalize(reading.strip().strip(",.;:"))
    if cell.block and raw == value and re.fullmatch(PERSON, value):
        return value
    if not value or value == raw or Levenshtein.distance(raw, value, score_cutoff=2) > 2:
        return None

    def plausible(candidate: str) -> bool:
        if cell.kind == "caption":
            return bool(re.fullmatch(PERSON, candidate))
        return candidate.isascii() and candidate.isdigit() and len(candidate) in _LENGTHS[cell.kind]

    check = _CHECKS.get(cell.kind)
    if (
        plausible(value)
        and check
        and check(value)
        and (Levenshtein.distance(raw, value) == 1 or (cell.kind, value) in printed)
    ):
        return value
    if cell.block:
        # A line recognizer cannot independently confirm a multi-line crop.
        return None
    try:
        alternative = normalize(second().strip().strip(",.;:"))
    except (RuntimeError, OSError):
        return None
    if not plausible(alternative) or Levenshtein.distance(raw, alternative, score_cutoff=2) > 2:
        return None
    if check:
        if plausible(value) and check(value) and alternative != value:
            return None
        return (
            alternative
            if check(alternative) and (alternative == value or Levenshtein.distance(raw, alternative) == 1)
            else None
        )
    return value if value == alternative else None


def verified_lines(path: Path, pages: list[str], boxes: list[WordBox], document: str) -> list[str]:
    """Render each disputed page once, and leave unrelated document text in place."""
    if os.getenv("KIO_OCR_DISPUTED_LINES") != "1" or not boxes or not remaining_ms(1):
        return pages
    from tesserocr import PSM, PyTessBaseAPI

    printed, disputed = _register_evidence(pages) if document != "receipt" else (set(), set())
    result = pages.copy()
    try:
        with ExitStack() as stack:
            doc = api = None
            for number, group in groupby(boxes, key=lambda box: box.page):
                require_remaining_ms()
                rows = _rows(list(group), page=number)
                cells = list(_cells(pages[number - 1], rows, document, disputed))
                if not cells:
                    continue
                if doc is None:
                    doc = stack.enter_context(pdfplumber.open(path))
                    api = stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.SINGLE_LINE))
                require_remaining_ms()
                image = doc.pages[number - 1].to_image(resolution=OCR_DPI)
                slope = _slope(rows)
                for cell in sorted(cells, key=lambda c: c.start, reverse=True):
                    require_remaining_ms()
                    crop = _line_image(image, cell.words, slope if abs(slope) < 0.12 else 0)
                    api.SetPageSegMode(PSM.SINGLE_BLOCK if cell.block else PSM.SINGLE_LINE)
                    api.SetVariable("tessedit_char_whitelist", "" if cell.kind == "caption" else "0123456789")
                    if reading := read_crop(crop, api, dpi=OCR_DPI):
                        value = _decision(
                            cell,
                            reading,
                            partial(recognize_crop, crop),
                            printed,
                        )
                        if value and remaining_ms(1):
                            line = result[number - 1]
                            result[number - 1] = line[: cell.start] + value + line[cell.end :]
    except (OSError, RuntimeError, ValueError, PdfminerException, RereadExpired):
        pass
    return result
