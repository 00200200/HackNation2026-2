"""Recover printed values from aligned cards after a transfer has been classified."""

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise

from .bank_transfer import (
    AMOUNT_LABEL,
    BOUNDARY_RE,
    DATE_LABEL,
    DIRECT_ROLE,
    MONEY,
    REFERENCE_LABEL,
    REFERENCE_RE,
    REMITTANCE_WITH_REFERENCE,
    TITLE_LABEL,
    _amount,
)
from .common import to_iso
from .pdf_text import WordBox
from .receipt_layout import LABELS, _cell_value, word_rows

_OPERATION = r"(?:przelewu|płatności|operacji|transakcji)"
_DATE = re.compile(
    rf"(?:{DATE_LABEL}(?: {_OPERATION})?|(?:data|dzień|termin) "
    rf"(?:realizacji|wykonania|obciążenia|księgowania|zaksięgowania|rozliczenia|wykonanej|wykonanego)(?: {_OPERATION})?"
    rf"|(?:wykonano|zrealizowano|zaksięgowano)(?: (?:w dniu|dnia))?)",
    re.IGNORECASE,
)
_AMOUNT = re.compile(
    rf"(?:{AMOUNT_LABEL}|(?:suma|kwota|wartość) (?:obciążenia|rozliczona|zaksięgowana)"
    r"|(?:kwota |suma |wartość )?obciążenia rachunku|(?:obciążenie|obciążono)(?: rachunek| rachunku)?)",
    re.IGNORECASE,
)
_TITLE = re.compile(rf"(?:{TITLE_LABEL}|(?:opis|treść|cel) {_OPERATION})", re.IGNORECASE)
_STOP = re.compile(
    rf"(?:{REFERENCE_LABEL}|referencj[ae](?: (?:banku|klienta|{_OPERATION}))?|"
    r"(?:data|dzień) (?:wydruku|sporządzenia|wygenerowania|wystawienia|waluty)|"
    r"(?:opłata|prowizja|saldo)(?: bankow[ae]| po operacji)?)",
    re.IGNORECASE,
)
_KNOWN = {phrase for phrases in LABELS.values() for phrase in phrases}


def _caption(text):
    head, colon, inline = text.partition(":")
    label = head.strip().casefold()
    for field, pattern in (("tytul", _TITLE), ("kwota", _AMOUNT), ("data_operacji", _DATE)):
        if pattern.fullmatch(label):
            return field, head, inline.strip()
    if (
        label in _KNOWN
        or REFERENCE_RE.fullmatch(text)
        or DIRECT_ROLE.fullmatch(label)
        or _STOP.fullmatch(label)
        or re.fullmatch(
            r"(?:(?:nr\.?|numer) )?(?:kont[oa]|rachun(?:ek|ku)) (?:adresata|płatnika|nadawcy|odbiorcy|zleceniodawcy|beneficjenta)",
            label,
        )
        # A reference prefix may also begin a wrapped purpose line. Only a
        # complete caption, explicit colon or document footer ends that value.
        or (
            (colon or label.startswith(("bank ", "dokument ", "signature ", "potwierdzenie ")))
            and BOUNDARY_RE.match(text)
            and not REMITTANCE_WITH_REFERENCE.match(text)
        )
    ):
        return "", head, inline.strip()
    return None


@dataclass
class CardLine:
    index: int
    row: int
    top: float
    bottom: float
    text: str


def _streams(boxes):
    rows, height = word_rows(boxes)
    streams = defaultdict(list)
    physical = []
    for row_index, row in enumerate(rows):
        parts = [[]]
        for word in row:
            if parts[-1] and word.x0 - parts[-1][-1].x1 > 1.5 * height:
                parts.append([])
            parts[-1].append(word)
        for words in parts:
            x = words[0].x0
            anchor = min(streams, key=lambda a: abs(a - x), default=x)
            if abs(anchor - x) > 0.65 * height:
                anchor = x
            cell = CardLine(
                len(physical),
                row_index,
                min(w.y0 for w in words),
                max(w.y1 for w in words),
                " ".join(w.text for w in words),
            )
            streams[anchor].append(cell)
            physical.append(cell)
    # A value-only track can belong to captions on its left. Require two
    # independently aligned rows before treating their common gutter as label/value.
    for left, right in pairwise(sorted(streams)):
        labels = streams[left]
        values = streams[right]
        if not labels or not values or any(_caption(v.text) for v in values):
            continue
        starts = {v.index for v in values}
        aligned = [
            line
            for line in labels
            if line.index + 1 in starts and abs(physical[line.index + 1].top - line.top) < 0.65 * height
        ]
        if len(aligned) >= 2 and all((c := _caption(line.text)) and not c[2] for line in aligned):
            streams[left] = sorted(labels + values, key=lambda line: line.index)
            streams[right] = []
    return streams.values(), physical, height


