from pathlib import Path

import pytest

from kio2json import pipeline


@pytest.mark.parametrize(
    ("primary", "scanned", "secondary", "expected", "calls"),
    [
        (["PEŁNOMOCNICTWO"], True, None, "power_of_attorney", 1),
        (["Informacja"], False, None, None, 1),
        (["Informacja"], True, ["PEŁNOMOCNICTWO"], "power_of_attorney", 2),
        (None, True, ["PEŁNOMOCNICTWO"], "power_of_attorney", 2),
        (["Faktura VAT"], True, None, None, 2),
    ],
)
def test_hybrid_retries_only_unrouted_ocr_documents(monkeypatch, primary, scanned, secondary, expected, calls):
    monkeypatch.setenv("KIO_OCR_ENGINE", "hybrid")
    engines = []

    def read(path, *, force_ocr, engine=None, ocr_pages=None, **kwargs):
        engines.append(engine)
        if scanned and ocr_pages is not None:
            ocr_pages.append(1)
        pages = primary if engine == "tesseract-dpi" else secondary
        if pages is None:
            raise pipeline.NoReadableTextError("no readable text after OCR")
        return pages

    monkeypatch.setattr(pipeline, "read_pages", read)
    assert pipeline.process_pdf(Path("invented.pdf"))[0] == expected
    assert engines == ["tesseract-dpi", "rapidocr"][:calls]


def test_hybrid_reports_two_unreadable_transcripts(monkeypatch):
    monkeypatch.setenv("KIO_OCR_ENGINE", "hybrid")
    engines = []

    def unreadable(path, *, engine=None, **kwargs):
        engines.append(engine)
        raise pipeline.NoReadableTextError("no readable text after OCR")

    monkeypatch.setattr(pipeline, "read_pages", unreadable)
    with pytest.raises(pipeline.NoReadableTextError, match="no readable text after OCR"):
        pipeline.process_pdf(Path("invented.pdf"))
    assert engines == ["tesseract-dpi", "rapidocr"]


def test_shared_cli_and_gui_reader_accepts_a_blank_scan(tmp_path, monkeypatch):
    from PIL import Image

    from kio2json.batch import read_document
    from kio2json.class_config import load_classes

    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract")
    path = tmp_path / "blank.pdf"
    Image.new("RGB", (300, 180), "white").save(path, resolution=150)
    result = read_document(path, load_classes())
    assert result.error is None
    assert result.text == ""


def test_hybrid_retries_failed_primary_recognition(monkeypatch):
    monkeypatch.setenv("KIO_OCR_ENGINE", "hybrid")

    def read(path, *, engine, **kwargs):
        if engine == "tesseract-dpi":
            raise pipeline.OCRRecognitionError("Polish OCR failed or timed out")
        return ["PEŁNOMOCNICTWO"]

    monkeypatch.setattr(pipeline, "read_pages", read)
    assert pipeline.process_pdf(Path("invented.pdf"))[0] == "power_of_attorney"
