"""Retained scanned pages can share wall time while preserving the ordered document read."""

from threading import Barrier, get_ident

import pytest
from PIL import Image, ImageDraw, ImageFont

from kio2json import pdf_text


def make_scan(path):
    images = []
    for text in ("PLAN SALI", "KARTA PRACY", "DRUGA CZESC"):
        image = Image.new("RGB", (900, 220), "white")
        ImageDraw.Draw(image).text((30, 40), text, font=ImageFont.load_default(size=48), fill="black")
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=150)


@pytest.mark.parametrize("engine", ["tesseract-dpi", "tesseract"])
def test_parallel_matches_serial_ocr_and_word_coordinates(tmp_path, monkeypatch, engine):
    path = tmp_path / "pages.pdf"
    make_scan(path)

    def read():
        provenance, boxes = [], []
        text = pdf_text.read_pages(path, engine=engine, ocr_pages=provenance, word_boxes=boxes)
        return text, provenance, boxes

    parallel = read()
    assert parallel[1] == [1, 2, 3] and all(parallel[0]) and parallel[2]
    monkeypatch.setattr(pdf_text, "MAX_PARALLEL_PIXELS", 1)
    monkeypatch.setattr(pdf_text, "_recognize_batch", lambda *a, **kw: pytest.fail("images exceed batch pixel budget"))
    assert read() == parallel


@pytest.mark.parametrize("failure", [None, "render", "recognition"])
def test_ordered_ocr_provenance_and_mixed_page_read(tmp_path, monkeypatch, failure):
    path = tmp_path / "mixed.pdf"
    make_scan(path)
    main_thread = get_ident()
    render = pdf_text._render
    # Two workers must start independently. The render-failure case has only one worker.
    rendezvous = Barrier(2)

    def layer(page):
        assert get_ident() == main_thread
        return "Native body" if page.page_number == 2 else ""

    def render_page(page):
        assert get_ident() == main_thread
        if failure == "render" and page.page_number == 3:
            raise RuntimeError("render failed")
        return render(page)

    def recognize(image, boxes, *, explicit_dpi):
        assert get_ident() != main_thread and explicit_dpi
        if failure != "render":
            rendezvous.wait(timeout=5)
        if failure == "recognition" and image.page_number == 3:
            raise pdf_text.OCRRecognitionError("recognition failed")
        name = f"sheet {image.page_number}"
        boxes.append(pdf_text.WordBox(image.page_number, name, 1, 2, 3, 4))
        return name

    monkeypatch.setattr(pdf_text.pdfplumber.page.Page, "extract_text", layer)
    monkeypatch.setattr(pdf_text, "_render", render_page)
    monkeypatch.setattr(pdf_text, "_tesseract", recognize)
    provenance, boxes = [], []

    def read():
        return pdf_text.read_pages(path, engine="tesseract-dpi", ocr_pages=provenance, ocr_word_boxes=boxes)

    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            read()
        assert boxes == []
    else:
        assert read() == ["sheet 1", "Native body", "sheet 3"]
        assert [box.page for box in boxes] == [1, 3]
    assert provenance == [1, 3]


def test_later_text_layer_error_preserves_first_page_ocr_provenance(tmp_path, monkeypatch):
    path = tmp_path / "damaged.pdf"
    make_scan(path)

    def layer(page):
        if page.page_number == 2:
            raise ValueError("unreadable text layer")
        return ""

    monkeypatch.setattr(pdf_text.pdfplumber.page.Page, "extract_text", layer)
    monkeypatch.setattr(pdf_text, "_ocr", lambda *a, **kw: "Readable sheet")
    provenance = []
    with pytest.raises(ValueError, match="unreadable text layer"):
        pdf_text.read_pages(path, ocr_pages=provenance)
    assert provenance == [1]
