"""Route one settled payment using the ledger or an assertion by its bank."""

import pytest

from kio2json.classify import classify

PAYER = "46137900000000000000471362"
PAYEE = "97298300000000000000836412"
ACCOUNTS = f"Z rachunku: {PAYER}\nNa rachunek: {PAYEE}"
HISTORY = (
    "Historia rachunku\nData operacji | Opis | Kwota\n"
    "15.04.2031 | Przelew krajowy | -52,90 PLN\n"
    f"{ACCOUNTS}\nTytuł: Zaliczka WZ/74/2031\nIdentyfikator operacji: BW08"
)
DETAIL = (
    "Bank Podmiejski\nInformacje o zleceniu przelewu\nStan realizacji\nZaksięgowano\n"
    f"{ACCOUNTS}\nKwota: 52,90 PLN\nIdentyfikator operacji: BW08"
)


def test_single_posted_debit_in_an_account_history():
    assert classify([HISTORY]) == "bank_transfer"


@pytest.mark.parametrize(
    "suffix",
    ["\n16.04.2031 | Przelew przychodzący | 240,00 PLN", "\n18.04.2031 | Opłata za kartę | -7,00 PLN"],
)
def test_second_unselected_entry_keeps_the_history_empty(suffix):
    assert classify([HISTORY + suffix]) is None
    assert classify([HISTORY, suffix]) is None


@pytest.mark.parametrize("heading", ["Szczegóły operacji płatniczej", "Informacje o zleceniu przelewu"])
def test_completed_state_can_occupy_its_own_cell(heading):
    assert classify([DETAIL.replace("Informacje o zleceniu przelewu", heading)]) == "bank_transfer"


@pytest.mark.parametrize("value", ["Oczekuje na środki", "Odrzucone", "Planowane", "Do wysłania"])
def test_order_request_with_separate_adverse_state_remains_empty(value):
    assert classify([DETAIL.replace("Zaksięgowano", value) + "\nData zlecenia: 15.04.2031"]) is None


@pytest.mark.parametrize("heading", ["Faktura pro forma", "Wezwanie do zapłaty", "Pismo przewodnie"])
def test_bank_fields_embedded_in_another_document_are_not_a_receipt(heading):
    assert classify([heading + "\n" + HISTORY]) is None


def test_bank_attestation_without_a_confirmation_form_heading():
    text = (
        "Biuro operacji bankowych\nSzanowna Pani,\n"
        f"Poświadczamy realizację płatności dnia 15.04.2031 z konta {PAYER}\n"
        f"w wysokości 52,90 EUR na konto {PAYEE}."
    )
    assert classify([text]) == "bank_transfer"
    assert classify(["Załączniki:\n" + text]) is None
    assert classify(["Rejestr pism banku\n" + text]) is None


def test_one_posted_history_row_under_bank_letterhead():
    assert classify([HISTORY.replace("Historia rachunku", "Bank Podmiejski")]) == "bank_transfer"


def test_order_details_have_actual_posting_evidence():
    page = DETAIL.replace("Stan realizacji\nZaksięgowano", "Data księgowania: 15.04.2031")
    assert classify([page]) == "bank_transfer"
    assert classify([page.replace("Data księgowania", "Planowana data księgowania")]) is None


SELECTED = (
    "Historia transakcji\n"
    "12.04.2031 | Przelew B12 | -9,00 PLN\nStatus: Odrzucono\n"
    "15.04.2031 | Przelew BW08 | -52,90 PLN\n"
    "Szczegóły wybranej transakcji\n"
    f"{ACCOUNTS}\nKwota: 52,90 PLN\nStatus: Zaksięgowano\nIdentyfikator operacji: BW08"
)


def test_history_can_identify_a_single_selected_settled_transaction():
    assert classify([SELECTED]) == "bank_transfer"


