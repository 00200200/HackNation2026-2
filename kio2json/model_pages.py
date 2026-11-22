"""Bounded model input from a primary transcript and independent OCR readings."""

from dataclasses import dataclass, field
from pathlib import Path

from .ocr_budget import REREAD_PAGE_TIMEOUT_SECONDS, remaining_ms

MODEL_INPUT_BYTES = 16384
_DIVIDER = "\n\n--- Alternate OCR of the scanned pages above ---\n\n"


def _clip(text: str, limit: int) -> str:
    return text.encode("utf-8")[: max(0, limit)].decode("utf-8", errors="ignore")


def model_readings(
    primary: str, alternate_pages: list[str] | None, limit: int = MODEL_INPUT_BYTES
) -> tuple[str, list[tuple[str, str]]]:
    """Return the prompt and each full source paired with the portion actually displayed."""
    pages = alternate_pages or []
    alternate = "\n".join(pages)
    available = limit - len(_DIVIDER.encode())
    if not alternate.strip() or available <= 0:
        excerpt = _clip(primary, limit)
        return excerpt, [(primary, excerpt)]
    # Split the byte budget equally and let either reading use space left by the other.
    primary_cap = max(available // 2, available - len(alternate.encode()))
    first = _clip(primary, primary_cap)
    second = _clip(alternate, available - len(first.encode()))
    sources = [(primary, first)]
    position = 0
    for page in pages:
        sources.append((page, second[position : position + len(page)]))
        position += len(page) + 1
    return first + _DIVIDER + second, sources


@dataclass
class AlternateOCR:
    """Read each requested scanned page at most once for this PDF."""

    path: Path
    scanned_pages: list[int]
    _text: dict[int, str] = field(default_factory=dict, init=False)

    def read(self, page: int) -> str:
        if page not in self.scanned_pages:
            return ""
        if page not in self._text:
            from .ocr_normalize import normalize_ocr
            from .rapid_worker import recognize

            timeout = remaining_ms(1000 * REREAD_PAGE_TIMEOUT_SECONDS) / 1000
            if not timeout:
                return ""
            try:
                text, _ = recognize(self.path, page, False, timeout)
            except TimeoutError:
                self._text[page] = ""
            else:
                self._text[page] = normalize_ocr(text)
        return self._text[page]

    def read_all(self) -> list[str]:
        return [self.read(page) for page in self.scanned_pages]
