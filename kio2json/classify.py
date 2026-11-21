"""Content-based routing. The file name is never an input."""

import re

from .bank_transfer import ACCOUNT_RE

JUDGMENT_RE = re.compile(
    r"^\s*(?:WYROK|POSTANOWIENIE|W IMIENIU RZECZYPOSPOLITEJ POLSKIEJ)\s*$", re.IGNORECASE | re.MULTILINE
)
PAYMENT_REQUEST_RE = re.compile(
    r"^\s*(?:faktura(?: VAT)?|wezwanie do zapłaty|prośba o płatność)\b", re.IGNORECASE | re.MULTILINE
)
CONFIRMATION_RE = re.compile(
    r"\b(?:potwierdzenie|dowód)\s+(?:(?:wykonania|realizacji)\s+)?(?:polecenia\s+)?"
    r"(?:przelewu|transakcji|operacji bankowej)\b|\bwykonano przelew\b|^\s*(?:status[\s.:]*)?(?:przelew\s+)?zrealizowan[yo]\b",
    re.IGNORECASE | re.MULTILINE,
)


def _headings(text: str) -> list[str]:
    """Lines with whitespace removed, so 'O D W O Ł A N I E' reads as 'ODWOŁANIE'."""
    return [re.sub(r"\s", "", line).upper() for line in text.splitlines()]


def classify(pages: list[str]) -> str | None:
    """Return 'appeal', 'power_of_attorney', 'bank_transfer', or None for any other document."""
    if not pages:
        return None
    head = "\n".join(pages[:2])
    first_page_headings = _headings(pages[0])

    if "ODWOŁANIE" in _headings(head) and "odwołując" in head.lower() and not JUDGMENT_RE.search(head):
        return "appeal"
    if any(h.startswith("PEŁNOMOCNICTWO") and len(h) <= 30 for h in first_page_headings):
        return "power_of_attorney"
    accounts = {re.sub(r"\s", "", m.group(1)) for m in ACCOUNT_RE.finditer(pages[0])}
    if (
        len(accounts) >= 2
        and "przelew" in pages[0].lower()
        and CONFIRMATION_RE.search(pages[0])
        and not PAYMENT_REQUEST_RE.search(pages[0])
    ):
        return "bank_transfer"
    return None
