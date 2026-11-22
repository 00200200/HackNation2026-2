"""Serialize regional API requests and cap model time across all workers in a jury batch."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from multiprocessing import get_context
from time import monotonic, sleep

from .endpoint_error import EndpointError

CALL_SECONDS = 10
# Even an entirely unresponsive provider can use at most five minutes for 150 PDFs.
SECONDS_PER_PDF = 2


class JuryBudget:
    def __init__(self, documents: int):
        ctx = get_context("spawn")
        self.slot = ctx.Lock()
        self.seconds = ctx.Value("d", max(CALL_SECONDS, min(300, documents * SECONDS_PER_PDF)), lock=False)
        self.next_start = ctx.Value("d", 0, lock=False)
        self.resume = ctx.Value("d", 0, lock=False)


_batch: JuryBudget | None = None
_active: ContextVar[JuryBudget | None] = ContextVar("jury_budget", default=None)


def use_batch(budget: JuryBudget | None):
    global _batch
    _batch = budget


@contextmanager
def jury_document(budget: JuryBudget | None = None):
    token = _active.set(budget or _active.get() or _batch or JuryBudget(1))
    try:
        yield
    finally:
        _active.reset(token)


@contextmanager
def request_slot():
    budget = _active.get()
    if budget is None:
        yield None
        return
    # A crashed lock holder must not stall each remaining PDF.
    if budget.seconds.value < 0.1 or monotonic() < budget.resume.value:
        raise EndpointError(TimeoutError())
    if not budget.slot.acquire(timeout=CALL_SECONDS + 1):
        budget.resume.value = monotonic() + 60
        raise EndpointError(TimeoutError())
    try:
        start = monotonic()
        allowed = min(CALL_SECONDS, budget.seconds.value)
        if start < budget.resume.value or allowed < 0.1:
            raise EndpointError(TimeoutError())
        try:
            delay = max(0.0, budget.next_start.value - start)
            if allowed - delay < 0.1:
                raise EndpointError(TimeoutError())
            if delay:
                sleep(delay)
            budget.next_start.value = monotonic() + 1
            yield allowed - delay
        except EndpointError as error:
            logging.getLogger(__name__).warning("Model request status %s", error.status or "unavailable")
            if error.status in (401, 403):
                budget.seconds.value = 0
            elif error.status == 429:
                budget.resume.value = monotonic() + 60
            else:
                budget.resume.value = monotonic() + 10
            raise
        finally:
            budget.seconds.value = max(0, budget.seconds.value - (monotonic() - start))
    finally:
        budget.slot.release()
