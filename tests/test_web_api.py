import pytest
from starlette.testclient import TestClient

from kio2json import web_api
from kio2json.batch import Result


@pytest.fixture
def client(monkeypatch):
    def fake_read(path, classes):
        if path.read_bytes().startswith(b"%PDF-1.7 transfer"):
            return Result("bank_transfer", '{"przelew_bankowy": {"kwota": 123.45}}\n')
        return Result(None, "")

    monkeypatch.setattr(web_api, "read_document", fake_read)
    monkeypatch.setattr(web_api, "_classes", list)
    return TestClient(web_api.app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_extract_keeps_upload_order_and_duplicate_names(client):
    files = [
        ("files", ("dokument.pdf", b"%PDF-1.7 transfer", "application/pdf")),
        ("files", ("dokument.pdf", b"%PDF-1.7 other", "application/pdf")),
        ("files", ("notatka.pdf", b"not a pdf", "application/pdf")),
    ]
    results = client.post("/api/extract", files=files).json()["results"]
    assert [r["index"] for r in results] == [0, 1, 2]
    assert results[0] == {
        "index": 0,
        "file": "dokument.pdf",
        "class": "bank_transfer",
        "data": {"przelew_bankowy": {"kwota": 123.45}},
        "error": None,
    }
    assert results[1]["class"] is None and results[1]["data"] == {} and results[1]["error"] is None
    assert results[2]["data"] is None and results[2]["error"]


def test_extract_requires_files(client):
    assert client.post("/api/extract", data={"x": "1"}).status_code == 422


def test_extract_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(web_api, "MAX_FILE_MB", 0)
    results = client.post("/api/extract", files=[("files", ("a.pdf", b"%PDF-1.7", "application/pdf"))]).json()
    assert results["results"][0]["error"] and results["results"][0]["data"] is None


def test_extract_limits_file_count(client):
    files = [("files", (f"{i}.pdf", b"%PDF-1.7", "application/pdf")) for i in range(web_api.MAX_FILES + 1)]
    assert client.post("/api/extract", files=files).status_code == 413


def test_document_waiting_past_the_budget_is_reported(client, monkeypatch):
    monkeypatch.setattr(web_api, "REQUEST_BUDGET_S", 0)
    results = client.post("/api/extract", files=[("files", ("a.pdf", b"%PDF-1.7", "application/pdf"))]).json()
    assert results["results"][0]["error"] and results["results"][0]["data"] is None
