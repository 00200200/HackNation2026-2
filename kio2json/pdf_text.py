"""Page text: the PDF text layer, with selectable local OCR for pages that have none."""

import os
import re
from contextlib import ExitStack
from functools import cache, partial
from importlib.metadata import files
from pathlib import Path
from typing import NamedTuple

import pdfplumber

from .ocr_normalize import MAIL_TOKEN_RE, confirmed_email, normalize_ocr

# The organizer README says the key information sits on the first three pages.
MAX_PAGES = 3
OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 60
DEFAULT_OCR_ENGINE = "tesseract-dpi"


class NoReadableTextError(RuntimeError):
    """Required OCR finished without finding any document text."""


class OCRRecognitionError(RuntimeError):
    """The OCR engine failed or timed out while recognizing a page."""


_PAGE_COUNTER = re.compile(
    # A printed label identifies a page number. Bare long digit strings can be the document's only content.
    r"\W*(?:(?:strona|str\.?|page|p\.?|arkusz)\W*\d+(?:\s*(?:/|of|z)\s*\d+)?"
    r"|\d{1,3}(?:\s*(?:/|of|z)\s*\d{1,3})?)\W*",
    re.IGNORECASE,
)


def _readable(text: str) -> bool:
    return any(any(c.isalnum() for c in line) and not _PAGE_COUNTER.fullmatch(line) for line in text.splitlines())


def _has_content(text: str) -> bool:
    # A page counter has digits and at most a label and a short connecting word.
    # Ignore the punctuation, layout and language of that counter.
    for line in text.splitlines():
        words = re.findall(r"[^\W\d_]+", line)
        if words and (not re.search(r"\d", line) or len(words) > 2 or (len(words) == 2 and len(words[1]) > 2)):
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
    if engine in {"tesseract", "tesseract-dpi", "hybrid"}:
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
) -> list[str]:
    """Read text, optionally collecting raw word boxes and the page numbers sent to OCR."""
    pages = []
    words = [] if word_boxes is not None else None
    used_ocr = False
    recognize = _ocr if engine is None else partial(_ocr, engine=engine)
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            text = "" if force_ocr else page.extract_text() or ""
            if not _has_content(text):
                used_ocr = True
                if ocr_pages is not None:
                    ocr_pages.append(page.page_number)
                text = normalize_ocr(recognize(page, words))
            elif words is not None:
                words.extend(
                    WordBox(page.page_number, w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
                    for w in page.extract_words()
                )
            pages.append(text)
    if used_ocr and not any(_readable(text) for text in pages):
        raise NoReadableTextError("no readable text after OCR")
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
