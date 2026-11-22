from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import tesserocr
from PIL import Image

from kio2json import ocr_budget, pdf_text, rapid_worker


@pytest.mark.parametrize("outcome", ["success", "second timeout", "immediate error", "expired budget"])
def test_tesseract_primary_retry(outcome, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(pdf_text, "monotonic", lambda: now[0])
    monkeypatch.setattr(ocr_budget, "monotonic", lambda: now[0])
    calls = []
    item = Mock()
    item.BoundingBox.return_value = (3, 6, 9, 12)
    item.GetUTF8Text.return_value = "word"
    monkeypatch.setattr(tesserocr, "iterate_level", lambda *_: [item])
    monkeypatch.setattr(pdf_text, "_language_dir", lambda: "")

    def api(**kwargs):
        reader = Mock()
        reader.GetUTF8Text.return_value = "word"

        def recognize(*, timeout):
            calls.append(
                (reader.SetImage.call_args.args[0].size, reader.SetSourceResolution.call_args.args[0], timeout)
            )
            if outcome == "immediate error":
                return False
            if len(calls) == 1 or outcome == "second timeout":
                now[0] += timeout / 1000
                return False
            return True

        reader.Recognize.side_effect = recognize
        return nullcontext(reader)

    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", api)
    # Three pixels per PDF point at the initial resolution.
    raster = pdf_text._Raster(Image.new("L", (60, 120)), (10, 20, 30, 60), 3, 2)
    boxes = []
    deadline = 1 if outcome == "expired budget" else 185
    with ocr_budget.document_budget(deadline):
        if outcome == "success":
            assert pdf_text._tesseract(raster, boxes, explicit_dpi=True) == "word"
            assert boxes == [pdf_text.WordBox(2, "word", 12, 24, 16, 28)]
        else:
            with pytest.raises(pdf_text.OCRRecognitionError):
                pdf_text._tesseract(raster, boxes, explicit_dpi=True)
            assert not boxes
    expected = [((60, 120), 300, 180_000)]
    if outcome in ("success", "second timeout"):
        expected.append(((30, 60), 150, 5000))
    assert calls == expected


def test_required_rapidocr_retries_once_at_lower_resolution(monkeypatch, tmp_path):
    read = Mock(side_effect=[TimeoutError, ("ok", [(1, "ok", 2, 3, 4, 5)])])
    monkeypatch.setattr(rapid_worker, "recognize", read)
    path = tmp_path / "scan.pdf"
    page = SimpleNamespace(pdf=SimpleNamespace(path=path), page_number=1)
    boxes = []
    assert pdf_text._ocr(page, boxes, engine="rapidocr") == "ok"
    assert boxes == [pdf_text.WordBox(1, "ok", 2, 3, 4, 5)]
    assert read.call_count == 2
    assert read.call_args_list[0].args == (path, 1, True, 180)
    assert read.call_args_list[1].kwargs == {"dpi": 150}
