"""Restore reading order when OCR emits a bank form's label and value columns separately."""

import re
from statistics import median

from rapidfuzz.distance import Levenshtein

from .ocr_normalize import normalize_ocr
from .pdf_text import WordBox

BOOKING_HEADINGS = (
    "potwierdzenie wykonania operacji",
    "potwierdzenie wykonanej operacji",
    "potwierdzenie zaksięgowania transakcji",
)
DETACHED_LABEL = re.compile(
    r"(?im)^(?:kwota|tytułem|numer transakcji|rachunek beneficjenta|data obciążenia|z rachunku)\s*:?$"
)


def booking_heading(line: str) -> bool:
    heading = line.strip(" |:/").casefold()
    return any(Levenshtein.distance(heading, template, score_cutoff=2) <= 2 for template in BOOKING_HEADINGS)


def has_detached_labels(pages: list[str]) -> bool:
    return bool(
        pages
        and len(DETACHED_LABEL.findall(pages[0])) >= 3
        and any(line.strip().casefold().startswith("potwierdzenie ") for line in pages[0].splitlines())
    )


def restore_receipt_rows(pages: list[str], boxes: list[WordBox]) -> list[str]:
    words = [b for b in boxes if b.page == 1 and b.text.strip() and b.y1 > b.y0]
    if not words:
        return pages
    # Small OCR differences in the tops of capitals and descenders still belong to one baseline.
    tolerance = 0.65 * median(w.y1 - w.y0 for w in words)
    rows = []
    baseline = float("-inf")
    for word in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        center = (word.y0 + word.y1) / 2
        if center - baseline > tolerance:
            rows.append([])
            baseline = center
        rows[-1].append(word)
    text = "\n".join(" ".join(w.text for w in sorted(row, key=lambda w: w.x0)) for row in rows)
    # Reordering must actually place a field opposite its value.
    if not re.search(r"(?im)^kwota\s*:?\s+[−-]?\d", text):
        return pages
    return [normalize_ocr(text), *pages[1:]]
