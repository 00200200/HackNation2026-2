"""Synthetic controls for document-level OCR outcomes."""

import sys
from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from kio2json import __main__ as cli
from kio2json import pdf_text


def scan(path, *lines, blur=0):
    images = []
    for line in lines:
        image = Image.new("RGB", (900, 240), "white")
        ImageDraw.Draw(image).text((60, 50), line, font=ImageFont.load_default(size=56), fill="black")
        images.append(image.filter(ImageFilter.GaussianBlur(blur)) if blur else image)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=150)


def test_unreadable_batch_reports_only_the_blurred_scan_and_continues(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract")
    blank, ordinary = tmp_path / "a.pdf", tmp_path / "b.pdf"
    scan(blank, "PLAN SALI", "", blur=30)
    scan(ordinary, "", "PLAN SALI")
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(tmp_path), "--output", str(output)])
    assert cli.main() == 1
    stderr = capsys.readouterr().err
    assert str(blank) in stderr and "no readable text after OCR" in stderr
    assert str(ordinary) not in stderr
    assert (output / "a.json").read_bytes() == (output / "b.json").read_bytes() == b""
    blank.unlink()
    assert cli.main() == 0


def test_empty_ocr_next_to_native_text_and_empty_document(monkeypatch):
    doc = MagicMock()
    blank, native = MagicMock(page_number=1), MagicMock(page_number=2)
    blank.extract_text.return_value = ""
    native.extract_text.return_value = "Informacja dla uczestników"
    doc.__enter__.return_value.pages = [blank, native]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda _: doc)
    monkeypatch.setattr(pdf_text, "_ocr", lambda page, words: "")
    attempted = []
    assert pdf_text.read_pages("mixed.pdf", ocr_pages=attempted) == ["", "Informacja dla uczestników"]
    assert attempted == [1]
    doc.__enter__.return_value.pages = []
    assert pdf_text.read_pages("empty.pdf") == []


def test_page_counter_after_ocr_is_unreadable_but_a_short_label_is_readable(tmp_path):
    attempted = []
    pdf = tmp_path / "scan.pdf"
    scan(pdf, "Strona 1 z 1")
    with pytest.raises(pdf_text.NoReadableTextError, match="no readable text after OCR"):
        pdf_text.read_pages(pdf, engine="tesseract", ocr_pages=attempted)
    assert attempted == [1]
    scan(pdf, "Sala 42")
    assert pdf_text.read_pages(pdf, engine="tesseract") == ["Sala 42"]


def test_scanned_numeric_identifier_is_readable(tmp_path):
    path = tmp_path / "identifier.pdf"
    scan(path, "2026112107046839")
    (text,) = pdf_text.read_pages(path, engine="tesseract")
    assert sum(c.isdigit() for c in text) >= 14


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [("202611210/7046839", True), ("2026112107046839", True), ("12 / 45", False), ("— 23 —", False)],
)
def test_long_identifiers_and_bare_page_counters(transcript, expected):
    assert pdf_text._readable(transcript) is expected


def test_explicit_tesseract_dpi_overrides_environment(tmp_path, monkeypatch):
    import tesserocr

    seen = []
    api_class = tesserocr.PyTessBaseAPI

    class RecordingAPI(api_class):
        def SetImage(self, image):
            seen.append("image")
            return super().SetImage(image)

        def SetSourceResolution(self, resolution):
            seen.append(resolution)
            return super().SetSourceResolution(resolution)

    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", RecordingAPI)
    monkeypatch.setenv("KIO_OCR_ENGINE", "missing")
    path = tmp_path / "scan.pdf"
    scan(path, "PLAN SALI")
    assert pdf_text.read_pages(path, engine="tesseract-dpi") == ["PLAN SALI"]
    assert seen == ["image", 300]
    seen.clear()
    assert pdf_text.read_pages(path, engine="tesseract") == ["PLAN SALI"]
    assert seen == ["image"]


@pytest.fixture
def rapid_worker():
    from kio2json import rapid_worker

    rapid_worker.close()
    yield rapid_worker
    rapid_worker.close()


def test_rapidocr_timeout_kills_the_stalled_worker_and_next_request_recovers(tmp_path, monkeypatch, rapid_worker):
    import os
    from time import monotonic

    # Replace the optional model at its import boundary, inside the real worker process.
    control = tmp_path / "stall"
    (tmp_path / "onnxruntime.py").write_text("")
    (tmp_path / "rapidocr.py").write_text(
        "import os, time\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
        "class RapidOCR:\n"
        "    def __init__(self, params): print('model loaded', flush=True)\n"
        "    def __call__(self, image, return_word_box):\n"
        "        if Path(os.environ['TEST_STALL_FILE']).exists(): time.sleep(30)\n"
        "        return SimpleNamespace(txts=['Model ' + str(os.getpid())], word_results=[])\n"
    )
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(tmp_path), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.setenv("TEST_STALL_FILE", str(control))
    path = tmp_path / "scan.pdf"
    scan(path, "PLAN SALI")
    pages = pdf_text.read_pages(path, engine="rapidocr")
    assert pages[0].startswith("Model ")
    assert pdf_text.read_pages(path, engine="rapidocr") == pages
    process = rapid_worker._process
    control.touch()
    with monkeypatch.context() as settings:
        settings.setattr(pdf_text, "OCR_TIMEOUT_SECONDS", 0.3)
        start = monotonic()
        with pytest.raises(TimeoutError, match="RapidOCR timed out"):
            pdf_text.read_pages(path, engine="rapidocr")
        assert monotonic() - start < 5
    assert process.returncode is not None
    control.unlink()
    assert pdf_text.read_pages(path, engine="rapidocr") != pages
