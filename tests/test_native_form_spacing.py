"""PDF text and layout readers should agree on physical gaps between field labels and values."""

import pytest
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from kio2json.pdf_text import read_pages


@pytest.mark.parametrize("gap", [0, 2.4])
def test_small_printed_gaps_separate_form_fields_and_preserve_solid_identifiers(tmp_path, gap):
    pdf = tmp_path / "card.pdf"
    canvas = Canvas(str(pdf))
    canvas.setFont("Helvetica", 10)
    canvas.drawString(45, 720, "Dane strony")
    for y, tokens in [(700, ["NIP", "1234567890", "REGON", "123456789"]), (680, ["adw.", "Iga", "Morska"])]:
        x = 45
        for token in tokens:
            canvas.drawString(x, y, token)
            x += stringWidth(token, "Helvetica", 10) + gap
    canvas.save()
    boxes = []
    (text,) = read_pages(pdf, word_boxes=boxes)
    expected = ["NIP", "1234567890", "REGON", "123456789"] if gap else ["NIP1234567890REGON123456789"]
    assert " ".join(expected) in text
    assert [box.text for box in boxes if "NIP" in box.text or "REGON" in box.text or box.text.isdecimal()] == expected
    assert ("adw. Iga Morska" if gap else "adw.IgaMorska") in text


def test_gap_inside_register_word_does_not_validate_the_page_spacing(tmp_path):
    pdf = tmp_path / "tracking.pdf"
    canvas = Canvas(str(pdf))
    canvas.setFont("Helvetica", 10)
    canvas.drawString(45, 720, "Dane strony")
    canvas.drawString(45, 700, "NI")
    canvas.drawString(45 + stringWidth("NI", "Helvetica", 10) + 2.4, 700, "P1234567890")
    canvas.save()
    (text,) = read_pages(pdf)
    assert "NIP1234567890" in text
