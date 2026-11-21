"""Content-based routing. The file name is never an input."""

import re

from .bank_transfer import ACCOUNT_RE

JUDGMENT_RE = re.compile(r"Sygn\.\s*akt|\bWYROK\b|\bPOSTANOWIENIE\b|W IMIENIU RZECZYPOSPOLITEJ")


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
    if len(accounts) >= 2 and re.search(r"przelew", pages[0], re.IGNORECASE):
        return "bank_transfer"
    return None
