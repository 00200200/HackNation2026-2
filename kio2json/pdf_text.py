"""Page text: the PDF text layer, with Polish Tesseract OCR for pages that have none."""

import re
from contextlib import ExitStack
from functools import cache
from importlib.metadata import files
from pathlib import Path
from typing import NamedTuple

import pdfplumber

from .ocr_normalize import MAIL_TOKEN_RE, confirmed_email, normalize_ocr

# The organizer README says the key information sits on the first three pages.
MAX_PAGES = 3
OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 60


PAGE_NUMBER_RE = re.compile(
    r"\s*[-–—]?\s*(?:(?:strona|str\.|page)\s*)?\d+(?:\s*(?:z|/|of)\s*\d+)?\s*[-–—]?\s*", re.IGNORECASE
)


class WordBox(NamedTuple):
    """Printed word in PDF points. Page numbers start at 1 and y increases downwards."""

    page: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@cache
def _language_dir() -> str:
    for entry in files("kio-polish-ocr-data") or ():
        if entry.name == "pol.traineddata" and entry.locate().is_file():
            return str(entry.locate().parent)
    raise FileNotFoundError("Polish OCR data missing from the kio-polish-ocr-data installation")


def _ocr(page, words: list[WordBox] | None) -> str:
    """Recognize the page and verify suspect e-mail separators against their image crops."""
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

    image = page.to_image(resolution=OCR_DPI)
    with ExitStack() as stack:
        api = stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.AUTO))
        api.SetImage(image.original)
        if not api.Recognize(timeout=1000 * OCR_TIMEOUT_SECONDS):
            raise RuntimeError("Polish OCR failed or timed out")
        text = api.GetUTF8Text()
        iterator = api.GetIterator() if text.strip() else None
        english = None
        cursor = 0
        if iterator is not None:
            left, top = image.bbox[:2]
            for item in iterate_level(iterator, RIL.WORD):
                box = item.BoundingBox(RIL.WORD)
                if not box:
                    continue
                token = item.GetUTF8Text(RIL.WORD)
                x0, y0, x1, y1 = box
                if words is not None:
                    words.append(
                        WordBox(
                            page.page_number,
                            token,
                            left + x0 / image.scale,
                            top + y0 / image.scale,
                            left + x1 / image.scale,
                            top + y1 / image.scale,
                        )
                    )
                start = text.find(token, cursor)
                if start < 0:
                    continue
                cursor = start + len(token)
                if not MAIL_TOKEN_RE.fullmatch(token):
                    continue
                if english is None:
                    english = stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang="eng", psm=PSM.SINGLE_WORD))
                # Include the edges of ascenders, descenders and punctuation.
                crop = (
                    max(x0 - 8, 0),
                    max(y0 - 8, 0),
                    min(x1 + 8, image.original.width),
                    min(y1 + 8, image.original.height),
                )
                english.SetImage(image.original.crop(crop))
                if english.Recognize(timeout=1000):
                    replacement = confirmed_email(token, english.GetUTF8Text().strip())
                    text = text[:start] + replacement + text[cursor:]
                    cursor = start + len(replacement)
    return "\n".join(line for line in text.splitlines() if line.strip())


def read_pages(
    pdf_path: Path, max_pages: int = MAX_PAGES, force_ocr: bool = False, *, word_boxes: list[WordBox] | None = None
) -> list[str]:
    """Read page text. Pass a list for raw word boxes in the same pass, before OCR substitutions."""
    pages = []
    words = [] if word_boxes is not None else None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            text = "" if force_ocr else page.extract_text() or ""
            has_content = any(line.strip() and not PAGE_NUMBER_RE.fullmatch(line) for line in text.splitlines())
            if not has_content:
                text = normalize_ocr(_ocr(page, words))
            elif words is not None:
                words.extend(
                    WordBox(page.page_number, w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                    for w in page.extract_words()
                )
            pages.append(text)
    if word_boxes is not None and words:
        word_boxes.extend(words)
    return pages


def join_pages(pages: list[str]) -> str:
    """Join pages into one text without 'Strona 1 z 11' footers and running headers."""
    first_lines = [page.split("\n", 1)[0] for page in pages]
    kept = []
    for index, page in enumerate(pages):
        lines = page.split("\n")
        if index > 0 and first_lines.count(lines[0]) > 1:
            lines = lines[1:]
        kept.extend(line for line in lines if not re.fullmatch(r"\s*Strona \d+ z \d+\s*", line))
    return "\n".join(kept)
