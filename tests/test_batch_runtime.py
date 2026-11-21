import os
import subprocess
import sys
from pathlib import Path

import pytest

from kio2json import pipeline


def test_parallel_cli_preserves_bytes_order_and_failure_status(tmp_path):
    source = Path("data/uzp/dane/przyklad_01")
    inputs = tmp_path / "input"
    inputs.mkdir()
    for p in source.glob("*.pdf"):
        (inputs / p.name).write_bytes(p.read_bytes())
    (inputs / "bad.PDF").write_bytes(b"invalid PDF")
    outputs = []
    for workers in (1, 2):
        target = tmp_path / str(workers)
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "kio2json",
                "--input",
                str(inputs),
                "--output",
                str(target),
                "--workers",
                str(workers),
            ],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "KIO_LLM_API_KEY": "", "OMP_THREAD_LIMIT": "8"},
        )
        assert run.returncode == 1, run.stderr
        assert run.stderr.count("bad.PDF: not processed") == 1
        assert (target / "bad.json").read_bytes() == b""
        outputs.append(
            ({p.name: p.read_bytes() for p in target.glob("*.json")}, run.stdout.replace(str(target), "out"))
        )
    assert outputs[0] == outputs[1]
    assert len(outputs[0][0]) == 4 and any(outputs[0][0].values())


def test_expired_reread_budget_keeps_primary_ocr(monkeypatch):
    from kio2json import ocr_budget

    monkeypatch.setattr(ocr_budget, "REREAD_DEADLINE_SECONDS", 0)
    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract-dpi")
    calls = []

    def read(path, *, engine, ocr_pages, **kwargs):
        calls.append(engine)
        ocr_pages.append(1)
        return ["Potwierdzenie wykonania operacji\nDzienny numer transakcji"]

    monkeypatch.setattr(pipeline, "read_pages", read)
    assert pipeline.process_pdf(Path("receipt.pdf")) == (None, {})
    assert calls == ["tesseract-dpi"]


@pytest.mark.parametrize(("workers", "exit_call"), [(1, "os._exit(17)"), (2, "os._exit(17)"), (2, "sys.exit(0)")])
def test_crashed_worker_does_not_lose_healthy_documents(tmp_path, monkeypatch, workers, exit_call):
    # A trusted custom extractor simulates a native backend terminating its process.
    from kio2json.batch import read_batch
    from kio2json.class_config import class_sources

    (tmp_path / "runtime_fixture.py").write_text(
        "import os, sys\n"
        "def backend(text):\n"
        "    if text.startswith('PEŁNOMOCNICTWO'):\n"
        f"        {exit_call}\n"
        "    return {'threads': os.environ['OMP_THREAD_LIMIT']}\n"
        "extract = lambda text: backend(text)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "example.toml").write_text(
        'id = "example"\nengines = ["python"]\nextractor = "runtime_fixture.extract"\n'
        "[routing]\nrequired = ['\\w']\n[fields.threads]\ntype = 'string'\ninstruction = 'test'\n"
    )
    source = Path("data/uzp/dane/przyklad_01")
    pdfs = [source / name for name in ("przelew.pdf", "pelnomocnictwo.pdf", "odwolanie.pdf")]
    monkeypatch.setenv("OMP_THREAD_LIMIT", "8")
    first, failed, last = read_batch(pdfs, class_sources(tmp_path), workers)
    assert first.text == last.text == '{\n  "threads": "1"\n}\n'
    assert failed.text == "" and failed.error


def test_crop_verification_obeys_remaining_milliseconds(monkeypatch):
    from unittest.mock import Mock

    from kio2json import ocr_budget, ocr_grant_register
    from kio2json.model_pages import AlternateOCR

    clock = [20.0]
    monkeypatch.setattr(ocr_budget, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ocr_budget, "REREAD_DEADLINE_SECONDS", 1)
    first, second = Mock(), Mock()
    first.GetUTF8Text.return_value = "1234567891"

    def recognize(*, timeout):
        assert timeout == 250
        clock[0] += 0.3
        return True

    first.Recognize.side_effect = recognize
    with ocr_budget.document_budget():
        clock[0] += 0.75
        assert ocr_grant_register._agreement(None, [first, second], "1234567890") == "1234567890"
        second.Recognize.assert_not_called()
        assert AlternateOCR(Path("unused.pdf"), [1, 2]).read_all() == ["", ""]
    with ocr_budget.document_budget():
        assert ocr_budget.remaining_ms(5000) == 1000
