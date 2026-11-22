"""Receipt cards use only the value printed beside or beneath each caption."""

import pytest
from reportlab.pdfgen.canvas import Canvas

from evals.variant_pages import polish_font
from kio2json.pdf_text import WordBox
from kio2json.pipeline import process_pdf


@pytest.mark.parametrize("swap", [False, True])
def test_routed_cards_keep_the_complete_purpose_and_exclude_print_date_and_fee(tmp_path, swap):
    path = tmp_path / "payment.pdf"
    pdf = Canvas(str(path))
    pdf.setFont(polish_font("Helvetica"), 10)
    left, right = (300, 40) if swap else (40, 300)
    for x, y, line in [
        (40, 790, "Potwierdzenie przelewu"),
        (left, 750, "Termin realizacji"),
        (left, 734, "12.04.2031"),
        (left, 710, "Kwota obciążenia"),
        (left, 694, "718,52 PLN"),
        (left, 670, "Data wydruku"),
        (left, 654, "15.04.2031"),
        (left, 630, "Prowizja"),
        (left, 614, "8,11 PLN"),
        (right, 750, "Opis płatności"),
        (right, 734, "Zwrot za elementy"),
        (right, 719, "zamienne, ref. L/418"),
        (right, 704, "do zamówienia"),
        (right, 675, "Numer transakcji"),
        (right, 659, "RX-73610"),
        (40, 570, "Z rachunku: 45109010140000071219812874"),
        (40, 546, "Na rachunek: 70114020040000310202177412"),
    ]:
        pdf.drawString(x, y, line)
    pdf.save()
    kind, record = process_pdf(path)
    assert kind == "bank_transfer"
    fields = record["przelew_bankowy"]
    assert fields["data_operacji"] == "2031-04-12"
    assert fields["kwota"] == 718.52
    assert fields["tytul"] == "Zwrot za elementy zamienne, ref. L/418 do zamówienia"


def read_card(lines, old=None):
    from kio2json.receipt_pairing import apply_receipt_cards

    words = [WordBox(1, line, 20, i * 14, 20 + 5 * len(line), i * 14 + 10) for i, line in enumerate(lines)]
    fields = {"tytul": old, "data_operacji": None, "kwota": None}
    apply_receipt_cards(fields, words)
    return fields


@pytest.mark.parametrize("extra", [["63,14 PLN"], ["Suma przelewu", "63,14 PLN"], ["Suma przelewu", "***"]])
def test_ambiguous_amount_is_not_filled(extra):
    assert read_card(["Suma przelewu", "89,23 PLN", *extra])["kwota"] is None


@pytest.mark.parametrize("value", [[], ["*****"], ["---"]])
def test_missing_purpose_stops_at_the_next_caption(value):
    assert read_card(["Opis operacji", *value, "Data wydruku", "12.08.2032"])["tytul"] is None


def test_replace_only_a_title_explained_by_printed_boundaries():
    lines = ["Opis płatności", "Serwis urządzeń", "nr X/402", "Referencja banku", "U-863"]
    assert read_card(lines, "płatności Serwis urządzeń")["tytul"] == "Serwis urządzeń nr X/402"
    assert read_card(lines, "Serwis urządzeń nr X/402 Referencja banku U-863")["tytul"] == "Serwis urządzeń nr X/402"
    assert read_card(lines, "Wynajem sprzętu")["tytul"] == "Wynajem sprzętu"


def test_aligned_right_hand_values_have_two_independent_caption_anchors():
    from kio2json.receipt_pairing import apply_receipt_cards

    rows = [
        ("Zaksięgowano dnia", "14.05.2032"),
        ("Obciążono rachunek", "221,18 PLN"),
        ("Prowizja", "4,12 PLN"),
        ("Data wydruku", "15.05.2032"),
    ]
    words = [
        WordBox(1, text, x, 20 + 16 * i, x + 5 * len(text), 30 + 16 * i)
        for i, row in enumerate(rows)
        for x, text in zip((20, 220), row, strict=True)
    ]
    fields = {"kwota": None, "data_operacji": None, "tytul": None}
    apply_receipt_cards(fields, words)
    assert fields == {"kwota": 221.18, "data_operacji": "2032-05-14", "tytul": None}


def test_a_typed_value_ends_at_a_new_account_role():
    lines = ["Suma przelewu", "139,53 PLN", "Numer konta adresata", "PL123", "Opis operacji", "Żywica"]
    assert read_card(lines)["kwota"] == 139.53


def test_an_indented_purpose_continuation_cannot_be_discarded():
    from kio2json.receipt_pairing import apply_receipt_cards

    words = [
        WordBox(1, line, x, i * 15, x + len(line) * 5, i * 15 + 10)
        for i, (x, line) in enumerate(
            [(10, "Opis operacji"), (10, "Zakup części"), (26, "serwisowych"), (10, "Nr transakcji"), (10, "R0471")]
        )
    ]
    fields = {"tytul": "Zakup części serwisowych", "kwota": None, "data_operacji": None}
    apply_receipt_cards(fields, words)
    assert fields["tytul"] == "Zakup części serwisowych"


def test_empty_purpose_followed_by_an_ancillary_fee():
    assert read_card(["Opis operacji", "Prowizja dodatkowa", "3,01 PLN", "Data wydruku"])["tytul"] is None


@pytest.mark.parametrize("boundary", ["Prowizja za przelew: 1,01 PLN", "Nazwa banku: Przykład"])
def test_empty_purpose_before_inline_unfamiliar_caption(boundary):
    assert read_card(["Cel płatności", boundary, "Data wydruku: 05.02.2030"])["tytul"] is None


def test_footer_after_a_complete_purpose():
    lines = ["Opis płatności", "Zakup części", "Dokument wygenerowany elektronicznie", "Numer transakcji: A742"]
    assert read_card(lines, "Zakup części")["tytul"] == "Zakup części"


def test_previous_owner_indent_is_not_a_neighbouring_column():
    from kio2json.receipt_pairing import apply_receipt_cards

    rows = [
        (36, "Dane nadawcy"),
        (36, "Spółka"),
        (20, "Tytuł: Zakup sprzętu"),
        (36, "technicznego"),
        (20, "Numer transakcji: A742"),
    ]
    words = [WordBox(1, text, x, i * 14, x + 5 * len(text), i * 14 + 10) for i, (x, text) in enumerate(rows)]
    fields = {"tytul": "Zakup sprzętu technicznego", "kwota": None, "data_operacji": None}
    apply_receipt_cards(fields, words)
    assert fields["tytul"] == "Zakup sprzętu technicznego"
