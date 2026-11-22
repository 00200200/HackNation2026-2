"""Invented financial tables with independent fields and different column geometries."""

import pytest

from kio2json.pdf_text import WordBox
from kio2json.receipt_layout import booking_heading, has_detached_labels, restore_receipt_rows


def boxes(*rows):
    return [
        WordBox(1, text, x, 16 * i, x + 5 * len(text), 16 * i + 10) for i, row in enumerate(rows) for x, text in row
    ]


def test_inline_amount_after_date_triggers_reading_order_without_a_heading_template():
    pages = ["Bankowość internetowa\nData operacji: 21.04.2026 Kwota: 91,42 PLN\nNr transakcji: MV834721"]
    words = boxes([(20, "Data operacji: 21.04.2026"), (260, "Kwota: 91,42 PLN")])
    assert has_detached_labels(pages)
    restored = restore_receipt_rows(pages, words)[0]
    assert "Kwota: 91,42 PLN" in restored.splitlines()
    assert pages[0] in restored


def test_reordered_payment_columns_work_without_a_party_table():
    words = boxes(
        [(20, "Kwota"), (145, "Waluta"), (245, "Tytuł operacji"), (475, "Data księgowania")],
        [(20, "-91,42"), (145, "PLN"), (245, "Kryształowe"), (475, "21.04.2026")],
        [(245, "lustra")],
    )
    lines = restore_receipt_rows(["Dokument księgowy"], words)[0].splitlines()
    assert "Kwota: -91,42" in lines
    assert "Data księgowania: 21.04.2026" in lines
    assert "Tytuł: Kryształowe lustra" in lines


def test_role_columns_find_accounts_below_addresses_and_keep_each_role_separate():
    words = boxes(
        [(20, "Beneficjent"), (300, "Zleceniodawca")],
        [(20, "Świetlisty Granat"), (300, "Niebieska Skała")],
        [(20, "ul. Wodna 13"), (300, "ul. Ostra 57")],
        [(20, "97298300000000000000836412"), (300, "**** **** **** 1362")],
    )
    lines = restore_receipt_rows(["Bankowość internetowa"], words)[0].splitlines()
    assert "Rachunek odbiorcy: 97298300000000000000836412" in lines
    assert any(line.startswith("Rachunek nadawcy:") and "*" in line for line in lines)


def test_multiple_operation_rows_do_not_supply_fields_for_a_single_transfer():
    words = boxes(
        [(20, "Kwota"), (180, "Tytuł")],
        [(20, "89,01"), (180, "Papier")],
        [(20, "57,23"), (180, "Kreda")],
    )
    assert restore_receipt_rows(["Zaksięgowane transakcje"], words) == ["Zaksięgowane transakcje"]


@pytest.mark.parametrize("ocr", [True, False])
def test_fuzzy_labels_and_single_glyph_account_repairs_require_ocr(ocr):
    words = boxes(
        [(20, "Kwota"), (180, "Odbiorcz")],
        [(20, "71,42"), (180, "7?351200009981234567890123")],
    )
    pages = ["Elektroniczne pokwitowanie"]
    restored = restore_receipt_rows(pages, words, ocr=ocr)[0]
    assert ("Rachunek odbiorcy: 78351200009981234567890123" in restored.splitlines()) is ocr
    assert booking_heading("Potwierdzenie wykonanej operacjj", ocr=ocr) is ocr


def test_operation_booking_and_value_date_columns_preserve_their_meaning():
    words = boxes(
        [(20, "Data waluty"), (170, "Data operacji"), (300, "Data księgowania")],
        [(20, "19.04.2026"), (170, "20.04.2026"), (300, "21.04.2026")],
    )
    lines = restore_receipt_rows(["Potwierdzenie"], words)[0].splitlines()
    assert "Data operacji: 20.04.2026" in lines
    assert "Data księgowania: 21.04.2026" in lines
    assert "Data operacji: 19.04.2026" not in lines


def test_an_unfamiliar_middle_column_does_not_become_part_of_the_title():
    words = boxes(
        [(20, "Tytuł"), (180, "Uwagi wewnętrzne"), (360, "Kwota")],
        [(20, "Blacha czarna"), (180, "uzgodniono"), (360, "56,14")],
    )
    lines = restore_receipt_rows(["Operacja bankowa"], words)[0].splitlines()
    assert "Tytuł: Blacha czarna" in lines
    assert "Kwota: 56,14" in lines


def test_conflicting_accounts_in_one_column_leave_an_independent_amount_available():
    words = boxes(
        [(20, "Odbiorca"), (280, "Kwota")],
        [(20, "97298300000000000000836412"), (280, "46,71 EUR")],
        [(20, "46137900000000000000471362")],
    )
    lines = restore_receipt_rows(["Operacja bankowa"], words)[0].splitlines()
    assert "Kwota: 46,71 EUR" in lines
    assert all("Rachunek odbiorcy:" not in line for line in lines)


