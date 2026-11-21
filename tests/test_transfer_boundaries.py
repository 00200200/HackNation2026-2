"""Document routing, OCR furniture and transaction-field boundaries."""

from unittest.mock import MagicMock

import pytest

from kio2json import bank_transfer, pdf_text
from kio2json.classify import classify

ACCOUNTS = "Nadawca: " + "31" * 13 + "\nOdbiorca: " + "42" * 13


@pytest.mark.parametrize(
    ("fields", "amount", "title", "ref"),
    [
        (
            "Kwota przelewu: brak\nOpłata bankowa (kwota: 3,40 PLN)\nTytuł: Identyfikator operacji: RT123456",
            None,
            None,
            "RT123456",
        ),
        ("Tytuł:\nBankowa gwarancja wadialna", None, "Bankowa gwarancja wadialna", None),
        ("Tytuł:\nNumer faktury 42/AB", None, "Numer faktury 42/AB", None),
        ("Tytuł: rata  Taryfa specjalna: nocna", None, "rata", None),
        ("Tytuł:\nWarunki dodatkowe: bez uwag", None, None, None),
        ("Tytuł: Kod księgowy: XY", None, None, None),
        ("Koszt (wartość: 11,00 zł)", None, None, None),
        ("Opis: wniesienie wpisu\nIdentyfikator transakcji QA987654", None, "wniesienie wpisu", "QA987654"),
        ("Uwagi: kwota: 89,00 PLN", None, None, None),
        ("Kwota operacji:\n12,35 PLN\nTytuł: opłata bankowa", 12.35, "opłata bankowa", None),
        ("Opis:\nBankowość dla firm\nKoszt usługi: 9,90", None, "Bankowość dla firm", None),
        ("Kwota operacji: brak\nInstrukcja: wpisz kwota 11,11 PLN", None, None, None),
    ],
)
def test_bank_fields(fields, amount, title, ref):
    data = bank_transfer.extract(fields)["przelew_bankowy"]
    assert (data["kwota"], data["tytul"], data["numer_transakcji"]) == (amount, title, ref)


@pytest.mark.parametrize(
    ("heading", "body", "expected"),
    [
        ("WYROK Z DNIA 17 LISTOPADA", "ODWOŁANIE\nOdwołujący: Wrzosik", None),
        ("POSTANOWIENIE z uzasadnieniem", "PEŁNOMOCNICTWO", None),
        ("ODWOŁANIE", "Odwołujący: Wrzosik\nCytowany dokument:\nWYROK", "appeal"),
        ("FAKTURA KORYGUJĄCA", "Potwierdzenie przelewu\nKwota: 19,22", None),
        ("Prosimy o przesłanie dokumentu: potwierdzenie przelewu", "Kwota: 21,22", None),
        ("Wezwanie do zapłaty", "Potwierdzenie przelewu\nKwota: 12,33", None),
        ("Potwierdzenie przelewu", "Opłata bankowa (kwota: 3,40 PLN)", None),
        ("Potwierdzenie przelewu", "Data wydruku: 12.10.2026", None),
        ("Potwierdzenie przelewu", "Data operacji: 12.10.2026", "bank_transfer"),
        ("Potwierdzenie przelewu", "Kwota operacji: 19,22\nStatus: odrzucony", None),
        ("Przelew", "Status: zrealizowany\nKwota: 19,22", "bank_transfer"),
    ],
)
def test_classification_needs_document_evidence(heading, body, expected):
    assert classify([f"{heading}\n{body}\n{ACCOUNTS}"]) == expected


@pytest.mark.parametrize(
    "stub", ["Strona: 1 z 1", "Page 9 of 12", "— 4 —", "Str. 3/7", "2", "p. 4 / 9", "Arkusz 7 z 9"]
)
def test_footer_furniture_needs_ocr(stub, monkeypatch):
    page = MagicMock()
    page.extract_text.return_value = stub
    doc = MagicMock()
    doc.__enter__.return_value.pages = [page]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda _: doc)
    monkeypatch.setattr(pdf_text, "_ocr", lambda _: "odczyt")
    assert pdf_text.read_pages("test.pdf") == ["odczyt"]


def test_transfer_account_without_a_supported_role():
    number = "68" * 13
    for field, expected in [("Konto:", (None, None)), ("Rachunek odbiorcy:", (None, number))]:
        assert bank_transfer._accounts(f"{field} {number}") == expected
    assert bank_transfer._accounts(f"Nadawca: {number}\nNadawca: {'47' * 13}") == (None, None)


def test_transfer_title_and_status_on_one_line():
    assert bank_transfer.extract("Tytuł: rata Status: wykonany")["przelew_bankowy"]["tytul"] == "rata"
