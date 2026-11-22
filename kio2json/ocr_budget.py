"""Monotonic wall-clock limits for optional OCR, shared by every reread and recovery."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

REREAD_DEADLINE_SECONDS = 300
REREAD_PAGE_TIMEOUT_SECONDS = 180
CROP_TIMEOUT_MS = 10_000
JURY_SECONDS_PER_PDF = 45 * 60 / 150
OPTIONAL_BATCH_FRACTION = 0.60
_deadline: ContextVar[float | None] = ContextVar("ocr_reread_deadline", default=None)


class RereadExpired(Exception):
    """Keep the primary reading when an optional pass runs out of time."""


def batch_deadline(pdf_count: int) -> float:
    """Compute once before dispatch so all workers, including replacements, share one cutoff."""
    scaled_seconds = pdf_count * JURY_SECONDS_PER_PDF * OPTIONAL_BATCH_FRACTION
    # Even a one-file upload should have room for a slow scan.
    return monotonic() + max(REREAD_DEADLINE_SECONDS, scaled_seconds)


@contextmanager
def document_budget(batch_deadline: float | None = None):
    deadline = monotonic() + REREAD_DEADLINE_SECONDS
    token = _deadline.set(deadline if batch_deadline is None else min(deadline, batch_deadline))
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_ms(limit: int) -> int:
    deadline = _deadline.get()
    if deadline is None:
        return limit
    return max(0, min(limit, int((deadline - monotonic()) * 1000)))


def require_remaining_ms(limit: int = 1) -> int:
    timeout = remaining_ms(limit)
    if not timeout:
        raise RereadExpired
    return timeout