def _title_agrees(old, source, label_words, first_value):
    """Match the old reading verbatim, starting in the caption and reaching its value."""
    if old is None:
        return True
    words = old.split()
    return any(
        start + len(words) > first_value and source[start : start + len(words)] == words
        for start in range(label_words + 1)
    )


def _complete_title(old, stream, physical, owned, start, stop, height, caption, values):
    _, label, inline = caption
    title = " ".join(values)
    if not re.search(r"[^\W\d_]", title) or re.fullmatch(r"[Xx*•\s.-]+", title):
        return None
    if any(_cell_value("Kwota", line, False) or _cell_value("Data operacji", line, False) for line in values):
        return None
    boundary = stream[stop].index if stop < len(stream) else len(physical)
    if any(line.index not in owned for line in physical[stream[start].index : boundary]):
        return None
    if old is None or old == title:
        return title
    # Include the next caption and its first value so a linear read which spilled
    # into that cell can be shortened. All other removed words must share a row
    # with the title in the original physical reading order.
    end = stop
    if end < len(stream) and stream[end].top - stream[end - 1].bottom <= 2 * height:
        end += 1
        if (
            end < len(stream)
            and not _caption(stream[end].text)
            and stream[end].top - stream[end - 1].bottom <= 2 * height
        ):
            end += 1
    start_line = stream[start]
    last_line = stream[end - 1]
    count = len(label.split())
    for lines in (stream[start:end], physical[start_line.index : last_line.index + 1]):
        prefix = (
            next((n for n, line in enumerate(lines) if line.index == stream[start + 1].index), 0) if not inline else 0
        )
        first_value = sum(len(line.text.split()) for line in lines[:prefix]) if not inline else count
        source = [
            word.rstrip(":") if pos == 0 else word for pos, line in enumerate(lines) for word in line.text.split()
        ]
        if _title_agrees(old, source, count, first_value):
            return title
    return None


def apply_receipt_cards(fields: dict, boxes: list[WordBox]) -> None:
    streams, physical, height = _streams(boxes)
    observations = defaultdict(list)
    labelled = [(stream, [_caption(line.text) for line in stream]) for stream in streams]
    # Unassigned tracks can contain indented continuations. A missing track
    # boundary is insufficient evidence to shorten a title across those words.
    row_sets = [{line.row for line in stream} for stream, _ in labelled]
    owned = []
    for stream, captions in labelled:
        active = False
        assigned = set()
        for i, (line, caption) in enumerate(zip(stream, captions, strict=True)):
            active = bool(caption) or (active and line.top - stream[i - 1].bottom <= 2 * height)
            if active:
                assigned.add(line.index)
        owned.append(assigned)
    for (stream, captions), rows in zip(labelled, row_sets, strict=True):
        # A side column must actually share a printed row with this track.
        neighbours = set().union(*(lines for other, lines in zip(row_sets, owned, strict=True) if rows & other))
        for i, caption in enumerate(captions):
            if not caption or not caption[0]:
                continue
            field, _, inline = caption
            values = [inline] if inline else []
            j = i + 1
            while j < len(stream) and not captions[j] and stream[j].top - stream[j - 1].bottom <= 2 * height:
                values.append(stream[j].text)
                j += 1
            # An ambiguous, empty or masked occurrence still counts against uniqueness.
            candidate = None
            if field == "tytul" and 0 < len(values) <= 6 and (j == len(stream) or captions[j]):
                candidate = _complete_title(fields[field], stream, physical, neighbours, i, j, height, caption, values)
            elif len(values) == 1:
                if field == "data_operacji" and (day := _cell_value("Data operacji", values[0], False)):
                    candidate = to_iso(day)
                elif (
                    field == "kwota"
                    and _cell_value("Kwota", values[0], False)
                    and (match := re.search(MONEY, values[0]))
                ):
                    candidate = _amount(match[0])
            observations[field].append(candidate)
    for field, values in observations.items():
        if len(values) == 1 and values[0] is not None and (field == "tytul" or fields[field] is None):
            fields[field] = values[0]
