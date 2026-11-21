"""Page text: the PDF text layer, with Polish Tesseract OCR for pages that have none."""

import re
from pathlib import Path

import pdfplumber
import pytesseract

# The organizer README says the key information sits on the first three pages.
MAX_PAGES = 3
OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 60


PAGE_NUMBER_RE = re.compile(
    r"\s*[-–—]?\s*(?:(?:strona|str\.|page)\s*)?\d+(?:\s*(?:z|/|of)\s*\d+)?\s*[-–—]?\s*", re.IGNORECASE
)


def _ocr(page) -> str:
    """OCR one page. Engine failures propagate to the batch error handler."""
    image = page.to_image(resolution=OCR_DPI).original
    text = pytesseract.image_to_string(image, lang="pol", timeout=OCR_TIMEOUT_SECONDS)
    # Tesseract separates paragraphs with blank lines; the text layer does not, and the rules expect that.
    return "\n".join(line for line in text.splitlines() if line.strip())


def read_pages(pdf_path: Path, max_pages: int = MAX_PAGES, force_ocr: bool = False) -> list[str]:
    """Text of the first pages. force_ocr ignores the text layer (used to measure OCR losses)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            text = "" if force_ocr else page.extract_text() or ""
            has_content = any(line.strip() and not PAGE_NUMBER_RE.fullmatch(line) for line in text.splitlines())
            pages.append(text if has_content else _ocr(page))
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
