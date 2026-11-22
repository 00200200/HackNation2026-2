"""Independent payment cards and near-negatives with the same ledger values."""

import pytest

from kio2json.bank_transfer import extract
from kio2json.classify import classify

CARD = """Karta transakcji krajowej / poświadczenie wykonania
Rachunek obciążony: 47 1020 5558 0000 0102 0003 4567
IBAN beneficjenta: PL34 9516 3218 0000 9712 0001 0003
Kwota operacji: 19,64 PLN
Data wykonania: 29 lutego 2032
Identyfikator operacji: RK-7129
Tytuł: Próba papieru"""


def test_settlement_caption_needs_one_dated_payment_with_two_account_roles():
    assert classify([CARD]) == "bank_transfer"
    fields = extract(CARD)["przelew_bankowy"]
    assert fields["kwota"] == 19.64
    assert fields["data_operacji"] == "2032-02-29"
    assert fields["na_rachunek"].startswith("PL")
    assert fields["z_rachunku"] == "47102055580000010200034567"


@pytest.mark.parametrize(
    "page",
    [
        CARD.replace("poświadczenie wykonania", "potwierdzenie przyjęcia zlecenia"),
        CARD.replace("Karta transakcji krajowej", "Wyciąg bankowy"),
        CARD.replace("Karta transakcji krajowej", "Rejestr operacji"),
        CARD.replace("Karta transakcji krajowej", "Historia płatności"),
        CARD.replace("Karta transakcji krajowej", "Lista transakcji"),
        CARD.replace("Karta transakcji krajowej", "Karta transakcji planowanej"),
        CARD.replace("Karta transakcji krajowej", "Formularz dyspozycji"),
        CARD.replace("Karta transakcji krajowej", "Faktura"),
        CARD.replace("Karta transakcji krajowej", "Wezwanie do zapłaty"),
        CARD.replace("Karta transakcji krajowej", "Wniosek o rozliczenie transakcji"),
        CARD.replace("Rachunek obciążony", "Rachunek zwrotów"),
        CARD.replace("IBAN beneficjenta", "Rachunek obciążony"),
        CARD + "\nKwota operacji: 23,11 PLN\nIdentyfikator operacji: RK-7194",
        CARD + "\nStan przelewu: odrzucony",
        CARD + "\nStan operacji: odmowa",
        CARD + "\nWynik operacji: odmowa",
        CARD + "\nPowód odrzucenia: brak środków",
        "Pro forma\n" + CARD,
        CARD.replace("Data wykonania", "Data zlecenia"),
        "Tytuł przelewu:\n" + CARD,
        CARD.replace("poświadczenie wykonania", "brak poświadczenia wykonania"),
        CARD.replace("Karta transakcji krajowej /", "Tytuł przelewu:"),
    ],
)
def test_ambiguous_or_unsettled_cards_stay_empty(page):
    assert classify([page]) is None


@pytest.mark.parametrize("printed", ["29 II 2032", "29.II.2032", "29-II-2032"])
def test_roman_month_in_transaction_cell(printed):
    fields = extract(f"Data wydruku: 14 V 2032\nData operacji: {printed}")["przelew_bankowy"]
    assert fields["data_operacji"] == "2032-02-29"
    assert extract("Data operacji: 31 IV 2032")["przelew_bankowy"]["data_operacji"] is None


def test_currency_before_whole_amount_in_typed_cell():
    page = "Opłata: PLN 1\nWartość operacji: PLN 8 064"
    assert extract(page)["przelew_bankowy"]["kwota"] == 8064
    assert extract(page.replace("PLN 8 064", "PLN 8 06"))["przelew_bankowy"]["kwota"] is None


@pytest.mark.parametrize("suffix", [".", " (słownie: sto dziewięćdziesiąt złotych)"])
def test_whole_amount_with_following_annotation(suffix):
    assert extract("Kwota: 190 PLN" + suffix)["przelew_bankowy"]["kwota"] == 190


def test_caption_on_separate_heading_line():
    assert classify([CARD.replace(" / ", "\n")]) == "bank_transfer"


@pytest.mark.parametrize("empty_reason", ["nie dotyczy.", "N/D", "—"])
def test_unused_reason_field_accepts_a_completed_transfer(empty_reason):
    assert classify([CARD + "\nPowód odrzucenia: " + empty_reason]) == "bank_transfer"
