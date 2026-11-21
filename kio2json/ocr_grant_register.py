"""Verify labelled register digits on a grant using their original word box."""

import itertools
import re
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

import pdfplumber

from .ocr_budget import remaining_ms
from .pdf_text import OCR_DPI, WordBox, _language_dir

LABEL = re.compile(r"\bKRS\s*:?\s*(\d{10})(?!\d)", re.IGNORECASE)


def _agreement(crop, readers, original: str) -> str:
    values = []
    for reader in readers:
        reader.SetImage(crop)
        timeout = remaining_ms(1000)
        if not timeout or not reader.Recognize(timeout=timeout):
            return original
        result = re.fullmatch(r"(\d{10})[,.;:]?", reader.GetUTF8Text().strip())
        if not result:
            return original
        values.append(result[1])
    if len(set(values)) == 1 and sum(a != b for a, b in zip(original, values[0], strict=True)) == 1:
        return values[0]
    return original


def verified_pages(pdf: Path, pages: list[str], boxes: list[WordBox]) -> list[str]:
    from tesserocr import PSM, PyTessBaseAPI

    candidates = defaultdict(list)
    for label, box in itertools.pairwise(boxes):
        if label.page != box.page or label.text.strip(":").upper() != "KRS":
            continue
        number = box.text.rstrip(",.;:")
        if number.isascii() and number.isdigit() and len(number) == 10:
            candidates[box.page].append((number, box))
    if not candidates or not remaining_ms(1):
        return pages
    result = pages.copy()
    try:
        with ExitStack() as stack:
            doc = stack.enter_context(pdfplumber.open(pdf))
            readers = [
                stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang=language, psm=PSM.SINGLE_WORD))
                for language in ("eng", "pol")
            ]
            for index, items in candidates.items():
                if not remaining_ms(1):
                    break
                page = doc.pages[index - 1]
                image = page.to_image(resolution=OCR_DPI)
                verified = defaultdict(set)
                for pos, (number, box) in enumerate(items):
                    if not remaining_ms(1):
                        # A repeated number with an unverified occurrence keeps its primary value.
                        for original, _ in items[pos:]:
                            verified[original].add(original)
                        break
                    x0, y0, x1, y1 = image._reproject_bbox((box.x0, box.y0, box.x1, box.y1))
                    crop = image.original.crop((x0 - 4, y0 - 4, x1 + 4, y1 + 4))
                    verified[number].add(_agreement(crop, readers, number))

                def substitute(match: re.Match, readings=verified) -> str:
                    values = readings[match[1]]
                    return match[0][:-10] + next(iter(values)) if len(values) == 1 else match[0]

                result[index - 1] = LABEL.sub(substitute, pages[index - 1])
    except (OSError, RuntimeError):
        # Rendering or recognizing an optional crop must preserve the primary reading.
        return pages
    return result
