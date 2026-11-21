import pytest

from kio2json import bank_transfer
from kio2json.classify import classify

SENDER = "46137900000000000000471362"
RECIPIENT = "97298300000000000000836412"
DETAIL = f"""Przelew z rachunku - Szczegóły transakcji zrealizowanej
Z rachunku {SENDER}
Na rachunek {RECIPIENT}
Kwota -86,34 PLN
Data operacji 2030-02-05"""
OWNER = f"""Potwierdzenie wykonanej operacji Suma kontrolna dokumentu: a46eb729
Rachunek właściciela {SENDER} PLN
Rachunek kontrahenta {RECIPIENT}
Data księgowania 05.02.2030
Kwota -86,34 PLN
Referencje banku 73#458#02"""


def test_outgoing_debit_details():
    assert classify([DETAIL]) == "bank_transfer"


def test_single_debit_binds_owner_counterparty_and_bank_reference():
    assert classify([OWNER]) == "bank_transfer"
    fields = bank_transfer.extract(OWNER)["przelew_bankowy"]
    assert (fields["z_rachunku"], fields["na_rachunek"], fields["numer_transakcji"]) == (SENDER, RECIPIENT, "73#458#02")


@pytest.mark.parametrize("heading", ["Wyciąg bankowy", "Wezwanie do zapłaty", "Faktura VAT", "Postanowienie"])
def test_debit_details_embedded_in_negative(heading):
    assert classify([heading + "\n" + DETAIL]) is None


def test_debit_details_with_pending_status():
    assert classify([DETAIL + "\nStatus: oczekujący"]) is None


