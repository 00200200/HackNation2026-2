"""Compare suspect parts of a searchable scan with the ink in the corresponding field."""

import re
from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from pdfplumber.utils import cluster_objects, extract_words
from pdfplumber.utils.exceptions import PdfminerException
from rapidfuzz.distance import Levenshtein
from stdnum.pl import nip

from .accounts import valid_account
from .ocr_budget import RereadExpired, remaining_ms
from .ocr_choices import Cell, verify_cells
from .pdf_text import WordBox, _fits_parallel_batch
from .receipt_layout import word_rows

# Accept a short printed value as evidence for a reread. Only a complete, valid
# value from the same image location can supply the missing characters.
_ACCOUNT = re.compile(r"(?<![\w*/-])((?:PL[ ]*)?[0-9](?:[ ]*[0-9]){23,25})(?![\w*/-]|[ ]*[0-9])", re.IGNORECASE)
_NIP = re.compile(r"\bNIP\s*[:.-]?\s*([0-9](?:[- ]?[0-9]){7,9})(?!\w|[- ]?[0-9])", re.IGNORECASE)
_MARKER = re.compile(r"^(?:[^\W\d_]+ nr )?(\(?[0-9Il]{1,2}(?:\.[0-9Il]{1,2})*[.)]|[0-9]{1,2}) ", re.IGNORECASE)
_ACCOUNT_LABEL = re.compile(r"\b(?:rachun\w+|kont[oa]|iban)\b", re.IGNORECASE)
_MASK = re.compile(r"[*Xx•?]{2,}")
_GARBLED = re.compile(r"\b[^\W\d_]{2,}\d[^\W\d_]+\b")


@dataclass
class Row:
    text: str
    words: list[WordBox]

    @property
    def y(self):
        return median((w.y0 + w.y1) / 2 for w in self.words)


def _compact(value):
    return re.sub(r"[- ]", "", value).upper()


def _native_rows(page, text, spacing):
    # The text map retains exact source positions, including a label fused to a field.
    if len(text) > 65_536 or text.count("\n") > 512 or len(text.split()) > 4_096:
        return []
    mapping = page.get_textmap(**spacing)
    if mapping.as_string != text:
        return []
    words = iter(mapping.search(r"\S+", return_groups=False, return_chars=False))
    rows = []
    for line in text.splitlines():
        boxes = []
        for _ in line.split():
            box = next(words)
            boxes.append(WordBox(page.page_number, box["text"], box["x0"], box["top"], box["x1"], box["bottom"]))
        if not boxes or line != " ".join(w.text for w in boxes):
            return []
        rows.append(Row(line, boxes))
    return rows