@pytest.mark.parametrize(
    "page",
    [
        SELECTED.replace("Zaksięgowano", "Oczekuje na potwierdzenie"),
        SELECTED.replace("Szczegóły wybranej transakcji", "Wyszukiwanie operacji"),
        SELECTED + "\n" + SELECTED[SELECTED.index("Szczegóły wybranej transakcji") :],
        SELECTED.replace("Status: Odrzucono", ACCOUNTS).replace(ACCOUNTS + "\nKwota", "Kwota"),
    ],
)
def test_history_needs_unambiguous_selection_and_local_settlement_evidence(page):
    assert classify([page]) is None


@pytest.mark.parametrize(
    ("heading", "day"),
    [("Dane operacji bankowej", "Data operacji"), ("Szczegóły zlecenia", "Data księgowania")],
)
def test_detail_screen_with_a_posted_ledger_reference_and_no_status_badge(heading, day):
    page = DETAIL.replace("Informacje o zleceniu przelewu", heading).replace(
        "Stan realizacji\nZaksięgowano", f"{day}: 15.04.2031"
    )
    assert classify([page]) == "bank_transfer"
    assert classify([page.replace(day, "Przewidywana data księgowania")]) is None
    assert classify([page.replace("Z rachunku", "Konto zwrotów")]) is None


@pytest.mark.parametrize(
    "state",
    [
        "Przyjęte do realizacji",
        "Czeka na podpis",
        "Nie zostało wykonane",
        "Do autoryzacji",
        "Do podpisu",
        "W przygotowaniu",
        "Wykonana częściowo",
    ],
)
def test_detached_pending_state_overrides_printed_dates(state):
    page = DETAIL.replace("Zaksięgowano", state) + "\nData księgowania: 15.04.2031"
    assert classify([page]) is None


def test_selected_operation_on_a_later_page_is_unique_across_the_statement():
    ledger, marker, detail = SELECTED.partition("Szczegóły wybranej transakcji")
    assert classify([ledger, marker + detail]) == "bank_transfer"
    assert classify([ledger, marker + detail, marker + detail]) is None


STACKED = (
    "Historia operacji\n"
    f"{ACCOUNTS}\nStan operacji: Wykonana\nData operacji: 07.09.2033\nKwota: 73,20 EUR\n"
    "Tytuł: Etap 4, umowa KL/83/32"
)


def test_one_settled_transfer_in_a_stacked_account_history():
    assert classify([STACKED]) == "bank_transfer"


@pytest.mark.parametrize(
    "distractor",
    [
        "\nKwota: 18,00 EUR",
        "\n05.09.2033 | Zakup | -83,00 EUR",
        "\nTytuł: Inna płatność",
        "\n09.04.2025 | Wypłata gotówki | -15,00",
        "\n12.04.2025\nKwota: 3,20",
    ],
)
def test_stacked_history_cannot_borrow_fields_from_another_payment(distractor):
    assert classify([STACKED + distractor]) is None


def test_executed_order_with_counterparty_and_booking_date_without_id():
    text = (
        "Dane zlecenia bankowego\nStatus zlecenia: wykonane\n"
        f"Rachunek zleceniodawcy: {PAYER}\nRachunek kontrahenta: {PAYEE}\n"
        "Kwota: 815,98 PLN\nData księgowania: 10.05.2032"
    )
    assert classify([text]) == "bank_transfer"


def test_unknown_detached_status_matches_the_inline_decision():
    page = DETAIL.replace("Stan realizacji\nZaksięgowano", "Status operacji: Weryfikacja ręczna")
    page += "\nData księgowania: 15.04.2031"
    assert classify([page]) is None
    assert classify([page.replace("Status operacji: ", "Status operacji\n")]) is None


@pytest.mark.parametrize(
    "state",
    ["Status: Wykonany 12.07.2030", "Status zlecenia\nWykonany 12.07.2030 09:48:12", "Stan realizacji: Wykonano 08:30"],
)
def test_completed_state_can_carry_a_timestamp(state):
    page = DETAIL.replace("Stan realizacji\nZaksięgowano", state)
    assert classify([page]) == "bank_transfer"
    assert classify([page.replace("Wykonan", "Częściowo wykonan")]) is None
