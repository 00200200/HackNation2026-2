"""HTTP API for the public page (doc2json.pl): the same per-document extraction as the CLI and GUI.

    GET  /api/health   -> {"status": "ok"}
    POST /api/extract  multipart `files` (PDF) -> {"results": [{"index", "file", "class", "data", "error"}]}

`index` follows the upload order, so two files with the same name stay apart. `class` is the class id from
`config/classes/*.toml` (null for a document outside every class, whose `data` is then `{}`).
Run: `uvicorn kio2json.web_api:app --host 0.0.0.0 --port 8000`. Starlette, uvicorn and python-multipart come with shiny.
"""

import asyncio
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .batch import Result, configure_logging, read_document
from .class_config import DocumentClass, load_classes

MAX_FILES = int(os.environ.get("KIO_WEB_MAX_FILES", "12"))
MAX_FILE_MB = int(os.environ.get("KIO_WEB_MAX_FILE_MB", "25"))
DOC_TIMEOUT_S = int(os.environ.get("KIO_WEB_DOC_TIMEOUT_S", "120"))
# OCR is CPU-heavy and the VPS is shared with another demo: documents queue for a small pool. A timed-out
# document that has not started is cancelled; one already running finishes in the background.
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("KIO_WEB_WORKERS", "1")))


@cache
def _classes() -> list[DocumentClass]:
    classes = load_classes()
    configure_logging(classes)
    return classes


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _extract_one(path: Path) -> Result:
    job = asyncio.get_running_loop().run_in_executor(_pool, read_document, path, _classes())
    try:
        return await asyncio.wait_for(job, DOC_TIMEOUT_S)
    except TimeoutError:
        return Result(None, "", f"Przekroczono limit {DOC_TIMEOUT_S} s na dokument.")


async def extract(request: Request) -> JSONResponse:
    try:
        form = await request.form(max_files=MAX_FILES, max_part_size=MAX_FILE_MB * 1024 * 1024)
    except HTTPException:
        return _error(f"Za dużo plików lub plik za duży (limit: {MAX_FILES} plików po {MAX_FILE_MB} MB).", 413)
    try:
        uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
        if not uploads:
            return _error("Wyślij co najmniej jeden plik PDF w polu 'files'.", 400)
        results = []
        with tempfile.TemporaryDirectory(prefix="doc2json-") as tmp:
            for index, upload in enumerate(uploads):
                name = Path(upload.filename or f"plik_{index + 1}.pdf").name
                head = await upload.read(5)
                if head != b"%PDF-":
                    results.append(
                        {"index": index, "file": name, "class": None, "data": None, "error": "To nie jest plik PDF."}
                    )
                    continue
                path = Path(tmp, f"{index}.pdf")
                path.write_bytes(head + await upload.read())
                result = await _extract_one(path)
                data = json.loads(result.text) if result.text else ({} if result.error is None else None)
                results.append(
                    {"index": index, "file": name, "class": result.label, "data": data, "error": result.error}
                )
    finally:
        await form.close()
    return JSONResponse({"results": results})


app = Starlette(
    routes=[Route("/api/health", health), Route("/api/extract", extract, methods=["POST"])],
)
