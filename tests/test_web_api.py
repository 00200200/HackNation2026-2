import asyncio
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from starlette import formparsers
from starlette.testclient import TestClient

from kio2json import web_api
from kio2json.batch import Result


@pytest.fixture
def client(monkeypatch):
    async def fake_read(content, deadline):
        if content.startswith(b"%PDF-1.7 transfer"):
            return Result("bank_transfer", '{"przelew_bankowy": {"kwota": 123.45}}')
        if content.startswith(b"%PDF-1.7 broken"):
            return Result(None, error="unreadable PDF")
        return Result(None, "{}\n")

    monkeypatch.setattr(web_api, "_read", fake_read)
    return TestClient(web_api.app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_extract_keeps_upload_order_and_duplicate_names(client):
    files = [
        ("files", ("dokument.pdf", b"%PDF-1.7 transfer", "application/pdf")),
        ("files", ("dokument.pdf", b"%PDF-1.7 other", "application/pdf")),
        ("files", ("notatka.pdf", b"not a pdf", "application/pdf")),
        ("files", ("broken.pdf", b"%PDF-1.7 broken", "application/pdf")),
    ]
    results = client.post("/api/extract", files=files).json()["results"]
    assert [r["index"] for r in results] == [0, 1, 2, 3]
    assert results[0] == {
        "index": 0,
        "file": "dokument.pdf",
        "class": "bank_transfer",
        "data": {"przelew_bankowy": {"kwota": 123.45}},
        "error": None,
    }
    assert results[1]["class"] is None and results[1]["data"] == {} and results[1]["error"] is None
    assert results[2]["data"] == {} and results[2]["error"]
    assert results[3]["data"] == {} and results[3]["error"] == "unreadable PDF"


def test_extract_requires_files(client):
    assert client.post("/api/extract", data={"x": "1"}).status_code == 422


def test_extract_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(web_api, "MAX_FILE_MB", 0)
    assert client.post("/api/extract", files={"files": ("a.pdf", b"%PDF-1.7")}).status_code == 413


def test_extract_limits_file_count(client):
    files = [("files", (f"{i}.pdf", b"%PDF-1.7", "application/pdf")) for i in range(web_api.MAX_FILES + 1)]
    assert client.post("/api/extract", files=files).status_code == 413


def test_receipt_limits_close_partial_uploads(monkeypatch):
    spools = []
    make_spool = formparsers.SpooledTemporaryFile

    def tracked_spool(*args, **kwargs):
        file = make_spool(*args, **kwargs)
        spools.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_spool)
    start = b'--test\r\nContent-Disposition: form-data; name="files"; filename="sample.pdf"\r\n\r\n'
    headers = {"content-type": "multipart/form-data; boundary=test"}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_api.app), base_url="http://test") as client:
            monkeypatch.setattr(web_api, "MAX_FILE_MB", 0)

            async def oversized():
                yield start
                yield b"x"
                pytest.fail("read past the file limit")

            assert (await client.post("/api/extract", content=oversized(), headers=headers)).status_code == 413
            assert spools and all(file.closed for file in spools)
            spools.clear()
            monkeypatch.setattr(web_api, "REQUEST_BUDGET_S", 0.1)

            async def delayed():
                yield start
                await asyncio.sleep(3)
                pytest.fail("waited past the receipt deadline")

            assert (await client.post("/api/extract", content=delayed(), headers=headers)).status_code == 408
            assert spools and all(file.closed for file in spools)
            assert web_api._queued == 0

    asyncio.run(run())


@pytest.mark.parametrize("short_limit", ["DOC_TIMEOUT_S", "REQUEST_BUDGET_S"])
def test_worker_deadlines_reap_process_clean_files_and_restore_service(monkeypatch, short_limit):
    processes = []
    paths = []
    started = asyncio.Event()
    ordinary_pdf = Path("data/uzp/dane/przyklad_01/przelew.pdf").read_bytes()
    normal_worker = web_api._start_worker

    def start_worker(pdf, output):
        paths.append(pdf.parent)
        if len(paths) == 1:
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=web_api.os.name == "posix"
            )
            processes.append(child)
            started.set()
            return child
        return normal_worker(pdf, output)

    async def run():
        monkeypatch.setattr(web_api, "_slot", asyncio.Semaphore(1))
        monkeypatch.setattr(web_api, "_start_worker", start_worker)
        monkeypatch.setattr(web_api, short_limit, 0.3)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_api.app), base_url="http://test") as client:
            pending = asyncio.create_task(client.post("/api/extract", files={"files": ("stuck.pdf", b"%PDF-")}))
            await asyncio.wait_for(started.wait(), 3)
            assert (await client.get("/api/health")).json()["status"] == "busy"
            response = await pending
            if short_limit == "DOC_TIMEOUT_S":
                item = response.json()["results"][0]
                assert item["data"] == {} and item["error"]
            else:
                assert response.status_code == 408
            assert processes[0].poll() is not None and not paths[0].exists()
            assert (await client.get("/api/health")).json()["status"] == "ok"

            monkeypatch.setattr(web_api, short_limit, 30)
            normal = await client.post("/api/extract", files={"files": ("przelew.pdf", ordinary_pdf)})
            result = normal.json()["results"][0]
            assert result["class"] == "bank_transfer" and result["data"] and result["error"] is None
            assert not paths[1].exists()

    asyncio.run(run())


def test_failed_worker_launch_cleans_directory_and_slot(monkeypatch):
    paths = []

    def fail(pdf, output):
        paths.append(pdf)
        raise OSError("launch failed")

    monkeypatch.setattr(web_api, "_start_worker", fail)
    with TestClient(web_api.app, raise_server_exceptions=False) as client:
        assert client.post("/api/extract", files={"files": ("a.pdf", b"%PDF-")}).status_code == 500
        assert not paths[0].parent.exists()
        assert client.get("/api/health").json() == {"status": "ok"}


def test_admission_and_queue_wait_share_request_budget(monkeypatch):
    async def no_body():
        pytest.fail("read the request body before admission")
        yield b""

    async def run():
        held = asyncio.Semaphore(0)
        monkeypatch.setattr(web_api, "_slot", held)
        monkeypatch.setattr(web_api, "REQUEST_BUDGET_S", 0.1)
        headers = {"content-type": "multipart/form-data; boundary=test", "content-length": "999999999"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web_api.app), base_url="http://test") as client:
            assert (await client.post("/api/extract", headers=headers, content=no_body())).status_code == 413
            with monkeypatch.context() as patch:
                patch.setattr(web_api, "MAX_QUEUED_REQUESTS", 0)
                assert (await client.post("/api/extract", headers=headers, content=no_body())).status_code == 503
            response = await client.post("/api/extract", files={"files": ("a.pdf", b"%PDF-")})
            assert response.status_code == 408 and held.locked() and web_api._queued == 0

    asyncio.run(run())
