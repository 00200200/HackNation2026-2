"""Page text: the PDF text layer, with selectable local OCR for pages that have none."""

import hashlib
import os
import re
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
from contextvars import copy_context
from functools import cache, partial
from math import ceil
from pathlib import Path
from time import monotonic
from typing import NamedTuple

import pdfplumber
from pdfplumber.utils import get_bbox_overlap, obj_to_bbox
from PIL import Image

from .case_repair import case_repair_enabled
from .ocr_budget import CROP_TIMEOUT_MS, REREAD_PAGE_TIMEOUT_SECONDS, RereadExpired, remaining_ms, require_remaining_ms
from .ocr_normalize import MAIL_TOKEN_RE, confirmed_email, normalize_ocr

# The organizer README says the key information sits on the first three pages.
MAX_PAGES = 3
OCR_DPI = 300
# Three A4 pages at 300 DPI fit within this limit (about 105 MiB of RGB pixels in Pillow).
MAX_PARALLEL_PIXELS = 28_000_000
OCR_TIMEOUT_SECONDS = 180
PRIMARY_RETRY_TIMEOUT_SECONDS = 60
RETRY_DPI = OCR_DPI // 2
DEFAULT_OCR_ENGINE = "tesseract-dpi"
TESSERACT_ENGINES = frozenset({"tesseract", "tesseract-dpi", "hybrid"})
OCR_ENGINES = TESSERACT_ENGINES | {"rapidocr"}


class NoReadableTextError(RuntimeError):
    """Required OCR finished without finding any document text."""


class OCRRecognitionError(RuntimeError):
    """The OCR engine failed or timed out while recognizing a page."""


class _PrimaryPageTimeout(OCRRecognitionError):
    """A required Tesseract pass exhausted its native watchdog."""


def _primary_retry_ms() -> int:
    return remaining_ms(int(1000 * min(PRIMARY_RETRY_TIMEOUT_SECONDS, OCR_TIMEOUT_SECONDS)))


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


def _has_visible_marks(page, *, reread: bool = False) -> bool:
    if reread:
        require_remaining_ms()
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


def damaged_text_layer(text: str) -> bool:
    # Digits repeatedly substituted inside distinct words are characteristic of a bad OCR layer.
    return len(set(re.findall(r"\b[^\W\d_]{2,}\d[^\W\d_]+\b", text.casefold()))) >= 3


def _page_sized_image(page) -> bool:
    visible = get_bbox_overlap(page.bbox, page.cropbox)
    if visible:
        for image in page.images:
            region = get_bbox_overlap(visible, obj_to_bbox(image))
            if region and all(region[i + 2] - region[i] >= 0.75 * (visible[i + 2] - visible[i]) for i in (0, 1)):
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


class OCRWord(WordBox):
    """A Tesseract reading with the same six positional fields used by the layout readers."""

    def __new__(cls, page, text, x0, y0, x1, y1, confidence=None):
        word = super().__new__(cls, page, text, x0, y0, x1, y1)
        word.confidence = confidence
        return word


# Tesseract fast models (Apache-2.0, see tessdata/LICENSE), vendored so pip needs no second host.
TESSDATA_DIR = Path(__file__).with_name("tessdata")
TESSDATA_UPSTREAM = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd"
)
TESSDATA_SHA256 = {
    "pol.traineddata": "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2",
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}


@cache
def _language_dir() -> str:
    for name, expected in TESSDATA_SHA256.items():
        path = TESSDATA_DIR / name
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise FileNotFoundError(f"OCR language data missing: {path} ({TESSDATA_UPSTREAM}/{name})") from error
        if digest != expected:
            raise RuntimeError(f"{path} has SHA-256 {digest}, expected {expected} ({TESSDATA_UPSTREAM}/{name})")
    return str(TESSDATA_DIR)


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


