"""Page text: the PDF text layer, with selectable local OCR for pages that have none."""

import os
import re
from collections.abc import Iterator
from contextlib import ExitStack
from functools import cache, partial
from importlib.metadata import files
from pathlib import Path
from typing import NamedTuple

import pdfplumber
from pdfplumber.utils import get_bbox_overlap, obj_to_bbox

from .ocr_normalize import MAIL_TOKEN_RE, confirmed_email, normalize_ocr

# The organizer README says the key information sits on the first three pages.
MAX_PAGES = 3
OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 60
DEFAULT_OCR_ENGINE = "tesseract-dpi"
TESSERACT_ENGINES = frozenset({"tesseract", "tesseract-dpi", "hybrid"})
OCR_ENGINES = TESSERACT_ENGINES | {"rapidocr"}


class NoReadableTextError(RuntimeError):
    """Required OCR finished without finding any document text."""


class OCRRecognitionError(RuntimeError):
    """The OCR engine failed or timed out while recognizing a page."""


MIN_OCR_WORDS = 2
_WORD = re.compile(r"\b[^\W\d_]{2,}\b")
_COUNTER_SEPARATOR = re.compile(r"[/\\|⁄∕–—−-]|z|of|sur|von|van|de|di|din|av|af|iz|na", re.IGNORECASE)
_NUMBER_MARKERS = {"n", "nº", "nr", "no", "numer", "number", "numbered"}
_PAGE_LABELS = {
    "str",
    "strona",
    "strony",
    "stron",
    "kartka",
    "karta",
    "arkusz",
    "p",
    "page",
    "pages",
    "sheet",
    "leaf",
    "leaves",
    "blatt",
    "seite",
    "feuillet",
}


def _is_page_counter(line: str) -> bool:
    line = line.strip()
    if len(line) > 64:
        return False
    numbers = list(re.finditer(r"\d+", line))
    if len(numbers) not in (1, 2):
        return False
    before = re.findall(r"[^\W\d_]+", line[: numbers[0].start()].lower())
    after = re.findall(r"[^\W\d_]+", line[numbers[-1].end() :].lower())
    label_words = len(before) + len(after)
    if label_words > 2:
        return False
    # Two genuine words with a reference or range (e.g. an invoice) are body text.
    if label_words == 2 and not _PAGE_LABELS.intersection(before + after):
        return False
    if len(numbers) == 2:
        separator = line[numbers[0].end() : numbers[1].start()].strip()
        return _COUNTER_SEPARATOR.fullmatch(separator) is not None
    # Without a total, two ordinary words and a number can be a complete statement.
    return label_words < 2 or any(word in _NUMBER_MARKERS for word in before[-1:] + after[:1])


def _body_word_count(text: str) -> int:
    return sum(len(_WORD.findall(line)) for line in text.splitlines() if not _is_page_counter(line))


def _has_visible_marks(page) -> bool:
    darkest, lightest = page.to_image(resolution=72).original.convert("L").getextrema()
    return darkest < 250 or darkest != lightest


def _has_content(text: str) -> bool:
    # A page counter has digits and at most a label and a short connecting word.
    # Ignore the punctuation, layout and language of that counter.
    for line in text.splitlines():
        words = re.findall(r"[^\W\d_]+", line)
        if words and (not re.search(r"\d", line) or len(words) > 2 or (len(words) == 2 and len(words[1]) > 2)):
            return True
    return False


def _needs_ocr(page, text: str) -> bool:
    if not _has_content(text):
        return True
    if not all(_is_page_counter(line) for line in text.splitlines() if line.strip()):
        return False
    # A selectable footer can sit below a scanned body with generous margins.
    visible_page = get_bbox_overlap(page.bbox, page.cropbox)
    if visible_page:
        for image in page.images:
            overlap = get_bbox_overlap(visible_page, obj_to_bbox(image))
            if overlap:
                left, top, right, bottom = overlap
                width, height = right - left, bottom - top
                if min(width, height) > 0 and max(width, height) > 36:  # Exclude half-inch decorative marks.
                    return True
    return False


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


@cache
def _rapid_engine():
    try:
        import onnxruntime  # noqa: F401 -- RapidOCR loads the selected runtime lazily.
        from rapidocr import RapidOCR
    except ImportError as error:
        raise RuntimeError("RapidOCR needs the rapidocr and onnxruntime packages (see README)") from error
    return RapidOCR(
        params={
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.log_level": "warning",
        }
    )


