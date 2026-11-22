"""Per-document output and diagnostics shared by the CLI and GUI."""

import json
import logging
import os
import sys
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from contextlib import ExitStack, redirect_stderr
from dataclasses import dataclass
from io import StringIO
from multiprocessing import get_context
from pathlib import Path

from .class_config import DocumentClass, parse_classes
from .endpoint_error import EndpointError
from .ocr_budget import batch_deadline
from .pdf_text import NoReadableTextError
from .pipeline import process_pdf


def configure_logging(classes: list[DocumentClass]) -> None:
    if any(c.enabled and ("llm" in c.engines or c.profile.routing != "rules") for c in classes):
        # The SDK banner names the model; debug logs include response headers and request URLs.
        os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
        os.environ.pop("OPENAI_LOG", None)
        for name in ("openai", "httpx2", "httpcore2"):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)


@dataclass(frozen=True)
class Result:
    label: str | None
    text: str
    error: str | None = None
    used_recovery: bool = False


def read_document(path: Path, classes: list[DocumentClass], *, batch_deadline: float | None = None) -> Result:
    recoveries = []
    try:
        label, data = process_pdf(path, classes=classes, on_recovery=recoveries.append, batch_deadline=batch_deadline)
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n" if data else ""
        return Result(label, text, used_recovery=bool(recoveries))
    except (EndpointError, NoReadableTextError) as error:
        return Result(None, "", str(error))
    except Exception as error:  # noqa: BLE001 - PDF and OCR backends raise unrelated types.
        return Result(None, "", f"{type(error).__name__}: {error}")


_worker_classes: list[DocumentClass]


def _init_worker(sources: dict[Path, bytes]) -> None:
    global _worker_classes
    _worker_classes = parse_classes(sources)
    configure_logging(_worker_classes)


def _read_in_worker(path: Path, deadline: float) -> tuple[Result, str]:
    with redirect_stderr(StringIO()) as diagnostics:
        try:
            result = read_document(path, _worker_classes, batch_deadline=deadline)
        except SystemExit as error:
            result = Result(None, "", f"PDF worker requested exit ({error.code})")
    return result, diagnostics.getvalue()


def read_batch(pdfs: list[Path], sources: dict[Path, bytes], workers: int) -> Iterator[Result]:
    """Yield in input order so the parent owns all writes, including colliding stems."""
    os.environ["OMP_THREAD_LIMIT"] = "1"
    deadline = batch_deadline(len(pdfs))
    inputs = iter(enumerate(pdfs))
    pending = {}
    ready = {}
    next_output = 0
    with ExitStack() as stack:

        def submit_next(pool=None):
            item = next(inputs, None)
            if item is None:
                return
            index, path = item
            if pool is None:
                # One outstanding PDF per interpreter. A native crash has exactly one owner.
                pool = stack.enter_context(
                    ProcessPoolExecutor(
                        1, mp_context=get_context("spawn"), initializer=_init_worker, initargs=(sources,)
                    )
                )
            pending[pool.submit(_read_in_worker, path, deadline)] = (pool, index)

        for _ in range(min(workers, len(pdfs))):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pool, index = pending.pop(future)
                try:
                    ready[index] = future.result()
                except BrokenProcessPool:
                    ready[index] = (Result(None, "", "PDF worker exited unexpectedly"), "")
                    pool.shutdown()
                    pool = None
                submit_next(pool)
            while next_output in ready:
                result, diagnostics = ready.pop(next_output)
                sys.stderr.write(diagnostics)
                next_output += 1
                yield result