def _ocr(page, words: list[WordBox] | None, *, engine: str | None = None, reread: bool = False) -> str:
    if engine is None:
        engine = os.environ.get("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
    if engine in TESSERACT_ENGINES:
        if reread:
            require_remaining_ms()
        return _tesseract(_render(page), words, explicit_dpi=engine != "tesseract", reread=reread)
    if engine != "rapidocr":
        raise ValueError(f"Unknown KIO_OCR_ENGINE={engine!r}, expected tesseract, tesseract-dpi, rapidocr or hybrid")
    from .rapid_worker import recognize

    timeout = require_remaining_ms(1000 * REREAD_PAGE_TIMEOUT_SECONDS) / 1000 if reread else OCR_TIMEOUT_SECONDS
    try:
        text, boxes = recognize(page.pdf.path, page.page_number, words is not None, timeout)
    except TimeoutError as error:
        if reread:
            raise RereadExpired from error
        retry_ms = _primary_retry_ms()
        if not retry_ms:
            raise
        text, boxes = recognize(page.pdf.path, page.page_number, words is not None, retry_ms / 1000, dpi=RETRY_DPI)
    if words is not None:
        words.extend(WordBox(*box) for box in boxes)
    return text


def _rapidocr(page, words: list[WordBox] | None, *, lines: bool = False, dpi: int | None = None) -> str:
    """Run inside the deadline-controlled worker, which owns the mutable ONNX engine."""
    image = page.to_image(resolution=OCR_DPI if dpi is None else dpi)
    result = _rapid_engine()(image.original, return_word_box=words is not None and not lines)
    if words is not None and result.txts:
        left, top = image.bbox[:2]
        if lines:
            groups = [zip(result.txts, result.scores, result.boxes, strict=True)]
        else:
            groups = result.word_results or ()
        for line in groups:
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


class _Raster(NamedTuple):
    original: Image.Image
    bbox: tuple[float, ...]
    scale: float
    page_number: int


def _render(page) -> _Raster:
    image = page.to_image(resolution=OCR_DPI)
    return _Raster(image.original, image.bbox, image.scale, page.page_number)


def _tesseract(image: _Raster, words: list[WordBox] | None, *, explicit_dpi: bool, reread: bool = False) -> str:
    try:
        return _recognize_raster(image, words, explicit_dpi=explicit_dpi, dpi=OCR_DPI, reread=reread)
    except _PrimaryPageTimeout:
        if not _primary_retry_ms():
            raise
        # Resize the existing raster: parallel workers must never render PDFium pages.
        with image.original.reduce(2) as reduced:
            retry = image._replace(original=reduced, scale=image.scale / 2)
            return _recognize_raster(retry, words, explicit_dpi=explicit_dpi, dpi=RETRY_DPI, reread=False)


def _recognize_raster(
    image: _Raster, words: list[WordBox] | None, *, explicit_dpi: bool, dpi: int, reread: bool
) -> str:
    """Recognize the page and verify suspect e-mail separators against their image crops."""
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

    if reread:
        require_remaining_ms()
    with ExitStack() as stack:
        api = stack.enter_context(PyTessBaseAPI(path=_language_dir(), lang="pol", psm=PSM.AUTO))
        api.SetImage(image.original)
        if explicit_dpi:
            api.SetSourceResolution(dpi)
        timeout = require_remaining_ms(1000 * REREAD_PAGE_TIMEOUT_SECONDS) if reread else 1000 * OCR_TIMEOUT_SECONDS
        if dpi == RETRY_DPI:
            timeout = _primary_retry_ms()
            if not timeout:
                raise _PrimaryPageTimeout("Polish OCR timed out before the lower-resolution retry")
        recognition_deadline = monotonic() + timeout / 1000
        if not api.Recognize(timeout=timeout):
            if reread and (not remaining_ms(1) or monotonic() >= recognition_deadline):
                raise RereadExpired
            if not reread and monotonic() >= recognition_deadline:
                raise _PrimaryPageTimeout("Polish OCR timed out")
            raise OCRRecognitionError("Polish OCR failed or timed out")
        text = api.GetUTF8Text()
        iterator = api.GetIterator() if text.strip() else None
        english = None
        cursor = 0
        if iterator is not None:
            left, top = image.bbox[:2]
            keep_confidence = case_repair_enabled()
            for item in iterate_level(iterator, RIL.WORD):
                box = item.BoundingBox(RIL.WORD)
                if not box:
                    continue
                token = item.GetUTF8Text(RIL.WORD)
                x0, y0, x1, y1 = box
                if words is not None:
                    word = WordBox(
                        image.page_number,
                        token,
                        left + x0 / image.scale,
                        top + y0 / image.scale,
                        left + x1 / image.scale,
                        top + y1 / image.scale,
                    )
                    if keep_confidence:
                        word = OCRWord(*word, confidence=item.Confidence(RIL.WORD))
                    words.append(word)
                start = text.find(token, cursor)
                if start < 0:
                    continue
                cursor = start + len(token)
                if not MAIL_TOKEN_RE.fullmatch(token) or not remaining_ms(1):
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
                    english.SetSourceResolution(dpi)
                timeout = remaining_ms(CROP_TIMEOUT_MS)
                if timeout and english.Recognize(timeout=timeout):
                    replacement = confirmed_email(token, english.GetUTF8Text().strip())
                    text = text[:start] + replacement + text[cursor:]
                    cursor = start + len(replacement)
    return "\n".join(line for line in text.splitlines() if line.strip())


def _text_layer(page, force_ocr: bool, repair_image_text: bool) -> str | None:
    text = "" if force_ocr else page.extract_text() or ""
    if _needs_ocr(page, text) or (repair_image_text and damaged_text_layer(text) and _page_sized_image(page)):
        return None
    return text


def _fits_parallel_batch(pages) -> bool:
    pixels = 0
    for page in pages:
        # PDFium initially renders the full page, before pdfplumber applies any crop.
        x0, y0, x1, y1 = page.mediabox
        if page.page_obj.attrs.get("UserUnit", 1) != 1:
            return False
        pixels += ceil((x1 - x0) * OCR_DPI / 72) * ceil((y1 - y0) * OCR_DPI / 72)
    return pixels <= MAX_PARALLEL_PIXELS


def _recognize_batch(scans, *, explicit_dpi: bool, with_boxes: bool):
    """Render on the caller's thread. Each Tesseract instance owns one raster and its word list."""
    jobs = {}
    with ThreadPoolExecutor(max_workers=len(scans)) as pool:
        for page in scans:
            boxes = [] if with_boxes else None
            try:
                raster = _render(page)
            except Exception as error:  # noqa: BLE001 -- deliver backend failures in page order.
                failed = Future()
                failed.set_exception(error)
                jobs[page.page_number] = failed, boxes
                break
            # Full-page primary OCR owns its timeout, but its e-mail crops share the document deadline.
            job = pool.submit(copy_context().run, _tesseract, raster, boxes, explicit_dpi=explicit_dpi)
            jobs[page.page_number] = job, boxes
    return jobs


def read_pages(
    pdf_path: Path,
    max_pages: int = MAX_PAGES,
    force_ocr: bool = False,
    *,
    word_boxes: list[WordBox] | None = None,
    first_ocr_words: list[WordBox] | None = None,
    page_sizes: dict[int, tuple[float, float]] | None = None,
    repair_image_text: bool = False,
    engine: str | None = None,
    ocr_pages: list[int] | None = None,
    ocr_word_boxes: list[WordBox] | None = None,
    reread: bool = False,
) -> list[str]:
    """Return the first pages and their optional boxes/OCR provenance. Check readability document-wide."""
    pages = []
    words = [] if any(out is not None for out in (word_boxes, ocr_word_boxes, first_ocr_words)) else None
    scanned_numbers = set()
    used_ocr = False
    readable = False
    word_count = 0
    recognize = _ocr if engine is None else partial(_ocr, engine=engine)
    if reread:
        require_remaining_ms()
        recognize = partial(recognize, reread=True)
    with pdfplumber.open(pdf_path) as pdf:
        retained = pdf.pages[:max_pages]
        limit = len(retained)
        layers = {}
        jobs = {}
        selected = engine if engine is not None else os.environ.get("KIO_OCR_ENGINE", DEFAULT_OCR_ENGINE)
        if not reread and selected in TESSERACT_ENGINES and 2 <= limit <= 3:
            for page in retained:
                try:
                    layers[page.page_number] = _text_layer(page, force_ocr, repair_image_text)
                except Exception as error:  # noqa: BLE001 -- earlier pages must finish before this error is raised.
                    layers[page.page_number] = error
                    break
            scans = [page for page in retained if page.page_number in layers and layers[page.page_number] is None]
            if len(scans) >= 2 and _fits_parallel_batch(scans):
                jobs = _recognize_batch(scans, explicit_dpi=selected != "tesseract", with_boxes=words is not None)
        for index, page in enumerate(pdf.pages):
            include = index < limit
            if not include and (not used_ocr or readable):
                break
            if reread:
                require_remaining_ms()
            number = page.page_number
            text = layers[number] if number in layers else _text_layer(page, force_ocr, repair_image_text)
            if isinstance(text, Exception):
                raise text
            scanned = text is None
            if scanned:
                used_ocr = True
                if include:
                    scanned_numbers.add(number)
                    if ocr_pages is not None:
                        ocr_pages.append(number)
                if number in jobs:
                    future, page_boxes = jobs[number]
                    text = future.result()
                    if page_boxes:
                        words.extend(page_boxes)
                else:
                    text = recognize(page, words if include else None)
                text = normalize_ocr(text)
            elif include and word_boxes is not None:
                words.extend(
                    WordBox(page.page_number, w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                    for w in page.extract_words()
                )
            if include:
                if page_sizes is not None:
                    page_sizes[number] = page.width, page.height
                pages.append(text)
            if not readable:
                page_words = _body_word_count(text)
                word_count += page_words
                readable = word_count >= MIN_OCR_WORDS or (not scanned and page_words > 0)
        if used_ocr and not readable and any(_has_visible_marks(page, reread=reread) for page in pdf.pages):
            raise NoReadableTextError("no readable text after OCR")
    if word_boxes is not None and words:
        word_boxes.extend(words)
    if ocr_word_boxes is not None and ocr_word_boxes is not word_boxes and words:
        ocr_word_boxes.extend(box for box in words if box.page in scanned_numbers)
    if first_ocr_words is not None and first_ocr_words is not word_boxes and first_ocr_words is not ocr_word_boxes:
        first_ocr_words.extend(box for box in words if box.page == 1 and 1 in scanned_numbers)
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
