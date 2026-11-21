"""Keep RapidOCR warm across pages and terminate native inference on its wall-clock deadline."""

import atexit
import json
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from threading import Lock, Timer
from time import monotonic
from typing import Literal

_process: subprocess.Popen | None = None
_lock = Lock()


def close() -> None:
    global _process
    if _process is not None:
        _process.kill()
        _process.wait()
        with suppress(BrokenPipeError):
            _process.stdin.close()
        _process.stdout.close()
        _process = None


atexit.register(close)


def recognize(path: Path, page: int, word_boxes: bool | Literal["lines"], timeout: float) -> tuple[str, list]:
    global _process
    deadline = monotonic() + timeout
    expired = TimeoutError(f"RapidOCR timed out after {timeout:g} seconds")
    if not _lock.acquire(timeout=timeout):
        raise expired
    try:
        if _process is not None and _process.poll() is not None:
            close()
        if _process is None:
            _process = subprocess.Popen(
                [sys.executable, "-m", "kio2json.rapid_worker"],
                cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="ascii",
            )
        # Killing the child releases a blocked pipe read or write, even when ONNX never returns.
        timer = Timer(max(0, deadline - monotonic()), _process.kill)
        timer.start()
        try:
            request = [str(path.resolve()), page, word_boxes]
            _process.stdin.write(json.dumps(request) + "\n")
            _process.stdin.flush()
            line = _process.stdout.readline()
        except OSError as error:
            if monotonic() >= deadline:
                raise expired from error
            raise
        finally:
            timer.cancel()
            timer.join()
        if monotonic() >= deadline:
            raise expired
        if not line:
            raise RuntimeError("RapidOCR worker exited before returning a result")
        text, boxes, error = json.loads(line)
        if error is not None:
            raise RuntimeError(error)
        return text, boxes
    except BaseException:
        # Also discard an interrupted exchange so the next caller cannot receive an old response.
        close()
        raise
    finally:
        _lock.release()


def _serve() -> None:
    # Reserve the original stdout for replies. Native libraries may print to fd 1 themselves.
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="ascii") as replies:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        import pdfplumber

        from .pdf_text import _rapidocr

        for request in sys.stdin:
            path, page, want_boxes = json.loads(request)
            boxes = [] if want_boxes else None
            try:
                with pdfplumber.open(path, pages=[page]) as pdf:
                    text = _rapidocr(pdf.pages[0], boxes, lines=want_boxes == "lines")
                result = [text, boxes or [], None]
            except Exception as error:  # noqa: BLE001 -- relay PDF and native model errors to the caller.
                result = [None, [], str(error) or type(error).__name__]
            print(json.dumps(result), file=replies, flush=True)


if __name__ == "__main__":
    _serve()
