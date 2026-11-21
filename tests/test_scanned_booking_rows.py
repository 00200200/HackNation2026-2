"""Invented single-debit history rows and signed outgoing orders."""

import pytest

from kio2json import pipeline
from kio2json.ocr_accounts import normalize_receipt
from kio2json.receipt_layout import _cell_value

PAYER = "78351200009981234567890123"
PAYEE = "56458700991234567801234567"


def scanned(text, monkeypatch):
    def read(path, *, ocr_pages=None, **kw):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [text]

    monkeypatch.setattr(pipeline, "read_pages", read)
    return pipeline.process_pdf("invented.pdf")


def test_interleaved_posted_debit(monkeypatch):
    text = f"""Data Opis Kwota
Data operacji PRZELEW KRAJOWY -248,90 PLN
2032-03-04 Z rachunku: {PAYER}
Data księgowania Firma Kobaltowa
2032-03-05 Na rachunek: {PAYEE}
Tytuł: Wyposażenie kuchni"""
    kind, data = scanned(text, monkeypatch)
    assert kind == "bank_transfer"
    fields = data["przelew_bankowy"]
    assert (fields["data_operacji"], fields["kwota"], fields["z_rachunku"], fields["na_rachunek"]) == (
        "2032-03-04",
        248.9,
        PAYER,
        PAYEE,
    )
    assert scanned("Wyciąg nr 4\n" + text, monkeypatch) == (None, {})


ORDER = f"""Przelew krajowy
Typ zlecenia Przelew internetowy
Statuś .. wykonańe
Dane zleceniodawcy
Rachunck zleceniodawcy {PAYER}
Dane kontrahenta
Racnunek kontrahenta {PAYEE}
Dane zlecenia
| --- 248,90 PLN
Tryb realizacji zwykły
Zlecona dala wykonania 04 03 2032
Dokument podpisany przez Bank Wschodni
Data: 2032.03.04 16:24:20 CET"""


def test_verified_status_and_signed_date_support_bank_order(monkeypatch):
    kind, data = scanned(ORDER, monkeypatch)
    assert kind == "bank_transfer"
    f = data["przelew_bankowy"]
    assert (f["kwota"], f["data_operacji"], f["z_rachunku"], f["na_rachunek"]) == (248.9, "2032-03-04", PAYER, PAYEE)


@pytest.mark.parametrize("status", ["nie wykonane", "niewykonane", "czeka"])
def test_ocr_cannot_turn_other_states_into_a_completed_order(monkeypatch, status):
    assert scanned(ORDER.replace("wykonańe", status), monkeypatch) == (None, {})


def test_requested_day_without_matching_bank_signature_is_not_an_execution_date():
    text = normalize_receipt(ORDER.replace("2032.03.04", "2032.03.05"))
    assert "Data operacji:" not in text


def test_speckle_after_date_only_removed_on_an_ocr_cell():
    assert _cell_value("Data operacji", "04.03.2032 *", True) == "04.03.2032"
    assert _cell_value("Data operacji", "04.03.2032 *", False) is None


def test_actual_payment_day_takes_precedence_over_a_signed_request(monkeypatch):
    statement = "Przelew wykonano dnia 07.03.2032."
    _, data = scanned(ORDER + "\n" + statement, monkeypatch)
    assert data["przelew_bankowy"]["data_operacji"] == "2032-03-07"


@pytest.mark.parametrize("label", ["Rachunek prowizji", "Rachunek nadawcy", "Rachunek banku"])
def test_bank_order_does_not_relabel_another_account_under_a_party_heading(label):
    text = ORDER.replace("Racnunek kontrahenta", label)
    assert f"Rachunek odbiorcy: {PAYEE}" not in normalize_receipt(text)
