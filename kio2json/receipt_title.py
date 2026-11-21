"""Read the printed title cell on a scanned bank receipt."""

import re
from pathlib import Path
from statistics import median

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from PIL import Image
from rapidfuzz.fuzz import ratio

from .bank_transfer import BOUNDARY_RE, STATUS, _field_text, _title
from .ocr_budget import CROP_TIMEOUT_MS, RereadExpired, require_remaining_ms
from .pdf_text import OCR_DPI, WordBox, _language_dir

_LABEL = re.compile(
    r"^[^\w]*(?P<label>tytu[łl](?:em| przelewu| operacji)?|szczeg[oó]ły płatności|opis(?: operacji)?)\b[.:]?\s*",
    re.IGNORECASE,
)
_END = re.compile(r"^(?:typ\b|data\b|dokument\b|s.gnature\b|rachun\w*|nazwa\b)", re.IGNORECASE)


def _rows(boxes: list[WordBox], *, page: int = 1) -> list[list[WordBox]]:
    """Tesseract returns words in reading order even on tilted pages."""
    rows = []
    for word in boxes:
        if word.page != page or not word.text.strip():
            continue
        if rows:
            prev = rows[-1][-1]
            step = abs((word.y0 + word.y1 - prev.y0 - prev.y1) / 2)
            if word.x0 >= prev.x0 and step <= max(5, prev.y1 - prev.y0, word.y1 - word.y0):
                rows[-1].append(word)
                continue
        rows.append([word])
    return rows


def _title_rows(rows: list[list[WordBox]], height: float) -> list[list[WordBox]]:
    anchors = []
    for index, row in enumerate(rows):
        text = " ".join(w.text for w in row)
        match = _LABEL.match(text)
        if match and not re.fullmatch(r"kwota", text[match.end() :], re.IGNORECASE):
            # 'Opis' alone can head a data table on a page with a dedicated title.
            # Some backends emit a whole multiword label in one box. Only crop
            # at a known box boundary when the value shares its physical row.
            prefix = match[0].rstrip()
            consumed = 0
            for stop, word in enumerate(row, start=1):
                consumed += len(word.text)
                if consumed >= len(prefix):
                    if consumed == len(prefix):
                        anchors.append((not match["label"].lower().startswith("opis"), index, stop))
                    break
                consumed += 1
    if not anchors:
        return []
    explicit, index, after = max(anchors)
    if sum(priority == explicit for priority, _, _ in anchors) != 1:
        return []
    previous = rows[index][after - 1]
    selected = []
    for offset, row in enumerate(rows[index : index + 10]):
        if offset == 0:
            row = row[after:]
        else:
            line = " ".join(w.text for w in row)
            if BOUNDARY_RE.match(line) or _END.match(line) or STATUS.match(line):
                break
        # Tiny detached marks around the first/last glyph are scan noise. Keep all
        # punctuation between normal-sized words (including spaces around a dash).
        ink = [i for i, w in enumerate(row) if w.y1 - w.y0 >= 0.48 * height and any(c.isalnum() for c in w.text)]
        if not ink:
            continue
        first, last = ink[0], ink[-1]
        if row[first].y0 - previous.y1 > 3.2 * height:
            break
        if any(b.x0 - a.x1 > 6 * height for a, b in zip(row[first:last], row[first + 1 : last + 1])):
            # An adjacent column contains other text on the same physical line.
            return []
        selected.append(row[first : last + 1])
        previous = row[first]
    return selected


def _slope(rows: list[list[WordBox]]) -> float:
    slopes = []
    for row in rows:
        words = [w for w in row if w.y1 - w.y0 >= 3]
        if not words:
            continue
        first = words[0]
        for word in words[1:]:
            span = (word.x0 + word.x1 - first.x0 - first.x1) / 2
            if span > 75:
                slopes.append((word.y0 + word.y1 - first.y0 - first.y1) / (2 * span))
    return median(slopes) if slopes else 0


