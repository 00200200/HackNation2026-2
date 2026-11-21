"""HTTP API for the public page (doc2json.pl): the same per-document extraction as the CLI and GUI.

    GET  /api/health   -> {"status": "ok"}
    POST /api/extract  multipart `files` (PDF) -> {"results": [{"index", "file", "class", "data", "error"}]}
    GET  /api/docs     -> OpenAPI docs

`index` follows the upload order, so two files with the same name stay apart. `class` is the class id from
`config/classes/*.toml` (null for a document outside every class, whose `data` is then `{}`).
Run: `uvicorn kio2json.web_api:app --host 0.0.0.0 --port 8000`.
"""

import asyncio
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .batch import Result, configure_logging, read_document
from .class_config import DocumentClass, load_classes

MAX_FILES = int(os.environ.get("KIO_WEB_MAX_FILES", "10"))
MAX_FILE_MB = int(os.environ.get("KIO_WEB_MAX_FILE_MB", "20"))
DOC_TIMEOUT_S = int(os.environ.get("KIO_WEB_DOC_TIMEOUT_S", "90"))
REQUEST_BUDGET_S = int(os.environ.get("KIO_WEB_REQUEST_BUDGET_S", "500"))  # under the 600 s proxy and page limits
MAX_QUEUED_REQUESTS = int(os.environ.get("KIO_WEB_MAX_QUEUED", "4"))

# OCR is CPU-heavy and the VPS is shared with another demo: one document at a time, server-wide. A document's
# timeout counts from when it starts; the slot stays taken until its thread really ends (threads cannot be killed).
_pool = ThreadPoolExecutor(max_workers=1)
_slot = asyncio.Semaphore(1)
_queued = 0

app = FastAPI(title="doc2json", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


class DocumentResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    file: str
    class_id: str | None = Field(None, alias="class")
    data: dict[str, Any] | None = None
    error: str | None = None


class ExtractResponse(BaseModel):
    results: list[DocumentResult]


@cache
def _classes() -> list[DocumentClass]:
    classes = load_classes()
    configure_logging(classes)
    return classes


def _read_and_delete(path: Path) -> Result:
    try:
        return read_document(path, _classes())
    finally:
        path.unlink(missing_ok=True)


async def _read(content: bytes) -> Result:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(content)
    await _slot.acquire()
    job = asyncio.get_running_loop().run_in_executor(_pool, _read_and_delete, Path(handle.name))
    job.add_done_callback(lambda _: _slot.release())
    try:
        return await asyncio.wait_for(asyncio.shield(job), DOC_TIMEOUT_S)
    except TimeoutError:
        return Result(None, "", f"Przekroczono limit {DOC_TIMEOUT_S} s na dokument.")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/extract", response_model_by_alias=True)
async def extract(files: list[UploadFile]) -> ExtractResponse:
    global _queued
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"Najwyżej {MAX_FILES} plików naraz.")
    if _queued >= MAX_QUEUED_REQUESTS:
        raise HTTPException(503, "Serwer przetwarza teraz inne pliki. Spróbuj za chwilę.")
    _queued += 1
    try:
        deadline = time.monotonic() + REQUEST_BUDGET_S
        results = []
        for index, upload in enumerate(files):
            item = DocumentResult(index=index, file=Path(upload.filename or f"plik_{index + 1}.pdf").name)
            content = await upload.read(MAX_FILE_MB * 1024 * 1024 + 1)
            if len(content) > MAX_FILE_MB * 1024 * 1024:
                item.error = f"Plik większy niż {MAX_FILE_MB} MB."
            elif content.lstrip()[:5] != b"%PDF-":
                item.error = "To nie jest plik PDF."
            elif time.monotonic() > deadline:
                item.error = "Nie zmieścił się w limicie czasu tego żądania. Wyślij go osobno."
            else:
                result = await _read(content)
                item.class_id, item.error = result.label, result.error
                item.data = json.loads(result.text) if result.text else ({} if result.error is None else None)
            results.append(item)
        return ExtractResponse(results=results)
    finally:
        _queued -= 1
