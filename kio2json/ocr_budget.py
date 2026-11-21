"""One monotonic deadline for optional OCR work across a document and its recovery."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

REREAD_DEADLINE_SECONDS = 27
_deadline: ContextVar[float | None] = ContextVar("ocr_reread_deadline", default=None)


class RereadExpired(Exception):
    """Keep the primary reading when an optional pass runs out of time."""


@contextmanager
def document_budget():
    token = _deadline.set(monotonic() + REREAD_DEADLINE_SECONDS)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_ms(limit: int) -> int:
    deadline = _deadline.get()
    if deadline is None:
        return limit
    return max(0, min(limit, int((deadline - monotonic()) * 1000)))
