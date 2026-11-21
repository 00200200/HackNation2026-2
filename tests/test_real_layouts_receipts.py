import pytest

from kio2json import bank_transfer
from kio2json.classify import classify

RECEIPT = """Potwierdzenie wykonania operacji
Dzienny numer transakcji 4
Data wydruku 18.08.2024
Data księgowania 16.08.2024
Z rachunku 56458700991234567801234567
Na rachunek 78351200009981234567890123
Kwota zaksięgowana −3 276,40 PLN
Tytuł operacji: dokument nr FA-
82
Data wystawienia dokumentu 18.08.2024"""


def test_executed_debit_fields_are_bound_to_their_labels():
    assert classify([RECEIPT]) == "bank_transfer"
    assert bank_transfer.extract(RECEIPT)["przelew_bankowy"] == {
        "data_operacji": "2024-08-16",
        "kwota": 3276.40,
        "numer_transakcji": "4",
        "z_rachunku": "56458700991234567801234567",
        "na_rachunek": "78351200009981234567890123",
        "tytul": "dokument nr FA-82",
    }


@pytest.mark.parametrize("heading", ["Wyciąg z rachunku", "Wezwanie do zapłaty", "Faktura pro forma"])
def test_execution_fields_inside_a_different_document(heading):
    assert classify([heading + "\n" + RECEIPT]) is None


def test_booking_form_uses_unique_checksum_repairs_and_abstains_on_ambiguity():
    repaired = RECEIPT.replace("78351200009981234567890123", "76351200009981234567890123")
    assert bank_transfer.extract(repaired)["przelew_bankowy"]["na_rachunek"] == "78351200009981234567890123"
    assert (
        bank_transfer.extract(RECEIPT.replace("78351200009981234567890123", "7?351200009981234567890123"))[
            "przelew_bankowy"
        ]["na_rachunek"]
        == "78351200009981234567890123"
    )
    assert (
        bank_transfer.extract(RECEIPT.replace("78351200009981234567890123", "79351200009981234567890123"))[
            "przelew_bankowy"
        ]["na_rachunek"]
        is None
    )


def test_pdf_columns_restore_labels_opposite_their_values(monkeypatch):
    from kio2json import pipeline
    from kio2json.pdf_text import WordBox

    rows = [
        ("Potwierdzenie realizacji przelewu", ""),
        ("Rachunek beneficjenta", "78351200009981234567890123"),
        ("Z rachunku", "56458700991234567801234567"),
        ("Data obciążenia", "14.03.2025"),
        ("Data stempla", "15.03.2025"),
        ("Kwota", "24,60"),
        ("Tytułem", "Dostawa"),
        ("Numer transakcji", "DK845312"),
    ]

    def read(path, force_ocr=False, *, word_boxes=None, **kwargs):
        if word_boxes is not None:
            for i, row in enumerate(rows):
                for x, cell in zip([10, 200], row):
                    if cell:
                        word_boxes.append(WordBox(1, cell, x, 20 * i, x + 80, 20 * i + 10))
        return ["\n".join(cell for column in zip(*rows) for cell in column if cell)]

    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    assert data["przelew_bankowy"] == {
        "kwota": 24.60,
        "data_operacji": "2025-03-14",
        "tytul": "Dostawa",
        "numer_transakcji": "DK845312",
        "na_rachunek": "78351200009981234567890123",
        "z_rachunku": "56458700991234567801234567",
    }


def test_debit_table_uses_booking_date_and_account_holder_direction():
    text = """Potwierdzenie wykonanej operacji
Dane właściciela rachunku
Rachunek właściciela 56458700991234567801234567
Dane kontrahenta
Rachunek 78351200009981234567890123
Data waluty Data księgowania Kwota
13.07.2024 15.072024 09:56:04 -72,10 PLN
Referencje banku
741332531"""
    assert classify([text]) == "bank_transfer"
    values = bank_transfer.extract(text)["przelew_bankowy"]
    assert (values["z_rachunku"], values["na_rachunek"]) == ("56458700991234567801234567", "78351200009981234567890123")
    assert (values["data_operacji"], values["kwota"], values["numer_transakcji"]) == ("2024-07-15", 72.10, "741332531")


def test_booking_form_with_pending_state_is_rejected():
    assert classify([RECEIPT + "\nStan: oczekujący"]) is None


def test_operation_date_precedes_booking_date_even_when_printed_second():
    text = RECEIPT.replace("Data księgowania 16.08.2024", "Data księgowania 16.08.2024\nData operacji 15.08.2024")
    assert bank_transfer.extract(text)["przelew_bankowy"]["data_operacji"] == "2024-08-15"