def scan(text, monkeypatch):
    from kio2json import pipeline

    def read(path, *, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [text]

    monkeypatch.setattr(pipeline, "read_pages", read)
    return pipeline.process_pdf("invented.pdf")


def test_booked_single_transfer_row_without_a_confirmation_heading(monkeypatch):
    text = f"""Data operacji
2030-02-05
Data księgowania
2030-02-06
Opis Kwota
PRZELEW INTERNETOWY -86,34 PLN
Z rachunku: {SENDER}
Na rachunek: {RECIPIENT}
Tytuł: materiał
Dokument jest wydrukiem komputerowym."""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["kwota"] == 86.34
    assert record["przelew_bankowy"]["tytul"] == "materiał"
    assert scan("Wyciąg z rachunku\n" + text, monkeypatch) == (None, {})


def test_debit_type_and_posted_date_bind_generic_source(monkeypatch):
    text = f"""Numer rachunku {SENDER}
Data operacji "2030-02-05
Rachunk odbiorcy:
{RECIPIENT}
Typ transakcji Przelew z rachunku
Kwota -86,34 PLN"""
    assert classify([text]) is None
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["z_rachunku"] == SENDER


def test_participant_table_keeps_printed_account_prefix(monkeypatch):
    text = f"""Potwierdzenie transakcji
Dane nadawcy
Nazwa i adres Numer rachunku Nazwa banku
Jasny Las PL{SENDER} Bank
Dane odbiorcy
Nazwa i adres Numer rachunku Nazwa banku
Firma {RECIPIENT}
Kwota: 86,34 PLN
Data operacji: 2030-02-05"""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["z_rachunku"] == "PL" + SENDER
    assert record["przelew_bankowy"]["na_rachunek"] == RECIPIENT


def test_completed_outgoing_order_with_table_rule_across_state(monkeypatch):
    text = f"""Przelew krajowy
Typ zlecenia Przelew krajowy
| XX wykonane
Rachunek zleceniodawcy: {SENDER}
Rachunek kontrahenta - {RECIPIENT}
Kwota 86,34 PLN
Zlecona data wykonania 05.02.2030
Szczegóły płatności: Materiał
Signature Not Verified"""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["na_rachunek"] == RECIPIENT
    assert record["przelew_bankowy"]["tytul"] == "Materiał"
    assert scan(text.replace("XX wykonane", "NIE wykonane"), monkeypatch) == (None, {})


def test_skewed_ocr_table_binds_date_and_amount_to_their_columns():
    from kio2json.pdf_text import WordBox
    from kio2json.receipt_layout import receipt_cell_fields

    rows = [("Kwota", "Data operacji"), ("86,34", "05.02.2030")]
    boxes = [
        WordBox(1, word, x, 20 * row - 0.04 * x, x + len(word) * 4, 20 * row - 0.04 * x + 8)
        for row, pair in enumerate(rows)
        for x, word in zip((10, 400), pair)
    ]
    assert receipt_cell_fields(boxes, ocr=True) == {"Kwota": "86,34", "Data operacji": "05.02.2030"}


def test_completed_confirmation_with_one_readable_role_and_bank_reference(monkeypatch):
    text = f"""/- Potwierdzenie transakcji
Rachunek nadawcy: {SENDER}
Dane odbiorcy:
Numer transakcji: TB-3059
Data księgowania: 06.02.2030
Kwota: 86 , 34 PLN"""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    fields = record["przelew_bankowy"]
    assert (fields["na_rachunek"], fields["kwota"]) == (None, 86.34)
    assert scan(text.replace("Numer transakcji: TB-3059", "Nr wydruku: 3059"), monkeypatch) == (None, {})


def test_attested_transaction_with_detached_unlabelled_values(monkeypatch):
    text = f"""Potwierdzenie transakcji
{SENDER}
{RECIPIENT}
2030-02-05
2030-02-05
86,34 PLN
Dokument jest wydrukiem potwierdzającym dokonanie transakcji."""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    fields = record["przelew_bankowy"]
    assert (fields["data_operacji"], fields["kwota"]) == ("2030-02-05", 86.34)
    assert fields["z_rachunku"] is fields["na_rachunek"] is None
    assert scan(text.replace("potwierdzającym dokonanie", "dotyczącym planowanej"), monkeypatch) == (None, {})


def test_fee_in_scanned_title_is_content(monkeypatch):
    from kio2json.pdf_text import WordBox
    from kio2json.receipt_layout import receipt_cell_fields

    rows = ["Tytuł", "Wpis od skargi"]
    boxes = [WordBox(1, row, 10, i * 18, 10 + 6 * len(row), i * 18 + 10) for i, row in enumerate(rows)]
    assert receipt_cell_fields(boxes, ocr=True)["Tytuł"] == rows[1]
    rows[1] = "Opłata skarbowa od umowy"
    boxes[1] = boxes[1]._replace(text=rows[1], x1=10 + 6 * len(rows[1]))
    assert receipt_cell_fields(boxes, ocr=True)["Tytuł"] == rows[1]


def test_reference_column_can_be_unreadable_on_a_booked_confirmation(monkeypatch):
    text = f"""Potwierdzenie operacji
Numer referencyjny:
Rachunek nadawcy: {SENDER}
Dane odbiorcy:
Kwota: 86,34 PLN
Data księgowania: 06.02.2030"""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["numer_transakcji"] is None


def test_numbered_statement_is_empty_even_with_a_debit_detail():
    assert classify(["Wyciąg nr 8/2030\n" + DETAIL]) is None


def test_ocr_repairs_preserve_iban_country_prefix(monkeypatch):
    text = DETAIL.replace(SENDER, "PL" + SENDER.replace("0", "?", 1))
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["z_rachunku"] == "PL" + SENDER


def test_single_booked_debit_can_route_with_damaged_party_columns(monkeypatch):
    text = f"""Potwierdzenie wykonanej operacji
Rachunek właściciela
Dane kontrahenta
Szczegóły tabeli Dała waluty Data księgowania Kwota
05.02.2030 06.022030 13:47 -86,34 PLN
Numer IBAN: PL{SENDER}"""
    kind, record = scan(text, monkeypatch)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["data_operacji"] == "2030-02-06"
    assert record["przelew_bankowy"]["na_rachunek"] is None
    assert scan(text.replace("Dane kontrahenta", "Ślad audytu"), monkeypatch) == (None, {})


@pytest.mark.parametrize("heading", ["Wyciąg nr. 4/2031", "Historia operacji"])
def test_account_history_precedes_embedded_debit(heading):
    assert classify([heading + "\n" + DETAIL]) is None


def test_negated_bank_attestation(monkeypatch):
    text = f"""Potwierdzenie transakcji
{SENDER}
{RECIPIENT}
2030-02-05
2030-02-05
86,34 PLN
Dokument nie jest wydrukiem potwierdzającym dokonanie transakcji."""
    assert scan(text, monkeypatch) == (None, {})


def test_account_holder_iban_on_a_posted_debit(monkeypatch):
    text = f"""Potwierdzenie wykonanej operacji
Rachunek właściciela
Dane kontrahenta
Data waluty Data księgowania Kwota
05.02.2030 06.02.2030 -86,34 PLN
Numer IBAN tego rachunku: PL{SENDER}"""
    _, record = scan(text, monkeypatch)
    assert record["przelew_bankowy"]["z_rachunku"] == "PL" + SENDER


def test_bank_named_reference_in_same_row_as_date():
    from kio2json.pdf_text import WordBox
    from kio2json.receipt_layout import receipt_cell_fields

    words = "Nr transakcji w Banku Różanym: 735092 Data księgowania: 06.02.2030"
    boxes = [WordBox(1, words, 10, 10, 10 + 6 * len(words), 20)]
    assert receipt_cell_fields(boxes, ocr=True)["Numer transakcji"] == "735092"


def test_account_prefix_belongs_to_the_role_on_its_source_page():
    from kio2json.ocr_extract import extract_bank_transfer

    pages = [
        f"Potwierdzenie przelewu\nZ rachunku: {SENDER}\nNota archiwalna: PL{SENDER}",
        f"Na rachunek: PL{RECIPIENT}",
    ]
    fields = extract_bank_transfer(pages, {1, 2})["przelew_bankowy"]
    assert (fields["z_rachunku"], fields["na_rachunek"]) == (SENDER, "PL" + RECIPIENT)
