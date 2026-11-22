import os
import subprocess
import sys
from pathlib import Path

import pytest

from kio2json import pipeline


@pytest.mark.parametrize(
    ("cpu_count", "options", "expected"),
    [(12, [], 4), (2, [], 2), (None, [], 1), (2, ["--workers", "8"], 8), (2, ["--jobs", "8"], 8)],
)
def test_cli_worker_count(tmp_path, monkeypatch, cpu_count, options, expected):
    from kio2json import __main__ as cli

    selected = []

    def record_workers(pdfs, sources, workers, explain=False):
        selected.append(workers)
        return iter(())

    monkeypatch.setattr(os, "process_cpu_count", lambda: cpu_count)
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(tmp_path), *options])
    monkeypatch.setattr(cli, "read_batch", record_workers)
    assert cli.main() == 0
    assert selected == [expected]


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
        assert (target / "bad.json").read_bytes() == b"{}\n"
        outputs.append(
            ({p.name: p.read_bytes() for p in target.glob("*.json")}, run.stdout.replace(str(target), "out"))
        )
    assert outputs[0] == outputs[1]
    assert len(outputs[0][0]) == 4 and any(outputs[0][0].values())


def test_cli_prints_polish_file_names_to_a_legacy_code_page_stream(tmp_path):
    root = Path(__file__).resolve().parents[1]
    inputs = tmp_path / "input"
    inputs.mkdir()
    (inputs / "pełnomocnictwo.pdf").write_bytes((root / "data/uzp/dane/przyklad_01/pelnomocnictwo.pdf").read_bytes())
    run = subprocess.run(
        [sys.executable, "-m", "kio2json", "--input", str(inputs), "--output", str(tmp_path / "out"), "--workers", "1"],
        capture_output=True,
        check=False,
        cwd=root,
        env={**os.environ, "KIO_LLM_API_KEY": "", "PYTHONIOENCODING": "cp1252"},
    )
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    assert "pełnomocnictwo.json" in run.stdout.decode("utf-8")
    assert (tmp_path / "out" / "pełnomocnictwo.json").read_text(encoding="utf-8").startswith("{")


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
    from kio2json import batch
    from kio2json.class_config import class_sources

    (tmp_path / "runtime_fixture.py").write_text(
        "import os, sys\n"
        "from kio2json.ocr_budget import remaining_ms\n"
        "def backend(text):\n"
        "    if text.startswith('PEŁNOMOCNICTWO'):\n"
        f"        {exit_call}\n"
        "    assert remaining_ms(1) == 0, 'worker received a fresh batch deadline'\n"
        "    return {'threads': os.environ['OMP_THREAD_LIMIT']}\n"
        "extract = lambda text: backend(text)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "example.toml").write_text(
        'id = "example"\nengines = ["python"]\nextractor = "runtime_fixture.extract"\n'
        "[routing]\nrequired = ['\\w']\n[fields.threads]\ntype = 'string'\ninstruction = 'test'\n",
        encoding="utf-8",
    )
    source = Path("data/uzp/dane/przyklad_01")
    pdfs = [source / name for name in ("przelew.pdf", "pelnomocnictwo.pdf", "odwolanie.pdf")]
    monkeypatch.setenv("OMP_THREAD_LIMIT", "8")
    monkeypatch.setattr(batch, "batch_deadline", lambda count: 0.0)
    first, failed, last = batch.read_batch(pdfs, class_sources(tmp_path), workers)
    assert first.text == last.text == '{\n  "threads": "1"\n}\n'
    assert failed.text == "{}\n" and failed.error


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


def test_batch_deadline_is_shared_across_documents_and_preserves_primary(monkeypatch):
    from kio2json import ocr_budget
    from kio2json.batch import read_document
    from kio2json.class_config import load_classes

    clock = [100.0]
    monkeypatch.setattr(ocr_budget, "monotonic", lambda: clock[0])
    deadline = ocr_budget.batch_deadline(150)
    assert deadline - clock[0] == 27 * 60
    remaining = []

    def read(path, *, engine, ocr_pages=None, **kwargs):
        remaining.append((engine, ocr_budget.remaining_ms(10_000_000)))
        if ocr_pages is not None:
            ocr_pages.append(1)
        return ["Potwierdzenie wykonania operacji\nDzienny numer transakcji"]

    monkeypatch.setattr(pipeline, "read_pages", read)
    classes = load_classes()
    for seconds_left in (0.25, 0):
        clock[0] = deadline - seconds_left
        result = read_document(Path("receipt.pdf"), classes, batch_deadline=deadline)
        assert not result.error
    # First PDF receives a primary and an alternate read. Second receives only its primary.
    assert remaining == [("tesseract-dpi", 250), ("tesseract", 250), ("tesseract-dpi", 0)]
    assert ocr_budget.remaining_ms(5000) == 5000


def test_long_primary_pass_leaves_room_for_optional_ocr(monkeypatch):
    from kio2json import ocr_budget

    clock = [0.0]
    monkeypatch.setattr(ocr_budget, "monotonic", lambda: clock[0])
    with ocr_budget.document_budget():
        clock[0] += 59
        assert ocr_budget.remaining_ms(1000) == 1000


def test_small_batch_has_room_for_one_slow_scan(monkeypatch):
    from kio2json import ocr_budget

    monkeypatch.setattr(ocr_budget, "monotonic", lambda: 100.0)
    assert ocr_budget.batch_deadline(1) == 100 + ocr_budget.REREAD_DEADLINE_SECONDS
    assert ocr_budget.batch_deadline(30) == 100 + 324
