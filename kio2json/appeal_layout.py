"""Rejoin a column of role labels to the adjacent values in a scanned appeal."""

import re
from pathlib import Path

from .pdf_text import WordBox, read_pages

_ROLE = r"(?:zamawiający|odwołujący|wykonawca|pełnomocnik odwołującego|nazwa postępowania):"
DETACHED_ROLES = re.compile(rf"(?im)^({_ROLE})[ \t]*\n({_ROLE})[ \t]*$")


def restore_labels(page: str, words: list[WordBox]) -> str:
    lines = page.splitlines()
    insertions = {}
    omitted = set()
    for index, label in enumerate(lines):
        label = label.strip()
        if not re.fullmatch(_ROLE, label, re.IGNORECASE):
            continue
        # The colon ends the label even when it consists of several words.
        ends = [w for w in words if w.text.casefold() == label.split()[-1].casefold()]
        if len(ends) != 1:
            continue
        end = ends[0]
        adjacent = sorted(
            (w for w in words if w.x0 > end.x1 and abs((w.y0 + w.y1 - end.y0 - end.y1) / 2) < (end.y1 - end.y0) * 0.65),
            key=lambda w: w.x0,
        )
        if not adjacent:
            continue
        row = " ".join(w.text for w in adjacent)
        matches = [n for n, line in enumerate(lines) if " ".join(line.split()) == row]
        if not matches:
            prefix = " ".join(w.text for w in adjacent[:2])
            matches = [n for n, line in enumerate(lines) if line == prefix or line.startswith(prefix + " ")]
        if len(matches) == 1 and matches[0] not in insertions:
            insertions[matches[0]] = label
            omitted.add(index)
    return "\n".join(
        (insertions[n] + " " if n in insertions else "") + line for n, line in enumerate(lines) if n not in omitted
    )


def restore_party_columns(
    path: Path,
    pages: list[str],
    force_ocr: bool,
    *,
    engine: str | None = None,
    boxes: list[WordBox] | None = None,
    ocr_pages: list[int] | None = None,
) -> list[str]:
    detached = [i for i, page in enumerate(pages) if DETACHED_ROLES.search(page)]
    if not detached:
        return pages
    if boxes is None or not all(i + 1 in (ocr_pages or []) for i in detached):
        boxes = []
        read_pages(path, max_pages=max(detached) + 1, force_ocr=force_ocr, word_boxes=boxes, engine=engine)
    return [
        restore_labels(page, [w for w in boxes if w.page == i + 1]) if i in detached else page
        for i, page in enumerate(pages)
    ]
