"""Synthetic controls for document-level OCR outcomes."""

import ctypes
import sys
from unittest.mock import MagicMock

import pypdfium2 as pdfium
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
    native.extract_text.return_value = "Informacja"
    doc.__enter__.return_value.pages = [blank, native]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda _: doc)
    monkeypatch.setattr(pdf_text, "_ocr", lambda page, words: "")
    attempted = []
    assert pdf_text.read_pages("mixed.pdf", ocr_pages=attempted) == ["", "Informacja"]
    assert attempted == [1]
    doc.__enter__.return_value.pages = []
    assert pdf_text.read_pages("empty.pdf") == []


def test_native_footer_alone_cannot_make_a_mixed_scan_readable(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    scan(path, "Strona nr 1 z 2", "Druga strona", blur=30)
    monkeypatch.setattr(
        pdf_text.pdfplumber.page.Page, "extract_text", lambda page: "Strona nr 1 z 2" if page.page_number == 1 else ""
    )
    monkeypatch.setattr(pdf_text.pdfplumber.page.Page, "images", [])
    attempted = []
    with pytest.raises(pdf_text.NoReadableTextError):
        pdf_text.read_pages(path, engine="tesseract", ocr_pages=attempted)
    assert attempted == [2]


@pytest.mark.parametrize(("paper", "ink"), [(0, 0), (242, 239)])
def test_uniform_dark_or_faint_nonblank_scan_with_empty_ocr_is_unreadable(tmp_path, monkeypatch, paper, ink):
    path = tmp_path / "dark.pdf"
    image = Image.new("L", (600, 320), paper)
    ImageDraw.Draw(image).text((30, 30), "Niewyrazny druk", font=ImageFont.load_default(size=48), fill=ink)
    image.save(path, resolution=150)
    monkeypatch.setattr(pdf_text, "_ocr", lambda page, words: "")
    with pytest.raises(pdf_text.NoReadableTextError):
        pdf_text.read_pages(path)


@pytest.mark.parametrize("counter", ["Strona nr 1 z 1", "Strona numer 1 z 1", "Page number 1 of 1"])
def test_extended_page_counter_after_ocr_is_unreadable_but_a_short_phrase_is_readable(tmp_path, counter):
    attempted = []
    pdf = tmp_path / "scan.pdf"
    image = Image.new("RGB", (1000, 320), "white")
    font = ImageFont.load_default(size=48)
    ImageDraw.Draw(image).text((45, 40), "Niewyrazny dokument", font=font, fill="black")
    image = image.filter(ImageFilter.GaussianBlur(30))
    ImageDraw.Draw(image).text((60, 215), counter, font=font, fill="black")
    image.save(pdf, resolution=150)
    with pytest.raises(pdf_text.NoReadableTextError, match="no readable text after OCR"):
        pdf_text.read_pages(pdf, engine="tesseract", ocr_pages=attempted)
    assert attempted == [1]
    scan(pdf, "Sala obrad 42")
    assert pdf_text.read_pages(pdf, engine="tesseract") == ["Sala obrad 42"]


def test_numeric_transcript_alone_does_not_establish_readability(tmp_path):
    path = tmp_path / "identifier.pdf"
    scan(path, "2026112107046839")
    with pytest.raises(pdf_text.NoReadableTextError):
        pdf_text.read_pages(path, engine="tesseract")


@pytest.mark.parametrize(
    "footer",
    [
        "Strona nr 1z 1",
        "Blatt Nr. 4/9",
        "Leaf No. 3",
        "Feuillet n° 3 sur 7",
        "12 / 45",
        "— 23 —",
        "1 / 3 — numbered leaves",
        "Numer strony 2/5",
        "1 of 3 pages",
        "Strona numer 8",
        "7 No. Blatt",
    ],
)
def test_footer_and_one_word_of_ocr_noise_do_not_establish_readability(tmp_path, monkeypatch, footer):
    path = tmp_path / "faint.pdf"
    scan(path, "Kontrola zalacznikow", blur=15)
    monkeypatch.setattr(pdf_text, "_ocr", lambda page, words: "szum\n" + footer)
    with pytest.raises(pdf_text.NoReadableTextError):
        pdf_text.read_pages(path)


@pytest.mark.parametrize(
    "statement",
    [
        "Faktura VAT 123",
        "Limit dni 10",
        "Faktura 12 VAT 123",
        "Faktura VAT 12/2025",
        "Faktura numer 12/2025",
        "Invoice number 123",
        "Godziny pracy 8–16",
        "Kwota netto 1-2",
    ],
)
def test_two_word_numeric_statement_is_readable(tmp_path, statement):
    path = tmp_path / "statement.pdf"
    scan(path, statement)
    assert not pdf_text._is_page_counter(statement)
    (transcript,) = pdf_text.read_pages(path, engine="tesseract")
    assert transcript.startswith(statement.split()[0])


def test_readability_checks_later_pages_without_returning_extra_text_or_ocr_boxes(tmp_path):
    path = tmp_path / "late.pdf"
    scan(path, "", "Strona nr 2 z 4", "", "PLAN SALI")
    attempted, words = [], []
    pages = pdf_text.read_pages(path, engine="tesseract", ocr_pages=attempted, word_boxes=words)
    assert len(pages) == 3
    assert attempted == [1, 2, 3]
    assert all(word.page <= 3 for word in words)


def test_three_blank_pages_do_not_hide_later_illegible_page(tmp_path):
    path = tmp_path / "late.pdf"
    scan(path, "", "", "", "Niewyrazny dokument", blur=30)
    with pytest.raises(pdf_text.NoReadableTextError):
        pdf_text.read_pages(path, engine="tesseract")


@pytest.mark.parametrize("placement", ["full", "bordered", "logo", "clipped"])
def test_selectable_footer_over_a_scan_requires_ocr_but_small_visible_images_keep_native_text(tmp_path, placement):
    image_pdf, combined = tmp_path / "image.pdf", tmp_path / "footer.pdf"
    scan(image_pdf, "PLAN SALI")
    with pdfium.PdfDocument(image_pdf) as document:
        page = document[0]
        (image,) = page.get_objects()
        width, height = page.get_size()
        if placement == "logo":
            image.set_matrix(pdfium.PdfMatrix().scale(16, 16))
        elif placement == "bordered":
            image.set_matrix(pdfium.PdfMatrix().scale(0.75 * width, 0.75 * height).translate(width / 8, height / 8))
        elif placement == "clipped":
            image.set_matrix(pdfium.PdfMatrix().scale(width, height).translate(width - 16, height - 16))
        text = "Strona nr 1 z 1"
        footer = pdfium.raw.FPDFPageObj_NewTextObj(document, b"Helvetica", 9)
        assert pdfium.raw.FPDFText_SetCharcodes(footer, (ctypes.c_uint * len(text))(*map(ord, text)), len(text))
        pdfium.raw.FPDFPageObj_Transform(footer, 1, 0, 0, 1, 30, 6)
        pdfium.raw.FPDFPage_InsertObject(page, footer)
        page.gen_content()
        document.save(combined)
    attempted = []
    (transcript,) = pdf_text.read_pages(combined, engine="tesseract", ocr_pages=attempted)
    if placement in {"logo", "clipped"}:
        assert attempted == [] and transcript == text
    else:
        assert attempted == [1] and "PLAN SALI" in transcript


def test_readable_words_can_span_two_scanned_pages(tmp_path):
    path = tmp_path / "plan.pdf"
    scan(path, "PLAN", "SALI")
    assert pdf_text.read_pages(path, engine="tesseract") == ["PLAN", "SALI"]


def test_joined_lines_keep_source_page_numbers_through_repeated_headers_and_footers():
    pages = ["Nagłówek\nA\n\nStrona 1 z 2", "Nagłówek\nB\nStrona 2 z 2"]
    assert list(pdf_text.iter_page_lines(pages)) == [(1, "Nagłówek"), (1, "A"), (1, ""), (2, "B")]
    assert pdf_text.join_pages(pages) == "Nagłówek\nA\n\nB"


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
    seen.clear()
    monkeypatch.delenv("KIO_OCR_ENGINE")
    assert pdf_text.read_pages(path) == ["PLAN SALI"]
    assert seen == ["image", 300]


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
        "        return SimpleNamespace(txts=['Model testowy ' + str(os.getpid())], word_results=[])\n"
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
