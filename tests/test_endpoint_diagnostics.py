"""Endpoint failures pass through the SDK and batch CLI without using the network."""

import json
import logging
import sys

import httpx2
import pytest

from kio2json import __main__ as cli
from kio2json import pipeline
from kio2json.class_config import DocumentClass


@pytest.mark.parametrize(
    ("failure", "diagnostic"),
    [
        (401, "ModelAuthenticationError, HTTP 401"),
        (503, "ModelUnavailableError, HTTP 503"),
        (302, "ModelAPIError, HTTP 302"),
        ("disconnect", "ModelConnectionError"),
        ("invalid-url", "InvalidURL"),
    ],
)
def test_cli_endpoint_failure_reports_only_path_type_and_status(
    tmp_path, monkeypatch, capsys, caplog, failure, diagnostic, in_process_cli
):
    secret = "invented-endpoint-key"
    url = "https://operator:invented-password@offline.invalid/v1"
    monkeypatch.setenv("KIO_LLM_BASE_URL", url if failure != "invalid-url" else url.replace(".invalid", f":{secret}"))
    monkeypatch.setenv("KIO_LLM_MODEL", "invented-model")
    monkeypatch.setenv("KIO_LLM_API_KEY", secret)
    # Exercise the first-run banner as it would behave for an interactive CLI user.
    for name in ("PYTEST_VERSION", "CI", "PYDANTIC_AI_NO_BANNER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_AGENT", "test-agent")
    # OPENAI_LOG=debug enables the SDK logger, which prints the server's X-Request-ID.
    monkeypatch.setenv("OPENAI_LOG", "debug")
    for logger in ("openai", "httpx2", "httpcore2"):
        caplog.set_level(logging.DEBUG, logger=logger)

    async def respond(transport, request):
        if failure == "disconnect":
            raise httpx2.ConnectError(f"Cannot reach {url} with credential {secret}", request=request)
        return httpx2.Response(
            failure,
            headers={"X-Request-ID": "invented-header"},
            json={"error": {"message": f"Rejected key {secret} on {url}", "code": "invented-error"}},
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", respond)
    receipt = DocumentClass.model_validate(
        {
            "id": "receipt",
            "routing": {"required": ["Receipt"]},
            "engines": ["labelled_fields", "llm"],
            "fields": {"ref": {"type": "string", "instruction": "Receipt reference", "pattern": r"Ref: (.+)"}},
        }
    )
    monkeypatch.setattr(cli, "parse_classes", lambda _: [receipt])
    first = tmp_path / "first.pdf"
    first.touch()
    (tmp_path / "second.pdf").touch()
    monkeypatch.setattr(
        pipeline, "read_pages", lambda path, **_: ["Receipt" if path == first else "Receipt\nRef: NIGHT-5"]
    )
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(tmp_path), "--output", str(output)])

    assert cli.main() == 1
    assert capsys.readouterr().err == f"{first}: not processed ({diagnostic})\n"
    assert "invented-header" not in caplog.text
    assert "offline.invalid" not in caplog.text
    assert (output / "first.json").read_bytes() == b""
    assert json.loads((output / "second.json").read_text()) == {"ref": "NIGHT-5"}
