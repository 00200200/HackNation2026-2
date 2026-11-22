"""The shared keyed document path recovers locally and processes the next document."""

import json
import sys
from pathlib import Path

import httpx2
import pytest

from kio2json import __main__ as cli
from kio2json import gui_files, pipeline, power_of_attorney, rapid_worker
from kio2json.pdf_text import NoReadableTextError

SECRET = "invented-secret"
PRIVATE = "invented-private-text"


@pytest.fixture
def inputs(tmp_path, monkeypatch, in_process_cli):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    for k, v in {
        "BASE_URL": "https://offline.invalid/v1",
        "MODEL": "invented",
        "API_KEY": SECRET,
        "MODE": "L",
        "ROUTING": "rules",
        "DUAL_OCR": "true",
    }.items():
        monkeypatch.setenv("KIO_LLM_" + k, v)
    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract-dpi")
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "one.pdf").touch()
    (folder / "two.pdf").touch()
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(folder), "--output", "out"])
    return folder


@pytest.mark.parametrize(
    "failure",
    [
        "routing",
        "validation",
        "malformed",
        "refused",
        "timeout",
        "transport",
        "alternate",
        "unreadable",
        "corrupt",
        "rules",
    ],
)
def test_bundled_keyed_batch_recovers_and_continues(inputs, monkeypatch, capsys, failure):
    reads = []
    later_calls = []
    if failure == "routing":
        monkeypatch.setenv("KIO_LLM_ROUTING", "model")

    def pages(path, *, ocr_pages, **kwargs):
        reads.append(path.name)
        if path.name == "one.pdf":
            if failure == "unreadable":
                raise NoReadableTextError(PRIVATE)
            if failure == "corrupt":
                raise ValueError(PRIVATE)
            if failure == "alternate":
                ocr_pages.append(1)
        return ["PEŁNOMOCNICTWO\n" + (PRIVATE if path.name == "one.pdf" else "second")]

    def broken(*args, **kwargs):
        raise RuntimeError(SECRET + PRIVATE)

    monkeypatch.setattr(pipeline, "read_pages", pages)
    monkeypatch.setattr(rapid_worker, "recognize", broken)
    if failure == "rules":
        monkeypatch.setattr(power_of_attorney, "extract", broken)

    async def respond(transport, request):
        body = json.loads(request.content)
        text = " ".join(m["content"] or "" for m in body["messages"])
        if PRIVATE in text:
            if failure == "timeout":
                raise httpx2.ReadTimeout(SECRET, request=request)
            if failure == "transport":
                return httpx2.Response(503, json={"error": {"message": SECRET}})
            content = "{" if failure == "malformed" else "{}"
            message = {"role": "assistant", "content": content}
            if failure == "refused":
                message.update(content=None, refusal=PRIVATE)
        else:
            later_calls.append(True)
            data = (
                {"label": "power_of_attorney"}
                if "Classify this Polish" in text
                else {"mocodawca": [], "pelnomocnicy": []}
            )
            message = {"role": "assistant", "content": json.dumps(data)}
        return httpx2.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": "invented",
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            },
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", respond)
    assert cli.main() == 0
    assert reads == ["one.pdf", "two.pdf"]
    assert later_calls
    captured = capsys.readouterr()
    assert "one.pdf" in captured.err
    assert SECRET not in captured.err and PRIVATE not in captured.err
    assert json.loads(Path("out/two.json").read_text()) == {"mocodawca": [], "pelnomocnicy": []}
    first = Path("out/one.json")
    if failure in ("unreadable", "corrupt", "rules"):
        assert first.read_text() == "{}\n"
    else:
        assert json.loads(first.read_text()) == {"mocodawca": [], "pelnomocnicy": []}


def test_gui_keyed_unreadable_returns_empty_object_and_marks_recovery(inputs, tmp_path, monkeypatch, capsys):
    def unreadable(*args, **kwargs):
        raise ValueError(PRIVATE)

    monkeypatch.setattr(pipeline, "read_pages", unreadable)
    docs = gui_files.analyze([(Path("case/one.pdf"), inputs / "one.pdf")], tmp_path)
    assert docs[0].result.text == "{}\n" and docs[0].result.used_recovery
    assert PRIVATE not in capsys.readouterr().err


def test_keyed_structural_errors_still_fail(inputs, monkeypatch, capsys):
    monkeypatch.setenv("KIO_LLM_TIMEOUT_SECONDS", "invalid")
    assert cli.main() == 1
    assert "configuration" in capsys.readouterr().err
    monkeypatch.delenv("KIO_LLM_TIMEOUT_SECONDS")
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", "absent"])
    with pytest.raises(SystemExit, match="2"):
        cli.main()
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(inputs), "--output", str(inputs / "one.pdf")])
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: ["unrelated"])
    with pytest.raises(OSError):
        cli.main()
