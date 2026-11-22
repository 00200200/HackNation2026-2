"""Per-document output and diagnostics shared by the CLI and GUI."""

import json
import logging
import os
import sys
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from contextlib import ExitStack, nullcontext, redirect_stderr
from dataclasses import dataclass, replace
from io import StringIO
from multiprocessing import get_context
from pathlib import Path

from .case_repair import Reading, case_repair_enabled, repairs
from .class_config import ClassSources, DocumentClass, parse_classes
from .endpoint_error import EndpointError
from .ocr_budget import batch_deadline
from .pdf_text import NoReadableTextError
from .pipeline import process_pdf, uses_case_schema
from .trace import build, recording, repaired


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
    text: str = "{}\n"
    error: str | None = None
    used_recovery: bool = False
    readings: tuple[Reading, ...] = ()
    custom_schema: bool = False
    trace: dict | None = None


def read_document(
    path: Path, classes: list[DocumentClass], *, batch_deadline: float | None = None, explain: bool = False
) -> Result:
    recoveries = []
    readings = [] if case_repair_enabled() else None
    try:
        with recording() if explain else nullcontext() as events:
            label, data = process_pdf(
                path,
                classes=classes,
                on_recovery=recoveries.append,
                batch_deadline=batch_deadline,
                case_readings=readings,
            )
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        custom = any(c.id == label and not uses_case_schema(c) for c in classes)
        return Result(
            label,
            text,
            used_recovery=bool(recoveries),
            readings=tuple(readings or ()),
            custom_schema=custom,
            trace=explained(label, data, events) if explain else None,
        )
    except (EndpointError, NoReadableTextError) as error:
        return Result(None, error=str(error))
    except Exception as error:  # noqa: BLE001 - PDF and OCR backends raise unrelated types.
        return Result(None, error=f"{type(error).__name__}: {error}")


def reconcile_cases(names: list[Path], results: list[Result]) -> list[Result]:
    """Use original readings only. Keep output order, diagnostics and unrelated bytes intact."""
    if not any(result.readings for result in results):
        return results
    grouped = defaultdict(list)
    for index, (name, result) in enumerate(zip(names, results, strict=True)):
        if name.parent != Path(".") and not result.error and (result.readings or result.label == "appeal"):
            grouped[name.parent].append(index)
    output = results.copy()
    for indices in grouped.values():
        if sum(results[i].label == "appeal" for i in indices) > 1:
            continue  # No document link distinguishes separate appeals within a folder.
        for i in indices:
            result = results[i]
            siblings = [reading for j in indices if results[j].label != result.label for reading in results[j].readings]
            changes = list(repairs(result.readings, siblings))
            if not changes:
                continue
            data = json.loads(result.text)
            # Edit title spans from right to left to preserve their original offsets.
            for reading, value in sorted(changes, key=lambda change: change[0].span or (0, 0), reverse=True):
                node = data
                for key in reading.path[:-1]:
                    node = node[key]
                field = reading.path[-1]
                if reading.span:
                    start, end = reading.span
                    value = node[field][:start] + value + node[field][end:]
                node[field] = value
            trace = repaired(result.trace, data) if result.trace else None
            output[i] = replace(result, text=json.dumps(data, ensure_ascii=False, indent=2) + "\n", trace=trace)
    return output


def explained(label: str | None, data: dict, events: dict) -> dict:
    """Build the evidence trace. A failure here must not cost the document its JSON."""
    try:
        return build(label, data, events)
    except Exception as error:  # noqa: BLE001 - the trace only reads values the extraction already produced
        empty = {"class": label, "routing": None, "pages": None, "fields": [], "warnings": events["warnings"]}
        expired = {"optional_ocr_expired": True} if events.get("optional_ocr_expired") else {}
        return empty | expired | {"trace_error": f"{type(error).__name__}: {error}"}


_worker_classes: list[DocumentClass]


def _init_worker(sources: ClassSources) -> None:
    global _worker_classes
    _worker_classes = parse_classes(sources)
    configure_logging(_worker_classes)


def _read_in_worker(path: Path, deadline: float, explain: bool = False) -> tuple[Result, str]:
    with redirect_stderr(StringIO()) as diagnostics:
        try:
            result = read_document(path, _worker_classes, batch_deadline=deadline, explain=explain)
        except SystemExit as error:
            result = Result(None, error=f"PDF worker requested exit ({error.code})")
    return result, diagnostics.getvalue()


def read_batch(pdfs: list[Path], sources: ClassSources, workers: int, *, explain: bool = False) -> Iterator[Result]:
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
            pending[pool.submit(_read_in_worker, path, deadline, explain)] = (pool, index)

        for _ in range(min(workers, len(pdfs))):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pool, index = pending.pop(future)
                try:
                    ready[index] = future.result()
                except BrokenProcessPool:
                    ready[index] = (Result(None, error="PDF worker exited unexpectedly"), "")
                    pool.shutdown()
                    pool = None
                submit_next(pool)
            while next_output in ready:
                result, diagnostics = ready.pop(next_output)
                sys.stderr.write(diagnostics)
                next_output += 1
                yield result