def _ocr(page, words: list[WordBox] | None, *, engine: str | None = None) -> str:
    if engine is None:
        engine = os.environ.get("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    if engine in TESSERACT_ENGINES:
        return _tesseract(page, words, explicit_dpi=engine != "tesseract")
    if engine != "rapidocr":
        raise ValueError(f"Unknown KIO_OCR_ENGINE={engine!r}, expected tesseract, tesseract-dpi, rapidocr or hybrid")
    from .rapid_worker import recognize

    text, boxes = recognize(page.pdf.path, page.page_number, words is not None, OCR_TIMEOUT_SECONDS)
    if words is not None:
        words.extend(WordBox(*box) for box in boxes)
    return text


def _rapidocr(page, words: list[WordBox] | None) -> str:
    """Run inside the deadline-controlled worker, which owns the mutable ONNX engine."""
    image = page.to_image(resolution=OCR_DPI)
    result = _rapid_engine()(image.original, return_word_box=words is not None)
    if words is not None and result.txts:
        left, top = image.bbox[:2]
        for line in result.word_results or ():
            for word, _, box in line or ():
                xs, ys = zip(*box)
                words.append(
                    WordBox(
                        page.page_number,
                        word,
                        left + float(min(xs)) / image.scale,
                        top + float(min(ys)) / image.scale,
                        left + float(max(xs)) / image.scale,
                        top + float(max(ys)) / image.scale,
                    )
                )
    return "\n".join(result.txts or ())


def _tesseract(page, words: list[WordBox] | None, *, explicit_dpi: bool) -> str:
    """Recognize the page and verify suspect e-mail separators against their image crops."""
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

    image = page.to_image(resolution=OCR_DPI)
    with ExitStack() as stack:
        api = stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.AUTO))
        api.SetImage(image.original)
        if explicit_dpi:
            api.SetSourceResolution(OCR_DPI)
        if not api.Recognize(timeout=1000 * OCR_TIMEOUT_SECONDS):
            raise OCRRecognitionError("Polish OCR failed or timed out")
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
                if explicit_dpi:
                    english.SetSourceResolution(OCR_DPI)
                if english.Recognize(timeout=1000):
                    replacement = confirmed_email(token, english.GetUTF8Text().strip())
                    text = text[:start] + replacement + text[cursor:]
                    cursor = start + len(replacement)
    return "\n".join(line for line in text.splitlines() if line.strip())


def read_pages(
    pdf_path: Path,
    max_pages: int = MAX_PAGES,
    force_ocr: bool = False,
    *,
    word_boxes: list[WordBox] | None = None,
    engine: str | None = None,
    ocr_pages: list[int] | None = None,
    ocr_word_boxes: list[WordBox] | None = None,
) -> list[str]:
    """Return the first pages and their optional boxes/OCR provenance. Check readability document-wide."""
    pages = []
    words = [] if word_boxes is not None else None
    used_ocr = False
    readable = False
    word_count = 0
    recognize = _ocr if engine is None else partial(_ocr, engine=engine)
    with pdfplumber.open(pdf_path) as pdf:
        limit = len(pdf.pages[:max_pages])
        for index, page in enumerate(pdf.pages):
            include = index < limit
            if not include and (not used_ocr or readable):
                break
            text = "" if force_ocr else page.extract_text() or ""
            scanned = _needs_ocr(page, text)
            if scanned:
                used_ocr = True
                if include and ocr_pages is not None:
                    ocr_pages.append(page.page_number)
                scan_words = words if words is not None else ocr_word_boxes
                text = normalize_ocr(recognize(page, scan_words if include else None))
                if include and words is not None and ocr_word_boxes is not None:
                    ocr_word_boxes.extend(box for box in words if box.page == page.page_number)
            elif include and words is not None:
                words.extend(
                    WordBox(page.page_number, w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                    for w in page.extract_words()
                )
            if include:
                pages.append(text)
            if not readable:
                page_words = _body_word_count(text)
                word_count += page_words
                readable = word_count >= MIN_OCR_WORDS or (not scanned and page_words > 0)
        if used_ocr and not readable and any(_has_visible_marks(page) for page in pdf.pages):
            raise NoReadableTextError("no readable text after OCR")
    if word_boxes is not None and words:
        word_boxes.extend(words)
    return pages


def iter_page_lines(pages: list[str]) -> Iterator[tuple[int, str]]:
    """Yield each retained line with its original 1-based page number."""
    first_lines = [page.split("\n", 1)[0] for page in pages]
    for page_number, page in enumerate(pages, start=1):
        lines = page.split("\n")
        if page_number > 1 and first_lines.count(lines[0]) > 1:
            lines = lines[1:]
        for line in lines:
            if not re.fullmatch(r"\s*Strona \d+ z \d+\s*", line):
                yield page_number, line


def join_pages(pages: list[str]) -> str:
    """Join pages into one text without 'Strona 1 z 11' footers and running headers."""
    return "\n".join(line for _, line in iter_page_lines(pages))
