"""HTTP API for the public page (doc2json.pl): the same per-document extraction as the CLI and GUI.

    GET  /api/health   -> {"status": "ok" | "busy"}
    POST /api/extract  multipart `files` (PDF) -> {"results": [{"index", "file", "class", "data", "error"}]}
    GET  /api/docs     -> OpenAPI docs

`index` follows the upload order, so two files with the same name stay apart. `class` is the class id from
`config/classes/*.toml` (null for a document outside every class, whose `data` is then `{}`).
Failed documents also return `data: {}` and include the diagnostic in `error`.
Run: `uvicorn kio2json.web_api:app --host 0.0.0.0 --port 8000`.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .batch import Result

MAX_FILES = int(os.environ.get("KIO_WEB_MAX_FILES", "10"))
MAX_FILE_MB = int(os.environ.get("KIO_WEB_MAX_FILE_MB", "20"))
DOC_TIMEOUT_S = int(os.environ.get("KIO_WEB_DOC_TIMEOUT_S", "90"))
REQUEST_BUDGET_S = int(os.environ.get("KIO_WEB_REQUEST_BUDGET_S", "500"))  # under the 600 s proxy and page limits
MAX_QUEUED_REQUESTS = int(os.environ.get("KIO_WEB_MAX_QUEUED", "4"))

_slot = asyncio.Semaphore(1)
_queued = 0

app = FastAPI(title="doc2json", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


class DocumentResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    file: str
    class_id: str | None = Field(None, alias="class")
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    results: list[DocumentResult]


class UploadParser(MultiPartParser):
    """Count file bytes in parser callbacks, before Starlette writes them to the spool."""

    complete = False

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self.file_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.file_bytes += end - start
            if self.file_bytes > MAX_FILE_MB * 1024 * 1024:
                raise HTTPException(413, f"Plik większy niż {MAX_FILE_MB} MB.")
        super().on_part_data(data, start, end)

    def on_end(self) -> None:
        self.complete = True

    async def parse(self) -> FormData:
        form = await super().parse()
        if not self.complete:
            # A truncated last part may have a spool which is not yet in FormData.
            for spool in self._files_to_close_on_error:
                spool.close()
            raise HTTPException(400, "Niepełne dane formularza.")
        return form


async def _uploads(request: Request, deadline: float) -> FormData:
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        raise HTTPException(422, "Wybierz pliki PDF.")
    # Reserve 1 MiB for form headers and boundaries, including on chunked requests.
    limit = (MAX_FILE_MB * MAX_FILES + 1) * 1024 * 1024
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdigit() or len(length) > 20:
            raise HTTPException(400, "Nieprawidłowa długość żądania.")
        if int(length) > limit:
            raise HTTPException(413, "Za duże żądanie.")

    async def stream():
        received = 0
        async for chunk in request.stream():
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError
            received += len(chunk)
            if received > limit:
                raise HTTPException(413, "Za duże żądanie.")
            yield chunk

    parser = UploadParser(request.headers, stream(), max_files=MAX_FILES, max_fields=0)
    try:
        return await parser.parse()
    except MultiPartException as exc:
        status = 413 if parser._current_files > MAX_FILES else 400
        raise HTTPException(status, exc.message) from exc


def _start_worker(pdf: Path, output: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "kio2json.web_worker", str(pdf), str(output)],
        start_new_session=os.name == "posix",
    )


def _stop_worker(process: subprocess.Popen) -> None:
    # RapidOCR may run a child of its own. Reap the whole job before admitting the next document.
    if os.name == "posix":
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        process.kill()
    process.wait()


async def _read(content: bytes, deadline: float) -> Result:
    async with _slot:
        async with asyncio.timeout_at(min(deadline, asyncio.get_running_loop().time() + DOC_TIMEOUT_S)):
            with tempfile.TemporaryDirectory() as directory:
                pdf = Path(directory) / "document.pdf"
                output = Path(directory) / "result.json"
                pdf.write_bytes(content)
                process = _start_worker(pdf, output)
                try:
                    code = await asyncio.to_thread(process.wait)
                finally:
                    # Cancellation leaves the waiting thread alive until the child has exited.
                    if process.returncode != 0:
                        cleanup = asyncio.create_task(asyncio.to_thread(_stop_worker, process))
                        try:
                            await asyncio.shield(cleanup)
                        except asyncio.CancelledError:
                            await cleanup
                            raise
                if code or not output.exists():
                    return Result(None, error="Proces odczytu dokumentu zakończył się błędem.")
                return Result(**json.loads(output.read_bytes()))


async def _extract_one(index: int, upload: UploadFile, deadline: float) -> DocumentResult:
    item = DocumentResult(index=index, file=Path(upload.filename or f"plik_{index + 1}.pdf").name)
    content = await upload.read()
    if not content.lstrip().startswith(b"%PDF-"):
        item.error = "To nie jest plik PDF."
    else:
        try:
            result = await _read(content, deadline)
        except TimeoutError:
            item.error = f"Przekroczono limit {DOC_TIMEOUT_S} s na dokument."
        else:
            item.class_id, item.error = result.label, result.error
            item.data = json.loads(result.text)
            item.sources = _sources(result.trace)
    return item


SOURCE_KEYS = ("field", "value", "engine", "page", "snippet", "note")


def _sources(trace: dict | None) -> list[dict[str, Any]]:
    """Where each extracted value came from: the engine, the page and the printed fragment."""
    fields = (trace or {}).get("fields", [])
    return [{key: entry.get(key) for key in SOURCE_KEYS} for entry in fields if entry.get("value") is not None]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "busy" if _slot.locked() or _queued >= MAX_QUEUED_REQUESTS else "ok"}


_UPLOAD_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["files"],
                    "properties": {"files": {"type": "array", "items": {"type": "string", "format": "binary"}}},
                }
            }
        },
    }
}


@app.post("/api/extract", response_model_by_alias=True, openapi_extra=_UPLOAD_SCHEMA)
async def extract(request: Request) -> ExtractResponse:
    global _queued
    if _queued >= MAX_QUEUED_REQUESTS:
        raise HTTPException(503, "Serwer przetwarza teraz inne pliki. Spróbuj za chwilę.")
    _queued += 1
    deadline = asyncio.get_running_loop().time() + REQUEST_BUDGET_S
    try:
        async with asyncio.timeout_at(deadline):
            form = await _uploads(request, deadline)
            try:
                files = form.getlist("files")
                if not files or any(not isinstance(f, UploadFile) for f in files):
                    raise HTTPException(422, "Wybierz pliki PDF.")
                results = [await _extract_one(i, upload, deadline) for i, upload in enumerate(files)]
                return ExtractResponse(results=results)
            finally:
                await form.close()
    except TimeoutError as exc:
        raise HTTPException(408, "Przekroczono limit czasu żądania.") from exc
    finally:
        _queued -= 1
