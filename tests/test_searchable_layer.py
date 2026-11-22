"""Verify a searchable scan against its pixels while retaining the rest of its native layer."""

from io import BytesIO

import pdfplumber
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from kio2json import pdf_text

SIZE = (480, 360)
ACCOUNT = "71932700000000000000000027"
NIP = "5260250274"


def searchable_scan(path, printed, hidden):
    source = BytesIO()
    canvas = Canvas(source, pagesize=SIZE)
    for y, text in printed:
        canvas.setFont("Helvetica", 14)
        canvas.drawString(24, y, text)
    canvas.save()
    with pdfplumber.open(source) as pdf:
        image = pdf.pages[0].to_image(resolution=200).original
    canvas = Canvas(str(path), pagesize=SIZE)
    canvas.drawImage(ImageReader(image), 0, 0, *SIZE)
    for y, text in hidden:
        layer = canvas.beginText(24, y)
        layer.setTextRenderMode(3)
        layer.setFont("Helvetica", 14)
        layer.textLine(text)
        canvas.drawText(layer)
    canvas.save()
    return path


def test_searchable_scan_repairs_identifiers_without_replacing_other_native_fields(tmp_path):
    rows = [(290, "Zestawienie dokumentu"), (250, f"Numer konta: {ACCOUNT}"), (210, f"NIP: {NIP}"), (170, "Ref: 10A")]
    hidden = [
        rows[0],
        (250, "Numer konta: " + ACCOUNT[:10] + ACCOUNT[11:]),
        (210, "NIP: " + NIP[:-1]),
        (170, "Ref: 1OA"),
    ]
    path = searchable_scan(tmp_path / "receipt.pdf", rows, hidden)
    boxes, recognized = [], []
    (text,) = pdf_text.read_pages(path, word_boxes=boxes, ocr_pages=recognized)
    assert text.splitlines() == [row for _, row in [*rows[:3], hidden[3]]]
    assert [word.text for word in boxes] == text.split()
    assert recognized == []


def test_list_marker_is_recovered_only_from_the_matching_printed_item(tmp_path):
    rows = [(300, "Wykaz czynnosci"), (260, "1) Wybor wykonawcy"), (220, "2) Ocena terminu")]
    hidden = [rows[0], (260, "2) Wybor wykonawcy"), rows[2]]
    path = searchable_scan(tmp_path / "items.pdf", rows, hidden)
    assert pdf_text.read_pages(path)[0].splitlines() == [row for _, row in rows]


def test_misplaced_searchable_line_returns_to_its_printed_section(tmp_path):
    rows = [(300, "Dane wykonawcy"), (262, "Studio Mechaniki"), (217, "Dane odbiorcy"), (171, "Mosty i Drogi")]
    hidden = [rows[0], (135, rows[1][1]), *rows[2:]]
    path = searchable_scan(tmp_path / "shifted.pdf", rows, hidden)
    boxes = []
    assert pdf_text.read_pages(path, word_boxes=boxes)[0].splitlines() == [row for _, row in rows]
    assert next(box for box in boxes if box.text == "Studio").y0 < next(box for box in boxes if box.text == "Mosty").y0


def test_optional_timeout_preserves_native_text_and_geometry(tmp_path, monkeypatch):
    rows = [(290, "Dane podmiotu"), (240, "NIP: " + NIP[:-1])]
    path = searchable_scan(tmp_path / "timeout.pdf", rows, rows)
    calls = []

    def timeout(page, words, **options):
        calls.append(options)
        raise pdf_text.RereadExpired

    monkeypatch.setattr(pdf_text, "_ocr", timeout)
    boxes = []
    assert pdf_text.read_pages(path, word_boxes=boxes)[0].splitlines() == [row for _, row in rows]
    assert [word.text for word in boxes] == " ".join(row for _, row in rows).split()
    assert len(calls) == 1 and calls[0]["reread"]


def test_correct_native_or_aligned_searchable_identifiers_skip_ocr(tmp_path, monkeypatch):
    rows = [(290, f"Numer konta: {ACCOUNT}"), (240, f"NIP: {NIP}")]
    path = searchable_scan(tmp_path / "intact.pdf", rows, rows)
    monkeypatch.setattr(pdf_text, "_ocr", lambda *a, **kw: pytest.fail("intact layer triggered OCR"))
    assert pdf_text.read_pages(path)[0].splitlines() == [row for _, row in rows]


def test_hierarchical_item_uses_the_preceding_sibling_of_the_next_item(tmp_path):
    rows = [
        (308, "Wykaz czynnosci"),
        (264, "3.1. Kontrola wyniku"),
        (224, "3.2. Ocena dokumentu"),
        (178, "4.1. Kontrola terminu"),
    ]
    path = searchable_scan(tmp_path / "hierarchy.pdf", rows, [rows[0], (264, "4.1. Kontrola wyniku"), *rows[2:]])
    assert pdf_text.read_pages(path)[0].splitlines() == [row for _, row in rows]


def test_line_shifted_onto_another_baseline_uses_both_printed_rows(tmp_path):
    rows = [
        (310, "Nadawca przelewu"),
        (275, "Studio Projektowe " + ACCOUNT),
        (230, "Odbiorca przelewu"),
        (191, "Kolej Miejska"),
        (157, "Adres do korespondencji"),
    ]
    hidden = [rows[0], (159, rows[1][1]), *rows[2:]]
    path = searchable_scan(tmp_path / "overprint.pdf", rows, hidden)
    assert pdf_text.read_pages(path)[0].splitlines() == [row for _, row in rows]


def test_displaced_digits_only_row_returns_to_its_printed_role(tmp_path):
    rows = [(310, "Nadawca przelewu"), (275, ACCOUNT), (230, "Odbiorca przelewu"), (190, "Kolej Miejska")]
    path = searchable_scan(tmp_path / "number.pdf", rows, [rows[0], (110, ACCOUNT), *rows[2:]])
    assert pdf_text.read_pages(path)[0].splitlines() == [row for _, row in rows]


def test_truncated_account_can_recover_a_legible_invalid_printed_number(tmp_path, monkeypatch):
    from kio2json import ocr_choices

    # Verify the image evidence independently of time spent loading Tesseract on a busy host.
    monkeypatch.setattr(ocr_choices, "monotonic", lambda: 0.0)

    # Synthetic bank documents can print a structurally complete, checksum-invalid number.
    printed = "PL" + ACCOUNT[:-1] + "8"
    rows = [(290, "Rachunek nadawcy"), (250, printed)]
    path = searchable_scan(tmp_path / "source-number.pdf", rows, [rows[0], (250, printed[:-1])])
    boxes = []
    assert pdf_text.read_pages(path, word_boxes=boxes)[0].splitlines() == [row for _, row in rows]
    assert boxes[-1].text == printed


def test_complete_invalid_number_cannot_be_overwritten_by_a_different_invalid_number(tmp_path):
    printed = "PL" + ACCOUNT[:-1] + "8"
    hidden = "PL" + ACCOUNT[:-1] + "9"
    rows = [(290, "Rachunek nadawcy"), (250, printed)]
    path = searchable_scan(tmp_path / "substitution.pdf", rows, [rows[0], (250, hidden)])
    assert pdf_text.read_pages(path)[0].splitlines() == [rows[0][1], hidden]
