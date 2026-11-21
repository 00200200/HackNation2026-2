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


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("76351200009981234567890123", "78351200009981234567890123"),
        ("7?351200009981234567890123", "78351200009981234567890123"),
        ("79351200009981234567890123", None),
    ],
)
def test_only_ocr_repairs_an_uncertain_account(monkeypatch, printed, expected):
    from kio2json import pipeline

    text = RECEIPT.replace("78351200009981234567890123", printed)

    def read(path, *, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [text]

    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    assert data["przelew_bankowy"]["na_rachunek"] == expected
    if printed.isdigit():
        assert bank_transfer.extract(text)["przelew_bankowy"]["na_rachunek"] == printed


@pytest.mark.parametrize("mode", ["R", "L", "V"])
def test_pdf_columns_restore_labels_opposite_their_values(monkeypatch, mode):
    from kio2json import llm, pipeline
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

    if mode != "R":
        for key, value in {
            "BASE_URL": "http://localhost",
            "MODEL": "fake",
            "API_KEY": "fake",
            "MODE": mode,
            "ROUTING": "rules",
        }.items():
            monkeypatch.setenv("KIO_LLM_" + key, value)

        def model(definition, text, **kwargs):
            assert text == read(None)[0]  # cite the original reading, before cell restoration
            return bank_transfer.extract("")

        monkeypatch.setattr(llm, "extract_llm", model)
    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    if mode != "R":
        assert data == bank_transfer.extract("")
        return
    assert data["przelew_bankowy"] == {
        "kwota": 24.60,
        "data_operacji": "2025-03-14",
        "tytul": "Dostawa",
        "numer_transakcji": "DK845312",
        "na_rachunek": "78351200009981234567890123",
        "z_rachunku": "56458700991234567801234567",
    }


def test_debit_table_uses_booking_date_and_account_holder_direction(monkeypatch):
    from kio2json import pipeline

    text = """Potwierdzenie wykonanej operacji
Dane właściciela rachunku
Rachunek właściciela 56458700991234567801234567
Dane kontrahenta
Rachunek 78351200009981234567890123
Data waluty Data księgowania Kwota
13.07.2024 15.072024 09:56:04 -72,10 PLN
Referencje banku
741332531"""

    def read(path, *, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [text]

    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    values = data["przelew_bankowy"]
    assert (values["z_rachunku"], values["na_rachunek"]) == ("56458700991234567801234567", "78351200009981234567890123")
    assert (values["data_operacji"], values["kwota"], values["numer_transakcji"]) == ("2024-07-15", 72.10, "741332531")


def test_booking_form_with_pending_state_is_rejected():
    assert classify([RECEIPT + "\nStan: oczekujący"]) is None


def test_operation_date_precedes_booking_date_even_when_printed_second():
    text = RECEIPT.replace("Data księgowania 16.08.2024", "Data księgowania 16.08.2024\nData operacji 15.08.2024")
    assert bank_transfer.extract(text)["przelew_bankowy"]["data_operacji"] == "2024-08-15"


def test_ocr_repairs_a_unique_digit_in_an_ordinary_confirmation(monkeypatch):
    from kio2json import pipeline

    def read(path, *, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [
            (
                "Potwierdzenie przelewu\nRachunek nadawcy: 56458700991234567801234567\n"
                "Rachunek odbiorcy: 76351200009981234567890123\nKwota: 42,08\nData operacji: 04.03.2025"
            )
        ]

    monkeypatch.setattr(pipeline, "read_pages", read)
    _, data = pipeline.process_pdf("invented.pdf")
    assert data["przelew_bankowy"]["na_rachunek"] == "78351200009981234567890123"


def test_unreadable_confirmed_scan_retries_first_page_with_inferred_dpi(monkeypatch):
    from kio2json import pipeline

    calls = []

    def read(path, *, engine, ocr_pages=None, **kwargs):
        calls.append(engine)
        if ocr_pages is not None:
            ocr_pages.append(1)
        return ["Potwierdzenie wykonania operacji\nDzienny numer transakcji"] if len(calls) == 1 else [RECEIPT]

    monkeypatch.setattr(pipeline, "DEFAULT_OCR_ENGINE", "tesseract-dpi")
    monkeypatch.delenv("KIO_OCR_ENGINE", raising=False)
    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    assert data["przelew_bankowy"]["numer_transakcji"] == "4"
    assert calls == ["tesseract-dpi", "tesseract"]


def test_parallel_party_and_payment_columns_keep_each_fields_values(monkeypatch):
    from kio2json import pipeline
    from kio2json.pdf_text import WordBox

    cells = [
        (20, 10, "Potwierdzenie transakcji"),
        (20, 25, "Nr transakcji:"),
        (120, 25, "BF576321"),
        (215, 25, "Data księgowania:"),
        (335, 25, "13.05.2024"),
        (20, 42, "Dane"),
        (45, 42, "Płatnika:"),
        (215, 42, "Dane"),
        (240, 42, "Odbiorcy:"),
        (20, 55, "?6 4587 0099 1234 5678 0123 4567"),
        (215, 55, "78 3512 0000 9981 2345 6789 0123"),
        (20, 105, "Tytuł"),
        (45, 105, "operacji:"),
        (215, 105, "Szczegóły"),
        (265, 105, "operacji:"),
        (355, 105, "Kwota:"),
        (20, 119, "Zakup"),
        (215, 119, "PRZELEW"),
        (355, 119, "49,12"),
        (20, 132, "papieru"),
        (355, 132, "PLN"),
        (20, 238, "Adres banku"),
    ]

    def read(path, *, word_boxes=None, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        if word_boxes is not None:
            word_boxes.extend(WordBox(1, t, x, y, x + 12, y + 7) for x, y, t in cells)
        return ["\n".join(t for x, y, t in cells)]

    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf("invented.pdf")
    assert kind == "bank_transfer"
    assert data["przelew_bankowy"] == {
        "kwota": 49.12,
        "data_operacji": "2024-05-13",
        "tytul": "Zakup papieru",
        "numer_transakcji": "BF576321",
        "na_rachunek": "78351200009981234567890123",
        "z_rachunku": "56458700991234567801234567",
    }


def test_second_read_propagates_a_recognition_timeout(monkeypatch):
    from kio2json import pipeline

    def read(path, *, engine, ocr_pages=None, **kwargs):
        if engine == "tesseract":
            raise pipeline.OCRRecognitionError("OCR timed out")
        ocr_pages.append(1)
        return ["Potwierdzenie wykonania operacji\nDzienny numer transakcji"]

    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract-dpi")
    monkeypatch.setattr(pipeline, "read_pages", read)
    with pytest.raises(pipeline.OCRRecognitionError, match="timed out"):
        pipeline.process_pdf("invented.pdf")
