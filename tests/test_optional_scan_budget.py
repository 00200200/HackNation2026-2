from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import tesserocr
from PIL import Image

from kio2json import appeal_scan_crops, ocr_budget, ocr_signatures, pdf_text, rapid_worker, receipt_account_crop
from kio2json.pdf_text import WordBox


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(ocr_budget, "REREAD_DEADLINE_SECONDS", 27)
    now = [0.0]
    monkeypatch.setattr(ocr_budget, "monotonic", lambda: now[0])
    return now


def test_primary_workers_share_the_crop_deadline(monkeypatch, clock):
    monkeypatch.setattr(pdf_text, "_render", lambda page: page)
    monkeypatch.setattr(pdf_text, "_tesseract", lambda *args, **kwargs: ocr_budget.remaining_ms(1000))
    with ocr_budget.document_budget():
        clock[0] = 26.75
        jobs = pdf_text._recognize_batch(
            [SimpleNamespace(page_number=i) for i in (1, 2)], explicit_dpi=True, with_boxes=False
        )
        assert [job.result() for job, _ in jobs.values()] == [250, 250]


def test_reread_checks_budget_before_render_and_after_it(monkeypatch, clock, tmp_path):
    render = Mock()
    monkeypatch.setattr(pdf_text, "_render", render)
    unavailable = Mock(side_effect=AssertionError("expired reread reached the backend"))
    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", unavailable)
    monkeypatch.setattr(pdf_text.pdfplumber, "open", unavailable)
    with ocr_budget.document_budget():
        clock[0] = 27.0
        with pytest.raises(ocr_budget.RereadExpired):
            pdf_text.read_pages(tmp_path / "scan.pdf", repair_image_text=True, reread=True)
        with pytest.raises(ocr_budget.RereadExpired):
            pdf_text._ocr(None, None, engine="tesseract-dpi", reread=True)
        render.assert_not_called()

    def render_and_expire(page):
        clock[0] += 0.25
        return Mock()

    render.side_effect = render_and_expire
    with ocr_budget.document_budget():
        clock[0] += 26.75
        with pytest.raises(ocr_budget.RereadExpired):
            pdf_text._ocr(None, None, engine="tesseract-dpi", reread=True)
    render.assert_called_once()
    unavailable.assert_not_called()


def test_full_page_tesseract_only_clips_optional_rereads(monkeypatch, clock):
    reader = Mock()
    reader.GetUTF8Text.return_value = ""
    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", lambda **kwargs: nullcontext(reader))
    monkeypatch.setattr(pdf_text, "_language_dir", lambda: "")
    with ocr_budget.document_budget():
        clock[0] += 26.75
        pdf_text._tesseract(
            pdf_text._Raster(Image.new("L", (20, 40)), (0, 0, 20, 40), 1, 1), None, explicit_dpi=True, reread=True
        )
        reader.Recognize.assert_called_once_with(timeout=250)
        clock[0] += 1
        pdf_text._tesseract(pdf_text._Raster(Image.new("L", (20, 40)), (0, 0, 20, 40), 1, 1), None, explicit_dpi=True)
        reader.Recognize.assert_called_with(timeout=1000 * pdf_text.OCR_TIMEOUT_SECONDS)


def test_account_crop_rechecks_timeout_between_variants(monkeypatch, tmp_path, clock):
    frame = Mock(scale=1, bbox=(0, 0, 50, 50))
    page = Mock()
    page.to_image.return_value = frame
    monkeypatch.setattr(receipt_account_crop.pdfplumber, "open", lambda _: nullcontext(SimpleNamespace(pages=[page])))
    reader = Mock()
    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", lambda **kwargs: nullcontext(reader))
    monkeypatch.setattr(receipt_account_crop, "_language_dir", lambda: "")

    def recognize(*, timeout):
        assert timeout == 125
        clock[0] += 0.125
        return False

    reader.Recognize.side_effect = recognize
    text = "Na rachunek: 06 1987 6543 1234 5678 0000 3453"
    boxes = [WordBox(1, word, i * 10, 0, i * 10 + 9, 8) for i, word in enumerate(text.split())]
    pages = [text]
    with ocr_budget.document_budget():
        clock[0] += 26.875
        assert receipt_account_crop.recover_account_crops(tmp_path / "receipt.pdf", pages, boxes) is pages
    reader.Recognize.assert_called_once()


def test_expired_cover_check_skips_render_and_board_stamp_caps_rapidocr(monkeypatch, tmp_path, clock):
    unavailable = Mock(side_effect=AssertionError("expired crop opened the PDF"))
    monkeypatch.setattr(appeal_scan_crops.pdfplumber, "open", unavailable)
    recognize = Mock(return_value=("", []))
    monkeypatch.setattr(rapid_worker, "recognize", recognize)
    record = {"mocodawca": [{"podpisujacy": [], "data": {"typ": "osoba_prawna", "nazwa": "Firma"}}], "pelnomocnicy": []}
    page = "Firma udziela pełnomocnictwa.\nDo reprezentowania w postępowaniu."
    path = tmp_path / "grant.pdf"
    with ocr_budget.document_budget():
        clock[0] += 26.875
        ocr_signatures.recover_board_stamp(path, record, page)
        clock[0] += 0.125
        ocr_signatures.recover_board_stamp(path, record, page)
        appeal_scan_crops.verify_cover({}, "", [WordBox(1, "A", 0, 0, 1, 1)], path)
    recognize.assert_called_once_with(path, 1, "lines", timeout=0.125)
    unavailable.assert_not_called()


def test_full_rapidocr_watchdog_preserves_primary_and_caches_missing_alternate(monkeypatch, tmp_path):
    from kio2json.model_pages import AlternateOCR

    recognize = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(rapid_worker, "recognize", recognize)
    path = tmp_path / "scan.pdf"
    page = SimpleNamespace(pdf=SimpleNamespace(path=path), page_number=1)
    with ocr_budget.document_budget():
        alternate = AlternateOCR(path, [1])
        assert alternate.read(1) == alternate.read(1) == ""
        recognize.assert_called_once()
        with pytest.raises(ocr_budget.RereadExpired):
            pdf_text._ocr(page, None, engine="rapidocr", reread=True)
        with pytest.raises(TimeoutError):
            pdf_text._ocr(page, None, engine="rapidocr")


def test_optional_tesseract_page_watchdog_preserves_primary_before_document_expires(monkeypatch, clock):
    reader = Mock()
    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", lambda **kwargs: nullcontext(reader))
    monkeypatch.setattr(pdf_text, "_language_dir", lambda: "")
    monkeypatch.setattr(pdf_text, "REREAD_PAGE_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(pdf_text, "monotonic", lambda: clock[0])

    def expire(*, timeout):
        clock[0] += timeout / 1000
        return False

    reader.Recognize.side_effect = expire
    with ocr_budget.document_budget(), pytest.raises(ocr_budget.RereadExpired):
        pdf_text._tesseract(
            pdf_text._Raster(Image.new("L", (20, 40)), (0, 0, 20, 40), 1, 1), None, explicit_dpi=True, reread=True
        )