def _unprinted_rows(page, rows):
    # Bound the inexpensive alignment check even for unusually large page dimensions.
    dpi = min(96, int(96 * 1000 / max(page.width, page.height, 1)))
    if dpi < 12:
        return set()
    image = page.to_image(resolution=dpi)
    left, top = image.bbox[:2]
    missing = set()
    pixel_budget = 4 * image.original.width * image.original.height
    with image.original, image.original.convert("L") as gray, gray.point(lambda v: 255 if v < 160 else 0) as ink:
        for i, row in enumerate(rows):
            sampled = [w for w in row.words if len(w.text) >= 3 and any(c.isalnum() for c in w.text)]
            if not sampled:
                continue
            empty = 0
            for w in sampled:
                bounds = (
                    max(0, round((w.x0 - left) * image.scale)),
                    max(0, round((w.y0 - top) * image.scale)),
                    min(ink.width, round((w.x1 - left) * image.scale)),
                    min(ink.height, round((w.y1 - top) * image.scale)),
                )
                if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                    pixel_budget -= (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                    if pixel_budget < 0:
                        return missing
                    with ink.crop(bounds) as crop:
                        empty += crop.getbbox() is None
            if empty and empty * 2 >= len(sampled):
                missing.add(i)
    return missing


def _collision_rows(page, spacing):
    rows = page.get_textmap(**spacing).extract_text_lines()
    collisions = {}
    for i, row in enumerate(rows):
        chars = sorted((c for c in row["chars"] if c["text"].strip()), key=lambda c: c["x0"])
        # A shifted line can collide with a second baseline within pdfplumber's
        # three-point line tolerance and interleave the glyphs from both rows.
        overlap = sum(
            abs(a["top"] - b["top"]) >= 0.5 and a["x1"] - b["x0"] >= 0.5 * (b["x1"] - b["x0"])
            for a, b in pairwise(chars)
        )
        if overlap < 3:
            continue
        groups = cluster_objects(row["chars"], "top", tolerance=0.4)
        if 2 <= len(groups) <= 3:
            parts = []
            for group in groups:
                boxes = [
                    WordBox(page.page_number, w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                    for w in extract_words(group, **spacing)
                ]
                if boxes:
                    parts.append(Row(" ".join(w.text for w in boxes), boxes))
            if len(parts) >= 2:
                collisions[i] = parts
    return collisions


def _ordinal(marker):
    return tuple(int(value) if value.isdigit() else 0 for value in re.findall(r"[0-9Il]+", marker[1], re.IGNORECASE))


def _marker_targets(rows):
    items = [(i, marker) for i, row in enumerate(rows) if (marker := _MARKER.match(row.text))]
    targets = {}
    for pos, (i, marker) in enumerate(items):
        ordinal = _ordinal(marker)
        expected = None
        if pos + 1 < len(items):
            following = _ordinal(items[pos + 1][1])
            if following[-1] == 2 and len(following) == len(ordinal):
                expected = (*following[:-1], 1)
        if expected is None and i and rows[i - 1].text.endswith(":"):
            expected = (1,) * len(ordinal)
        if expected and ordinal != expected:
            targets[i] = marker, expected
    return targets


def _restore_digits(printed, candidate):
    """Apply the checksum-confirmed edits to digits, retaining the layer's group spacing."""
    indices = [i for i, char in enumerate(printed) if char not in "- "] + [len(printed)]
    for action, src, dest in reversed(Levenshtein.editops(_compact(printed), candidate)):
        i = indices[src]
        if action == "insert":
            printed = printed[:i] + candidate[dest] + printed[i:]
        elif action == "replace":
            printed = printed[:i] + candidate[dest] + printed[i + 1 :]
        else:
            printed = printed[:i] + printed[i + 1 :]
    return printed


def _replace(row, start, end, replacement):
    text = row.text[:start] + replacement + row.text[end:]
    tokens = text.split()
    if len(tokens) == len(row.words):
        row.text = text
        row.words = [word._replace(text=token) for word, token in zip(row.words, tokens, strict=True)]


def _nearby_word(native, printed):
    return abs((native.y0 + native.y1 - printed.y0 - printed.y1) / 2) <= max(3, (native.y1 - native.y0) * 0.65)


def _image_span(row, start, end, image_words):
    # Localize the field independently of OCR line breaks or column reading order.
    spans = zip(re.finditer(r"\S+", row.text), row.words, strict=True)
    field = [w for match, w in spans if start < match.end() and match.start() < end]
    margin = max(3, (field[0].y1 - field[0].y0) * 0.75)
    nearby = [
        w
        for w in image_words
        if _nearby_word(field[0], w) and field[0].x0 - margin <= (w.x0 + w.x1) / 2 <= field[-1].x1 + margin
    ]
    return sorted(nearby, key=lambda w: w.x0)


def _repair_digits(row, match, kind, image_words, path, labelled_account):
    start, end = match.span(1)
    old = _compact(match[1])
    nearby = _image_span(row, start, end, image_words)
    seen = " ".join(w.text for w in nearby)
    pattern = r"(?<!\w)([0-9](?:[ -]*[0-9]){9})(?!\w)" if kind == "nip" else _ACCOUNT
    valid = nip.is_valid if kind == "nip" else valid_account
    candidates = [
        (new, value)
        for value in re.finditer(pattern, seen)
        if (new := _compact(value[1]))[:2].isalpha() == old[:2].isalpha()
        and Levenshtein.distance(old, new, score_cutoff=2) <= 2
    ]
    if len(candidates) != 1:
        return
    new, value = candidates[0]
    if old == new:
        return
    if not valid(new):
        # A printed bank account can itself have a bad check digit. Restore one omission
        # only in a labelled, unmasked field and only after confirming every printed glyph.
        if not (
            kind == "account"
            and path is not None
            and labelled_account
            and not _MASK.search(row.text)
            and len(old.removeprefix("PL")) == 25
            and len(new.removeprefix("PL")) == 26
            and Levenshtein.distance(old, new) == 1
            and remaining_ms(1)
        ):
            return
        words = [
            w
            for span, w in zip(re.finditer(r"\S+", seen), nearby, strict=True)
            if value.start(1) < span.end() and span.start() < value.end(1)
        ]
        # verify_cells retains an invalid literal only on unambiguous LSTM symbol choices.
        key = "z_rachunku"
        record = {key: None}
        verify_cells(path, lambda record, words: [Cell(record, key, new, words)], record, words)
        if record[key] != new:
            return
    _replace(row, start, end, _restore_digits(match[1], new))


def _same_line(native, printed):
    return (
        len(native.words) == len(printed.words)
        and Levenshtein.normalized_similarity(native.text.casefold(), printed.text.casefold(), score_cutoff=0.95)
        >= 0.95
        and re.findall(r"\d+", native.text) == re.findall(r"\d+", printed.text)
    )


def _relocated_rows(rows, printed, misplaced, collisions):
    originals = [r for i, row in enumerate(rows) for r in collisions.get(i, [row])]
    moves = {}
    for i in misplaced | collisions.keys():
        parts = collisions.get(i, [rows[i]])
        relocated = []
        for part in parts:
            equal = [r for r in printed if _same_line(part, r)]
            if len(equal) != 1 or sum(_same_line(native, equal[0]) for native in originals) != 1:
                break
            boxes = [w._replace(text=n.text) for n, w in zip(part.words, equal[0].words, strict=True)]
            relocated.append(Row(part.text, boxes))
        if len(relocated) == len(parts) and any(
            abs(r.y - p.y) > max(p.words[0].y1 - p.words[0].y0, 4) for r, p in zip(relocated, parts, strict=True)
        ):
            moves[i] = relocated

    return moves


def repair_layer(page, text, spacing, recognize):
    """Return a corrected native reading and matching boxes, or keep the original."""
    if not remaining_ms(1) or not _fits_parallel_batch([page]):
        return None
    try:
        rows = _native_rows(page, text, spacing)
        if not rows:
            return None
        ids = {
            i: sorted(
                [(m, "nip") for m in _NIP.finditer(row.text) if not nip.is_valid(_compact(m[1]))]
                + [(m, "account") for m in _ACCOUNT.finditer(row.text) if not valid_account(_compact(m[1]))],
                key=lambda item: item[0].start(),
                reverse=True,
            )
            for i, row in enumerate(rows)
        }
        markers = _marker_targets(rows)
        garbled = {i for i, row in enumerate(rows) if _GARBLED.search(row.text)}
        collisions = _collision_rows(page, spacing)
        misplaced = _unprinted_rows(page, rows)
        if not (any(ids.values()) or markers or garbled or misplaced or collisions) or not remaining_ms(1):
            return None
        image_words = []
        recognize(page, image_words, reread=True)
        if not image_words or len(image_words) > 4_096 or not remaining_ms(1):
            return None
    except (RereadExpired, OSError, RuntimeError, ValueError, PdfminerException):
        return None

    printed = [Row(" ".join(w.text for w in words), words) for words in word_rows(image_words, page.page_number)[0]]
    moves = _relocated_rows(rows, printed, misplaced, collisions)
    image_words = [w for row in printed for w in row.words]
    short_accounts = sum(
        kind == "account" and len(_compact(match[1]).removeprefix("PL")) == 25
        for fields in ids.values()
        for match, kind in fields
    )
    for i, row in enumerate(rows):
        if i in moves:
            continue
        for match, kind in ids[i]:
            labelled = short_accounts <= 2 and any(_ACCOUNT_LABEL.search(r.text) for r in rows[max(0, i - 1) : i + 1])
            _repair_digits(row, match, kind, image_words, page.pdf.path, labelled)
        if i in markers:
            marker, expected = markers[i]
            for other in printed:
                first = _MARKER.match(other.text)
                if (
                    first
                    and _ordinal(first) == expected
                    and _nearby_word(row.words[0], other.words[0])
                    and Levenshtein.normalized_similarity(
                        row.text[marker.end() :].casefold(), other.text[first.end() :].casefold()
                    )
                    >= 0.9
                ):
                    _replace(row, *marker.span(1), first[1])
                    break
        if i in garbled:
            for match in reversed(list(_GARBLED.finditer(row.text))):
                words = _image_span(row, *match.span(), image_words)
                seen = " ".join(w.text for w in words).strip(".,;:()")
                if seen.isalpha() and Levenshtein.distance(match[0].casefold(), seen.casefold()) == 1:
                    _replace(row, *match.span(), seen)
    if moves:
        # Keep the order and coordinates of all readings without a confirmed move.
        fixed = [r for i, r in enumerate(rows) if i not in moves]
        for r in sorted((r for parts in moves.values() for r in parts), key=lambda r: r.y):
            fixed.insert(next((j for j, other in enumerate(fixed) if other.y > r.y), len(fixed)), r)
        rows = fixed
    revised = "\n".join(row.text for row in rows)
    if revised != text or moves:
        return revised, [w for row in rows for w in row.words]
    return None