def _line_image(image, row: list[WordBox], slope: float) -> Image.Image:
    left, right = min(w.x0 for w in row), max(w.x1 for w in row)
    center = (left + right) / 2
    leveled = [slope * ((w.x0 + w.x1) / 2 - center) for w in row]
    top = min(w.y0 - delta for w, delta in zip(row, leveled)) - 2.5
    bottom = max(w.y1 - delta for w, delta in zip(row, leveled)) + 2.5
    left -= 3
    scale = image.scale
    offset_x, offset_y = image.bbox[:2]
    return image.original.transform(
        (max(1, int((right + 3 - left) * scale)), max(1, int((bottom - top) * scale))),
        Image.Transform.AFFINE,
        (1, 0, (left - offset_x) * scale, slope, 1, (top + slope * (left - center) - offset_y) * scale),
        resample=Image.Resampling.BICUBIC,
        fillcolor="white",
    )


def _read_sloped_lines(pdf_path: Path, selected: list[list[WordBox]], tilt: float, lines: list[str]) -> bool:
    from tesserocr import PSM, PyTessBaseAPI

    require_remaining_ms()
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        dpi = OCR_DPI
        if len(page.images) == 1 and page.images[0]["bits"] == 1:
            raster = page.images[0]
            # Upsampling a bilevel source can merge tiny punctuation with
            # neighbouring strokes. Its native resolution preserves the dots.
            dpi = min(dpi, max(150, round(raster["srcsize"][0] * 72 / raster["width"])))
        require_remaining_ms()
        image = page.to_image(resolution=dpi)
        require_remaining_ms()
        with PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.SINGLE_LINE) as api:
            for i, row in enumerate(selected):
                require_remaining_ms()
                api.SetImage(_line_image(image, row, tilt))
                api.SetSourceResolution(dpi)
                if not api.Recognize(timeout=require_remaining_ms(CROP_TIMEOUT_MS)):
                    return False
                candidate = api.GetUTF8Text().strip()
                if not candidate:
                    return False
                # Reject inserted words from adjacent rows. Minor punctuation
                # and spacing changes within an identifier are allowed.
                if (
                    (
                        api.MeanTextConf() >= 75
                        or (lines[i].casefold() == candidate.casefold() and api.MeanTextConf() >= 65)
                    )
                    and ratio(lines[i].casefold(), candidate.casefold()) >= 85
                    and len(candidate.split()) <= len(lines[i].split())
                    and (not lines[i].isupper() or candidate.isupper())
                ):
                    lines[i] = candidate
    return True


def reread_title(pdf_path: Path | None, boxes: list[WordBox], primary_title: str | None) -> str | None:
    """Return a reconstructed value only when a unique labelled cell supports it."""
    rows = _rows(boxes)
    sizes = [w.y1 - w.y0 for row in rows for w in row if len(w.text) > 1 and w.y1 > w.y0]
    if not sizes:
        return None
    selected = _title_rows(rows, median(sizes))
    if not selected or len(selected) > 6:
        return None
    lines = [" ".join(w.text for w in row) for row in selected]
    geometric = " ".join(lines)
    if len(geometric) > 600:
        return None
    # A scrambled multiline title may already contain the right words in a
    # different order. Otherwise the existing and reconstructed cells must agree.
    if (
        primary_title
        and ratio(primary_title.casefold(), geometric.casefold()) < 80
        and not set(primary_title.split()) <= set(geometric.split())
    ):
        return None
    tilt = _slope(rows)
    if pdf_path and 0.015 < abs(tilt) < 0.12:
        try:
            if not _read_sloped_lines(pdf_path, selected, tilt, lines):
                return None
        except (OSError, RuntimeError, ValueError, PdfminerException, RereadExpired):
            # The first pass already established the receipt. Keep its fields.
            return None
    # Reuse native quote handling and boundaries for another labelled field on
    # the same physical line as the title.
    result = _title(_field_text("Tytuł: " + "\n".join(lines)))
    return result if result != primary_title else None
