"""Deskew right-angle scans while keeping PDF word coordinates in the rendered page frame."""

from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw, ImageFont

from kio2json import ocr_orientation, pdf_text


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


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_admitted_rotation_preserves_physical_and_logical_word_boxes(angle, monkeypatch):
    image, heading = printed_page()
    # Geometry must work for every admitted direction independently of a
    # particular Tesseract build's ability to read some sideways inputs.
    monkeypatch.setattr(pdf_text, "correction_angle", lambda *args: -angle % 360)
    monkeypatch.setattr(pdf_text, "rotation_improves_text", lambda *args: True)
    mark = Image.new("L", image.size)
    ImageDraw.Draw(mark).rectangle(heading, fill=255)
    incoming = image.rotate(angle, expand=True)
    expected = mark.rotate(angle, expand=True).getbbox()
    boxes = []
    raster = pdf_text._Raster(incoming, (7, 13, 7 + incoming.width / 2, 13 + incoming.height / 2), 2, 4, True)
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


@pytest.mark.parametrize(
    "case", ["missing", "weak", "wrong", "first_probe_timeout", "candidate_timeout", "rejected_layer"]
)
def test_unconfirmed_rotation_retains_exact_upright_reading(monkeypatch, case):
    import tesserocr

    image, _ = printed_page()
    # On the original regression the first orientation probe timed out on
    # genuinely upright ink. No speculative result may replace that reading.
    if case in {"missing", "weak", "rejected_layer"}:
        image = image.transpose(Image.Transpose.ROTATE_180)
    raster = pdf_text._Raster(image, (7, 13, 7 + image.width, 13 + image.height), 1, 4)
    expected = []
    upright = pdf_text._tesseract(raster, expected, explicit_dpi=True)
    real_api = tesserocr.PyTessBaseAPI
    detector = Mock()
    detector.DetectOrientationScript.return_value = {"orient_deg": 180, "orient_conf": 14.9 if case == "weak" else 20}
    if case == "first_probe_timeout":
        detector.DetectOrientationScript.side_effect = TimeoutError("first orientation probe timed out")
    monkeypatch.setattr(ocr_orientation, "_osd_directory", lambda: None if case == "missing" else "osd")

    def api(**kwargs):
        return nullcontext(detector) if kwargs["lang"] == "osd" else real_api(**kwargs)

    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", api)
    recognize = pdf_text._recognize_raster

    def read(raster, words, **kwargs):
        if kwargs.get("angle") and case == "candidate_timeout":
            words.append(pdf_text.WordBox(4, "partial", 0, 0, 10, 10))
            raise pdf_text.RereadExpired
        return recognize(raster, words, **kwargs)

    monkeypatch.setattr(pdf_text, "_recognize_raster", read)
    words = []
    text = pdf_text._tesseract(raster._replace(orientation_eligible=case != "rejected_layer"), words, explicit_dpi=True)
    assert (text, words) == (upright, expected)
    assert [w.confidence for w in words] == [w.confidence for w in expected]
    assert all(w.layout_box is w for w in words)
    if case in {"missing", "rejected_layer"}:
        detector.SetImage.assert_not_called()
    else:
        detector.SetImage.assert_called_once_with(image)
        detector.DetectOrientationScript.assert_called_once()


def test_high_osd_confidence_and_polish_word_gain_admit_rotation():
    from evals.document_variants.pdfkit import FONT_DIR

    if not ocr_orientation._osd_directory():
        pytest.skip("real OSD data is optional on the deployment host")
    page = Image.new("L", (1440, 1000), "white")
    draw = ImageDraw.Draw(page)
    font = ImageFont.truetype(FONT_DIR / "DejaVuSerif.ttf", 32)
    lines = (
        "W sprawie przedstawiono stanowisko oraz uzasadnienie dotyczące zakupu.",
        "Przygotowanie szczegółowego zamówienia wymaga opisania okoliczności.",
        "Podstawą rozstrzygnięcia będzie harmonogram prac zespołu ludzi.",
        "Biuro prowadziło rozmowy dotyczące wydania dokumentu do akt.",
        "Instytucja powinna potwierdzić otrzymanie złożonych wniosków.",
    )
    for i in range(6):
        draw.text((90, 60 + i * 57), lines[i % len(lines)], font=font, fill=0)
    image = page.transpose(Image.Transpose.ROTATE_180)
    words = []
    raster = pdf_text._Raster(image, (0, 0, *image.size), 1, 1, True)
    assert "W sprawie przedstawiono stanowisko" in pdf_text._tesseract(raster, words, explicit_dpi=True)
    assert all(w.layout_box is not w for w in words)


def test_only_scans_with_absent_or_garbled_layers_allow_rotation(tmp_path):
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / "layers.pdf"
    page = Canvas(str(path), pagesize=(250, 320))
    image, _ = printed_page()
    for cover, layer in (
        ("full", ""),
        ("full", "Widoczny tekst"),
        ("full", "ab1cd ef2gh ij3kl"),
        ("strips", ""),
        ("none", ""),
    ):
        if cover == "full":
            page.drawImage(ImageReader(image), 0, 0, 250, 320)
        elif cover == "strips":
            for y in (60, 120, 180):
                page.drawImage(ImageReader(image), 20, y, 200, 55)
        else:
            page.line(0, 100, 200, 100)
        if layer:
            text = page.beginText(10, 280)
            text.setTextRenderMode(3)
            text.textLine(layer)
            page.drawText(text)
        page.showPage()
    page.save()
    with pdf_text.pdfplumber.open(path) as doc:
        assert [pdf_text._render(p).orientation_eligible for p in doc.pages] == [True, False, True, True, False]


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_admitted_rotation_keeps_detached_receipt_amount_and_date(tmp_path, angle, monkeypatch):
    from kio2json.pipeline import process_pdf
    from kio2json.receipt_layout import receipt_cell_fields

    monkeypatch.setattr(pdf_text, "correction_angle", lambda *args: -angle % 360)
    monkeypatch.setattr(pdf_text, "rotation_improves_text", lambda *args: True)
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