def test_one_typed_column_can_be_bound_next_to_an_unfamiliar_heading():
    words = boxes(
        [(20, "Ścieżka audytu"), (250, "Kwota")],
        [(20, "automatyczna"), (250, "246,71 PLN")],
    )
    lines = restore_receipt_rows(["Dowód operacji"], words)[0].splitlines()
    assert "Kwota: 246,71 PLN" in lines


def test_layout_read_requires_printed_transaction_values():
    assert not has_detached_labels(["Opis wzoru formularza\nKwota Tytuł\nData operacji"])


def test_detached_plain_title_value_preceding_another_label():
    words = boxes(
        [(10, "Tytułem"), (200, "Dostawa")],
        [(10, "Numer transakcji"), (200, "TW740316")],
    )
    lines = restore_receipt_rows(["Przelew"], words)[0].splitlines()
    assert "Tytuł: Dostawa" in lines
    assert "Numer transakcji: TW740316" in lines


def test_interior_financial_word_in_remittance_text_is_part_of_the_title():
    words = boxes(
        [(20, "Tytuł: Faktura za półki, kwota brutto 37,25")],
        [(20, "Data operacji:"), (185, "20.07.2026")],
    )
    lines = restore_receipt_rows(["Pokwitowanie"], words)[0].splitlines()
    assert "Tytuł: Faktura za półki, kwota brutto 37,25" in lines
    assert all(not line.startswith("Kwota:") for line in lines)


def test_amount_column_continues_beside_an_independent_party_label():
    words = boxes([(280, "Kwota:")], [(20, "Odbiorca przelewu:"), (280, "89,10 PLN")])
    assert "Kwota: 89,10 PLN" in restore_receipt_rows(["Potwierdzenie realizacji przelewu"], words)[0]


def test_requested_day_cannot_supply_execution_date():
    words = boxes([(20, "Zlecona data realizacji przelewu"), (280, "2032-04-08")])
    assert "Data realizacji:" not in restore_receipt_rows(["Zlecenie"], words)[0]


@pytest.mark.parametrize(
    ("execution", "accepted"),
    [
        ("Data realizacji przelewu 2032-01-08", True),
        ("Data realizacji przelewu 2032-02-08", False),
        ("Zlecona data realizacji przelewu 2032-01-08", False),
    ],
)
def test_order_printout_requires_a_separate_execution_day(execution, accepted):
    from kio2json.classify import _executed_order_printout

    text = "Przelew krajowy Szczegóły przelewu przyjętego do realizacji\nData wydruku: 2032-01-09\n" + execution
    assert _executed_order_printout(text) is accepted


@pytest.mark.parametrize("label", ["Prowizja:", "Saldo:", "Opłata:"])
def test_neighboring_monetary_label_owns_its_value(label):
    words = boxes([(280, "Kwota:")], [(20, label), (280, "2,00 PLN")])
    assert "Kwota: 2,00" not in restore_receipt_rows(["Potwierdzenie"], words)[0]


def test_account_beneath_neighboring_party_stays_in_its_column():
    from kio2json.receipt_layout import receipt_cell_fields

    words = boxes(
        [(20, "Nadawca przelewu:"), (280, "Odbiorca przelewu:")],
        [(20, "Nr rachunku:"), (280, "78 3512 0000 9981 2345 6789 0123")],
    )
    assert "Rachunek nadawcy" not in receipt_cell_fields(words, ocr=True)


def test_scanned_receipt_routes_with_an_underlined_account_in_its_party_column():
    from kio2json.classify import classify
    from kio2json.ocr_accounts import account_evidence
    from kio2json.ocr_extract import extract_bank_transfer

    account = "78 3512 0000 9981 2345 6789 0123"
    page = (
        "Potwierdzenie przelewu\nNumer rachunku: 56458700991234567801234567\n"
        f"Odbiorca przelewu:\nNr rachunku: _{account}\nKwota: 48,20 PLN"
    )
    words = boxes([(20, "Odbiorca przelewu:")], [(20, "Nr rachunku: _" + account)])
    assert classify([page], ocr_accounts=account_evidence(page)) is None
    restored = restore_receipt_rows([page], words, ocr=True)
    evidence = account_evidence(restored[0])
    assert classify(restored, ocr_accounts=evidence) == "bank_transfer"
    assert extract_bank_transfer(restored, {1}, accounts=evidence)["przelew_bankowy"]["na_rachunek"] == (
        "78351200009981234567890123"
    )


@pytest.mark.parametrize("prefix", ["Kod archiwalny: _", "Nr rachunku: X_", "Nr rachunku: _DE "])
def test_a_nearby_identifier_cannot_fill_an_underlined_account_cell(prefix):
    from kio2json.receipt_layout import receipt_cell_fields

    words = boxes([(20, "Odbiorca przelewu:")], [(20, prefix + "78 3512 0000 9981 2345 6789 0123")])
    assert "Rachunek odbiorcy" not in receipt_cell_fields(words, ocr=True)
