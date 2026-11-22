"""Deskew right-angle scans while keeping PDF word coordinates in the rendered page frame."""

import pytest
from PIL import Image, ImageDraw, ImageFont

from kio2json import pdf_text


def printed_page():
    image = Image.new("L", (1080, 1400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=34)
    heading = draw.textbbox((160, 130), "ARCHIWUM", font=font)
    draw.text((160, 130), "ARCHIWUM", font=font, fill=0)
    for i, line in enumerate(
        (
            "Dokument zawiera opis procesu i wyniki badania.",
            "Pierwsza strona zawiera informacje ogólne.",
            "W kolejnym rozdziale omówiono szczegóły.",
            "Podsumowanie przedstawia przebieg spotkania.",
            "W piątek zespół przygotuje raport końcowy.",
        )
    ):
        draw.text((120, 320 + 66 * i), line, font=font, fill=0)
    return image, heading


@pytest.mark.parametrize("osd_available", [True, False], ids=["installed", "portable"])
@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_rotated_scan_preserves_text_and_physical_word_boxes(angle, osd_available, monkeypatch):
    image, heading = printed_page()
    if not osd_available:
        from kio2json import ocr_orientation

        monkeypatch.setattr(ocr_orientation, "_osd_directory", lambda: None)
    mark = Image.new("L", image.size)
    ImageDraw.Draw(mark).rectangle(heading, fill=255)
    incoming = image.rotate(angle, expand=True)
    expected = mark.rotate(angle, expand=True).getbbox()
    boxes = []
    raster = pdf_text._Raster(incoming, (7, 13, 7 + incoming.width / 2, 13 + incoming.height / 2), 2, 4)
    text = pdf_text._tesseract(raster, boxes, explicit_dpi=True)
    assert "ARCHIWUM" in text and "Dokument zawiera" in text
    word = next(w for w in boxes if w.text == "ARCHIWUM")
    assert word.page == 4
    assert word[2:] == pytest.approx(tuple(v / 2 + (7 if i % 2 == 0 else 13) for i, v in enumerate(expected)), abs=3)
    if angle:
        assert word.layout_box[2:] == pytest.approx(tuple(v / 2 for v in heading), abs=3)
        assert word.upright_page_size == (540, 700)
    else:
        assert word.layout_box is word


def test_required_portable_orientation_survives_expired_optional_budget(monkeypatch):
    from kio2json import ocr_orientation
    from kio2json.ocr_budget import document_budget

    monkeypatch.setattr(ocr_orientation, "_osd_directory", lambda: None)
    image, _ = printed_page()
    image = image.transpose(Image.Transpose.ROTATE_180)
    raster = pdf_text._Raster(image, (0, 0, *image.size), 1, 1)
    with document_budget(0):
        assert "ARCHIWUM" in pdf_text._tesseract(raster, None, explicit_dpi=True)


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_rotated_receipt_keeps_detached_amount_and_date(tmp_path, angle):
    from kio2json.pipeline import process_pdf
    from kio2json.receipt_layout import receipt_cell_fields

    page = Image.new("L", (1200, 1300), "white")
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=32)
    for x, y, text in (
        (90, 100, "Potwierdzenie realizacji przelewu"),
        (90, 220, "Z rachunku: 78351200009981234567890123"),
        (90, 275, "Na rachunek: 56458700991234567801234567"),
        (90, 330, "Numer transakcji: MV834721"),
        (90, 385, "Tytul: Dostawa papieru dla biura"),
        (90, 530, "Kwota"),
        (620, 530, "Data operacji"),
        (90, 575, "91,42 PLN"),
        (620, 575, "21.04.2026"),
    ):
        draw.text((x, y), text, font=font, fill=0)
    path = tmp_path / "receipt.pdf"
    page.rotate(angle, expand=True).save(path, resolution=200)
    words = []
    pdf_text.read_pages(path, word_boxes=words)
    cells = receipt_cell_fields(words, ocr=True)
    assert cells.get("Kwota") == "91,42 PLN" and cells.get("Data operacji") == "21.04.2026"
    kind, doc = process_pdf(path)
    assert kind == "bank_transfer"
    assert doc["przelew_bankowy"]["kwota"] == 91.42
    assert doc["przelew_bankowy"]["data_operacji"] == "2026-04-21"
