"""Account-history rows bind the debit to its own operation day."""

import pytest

from kio2json import bank_transfer

HEADER = "Data operacji | Opis transakcji | Kwota"
DEBIT = "04.06.2033 | Przelew wychodzący | −361,45 PLN"
BODY = """Z rachunku: 56458700991234567801234567
Na rachunek: 78351200009981234567890123
Tytuł: Zaliczka w sprawie TT-4/2033"""


def test_history_binds_the_date_and_amount_in_one_row_without_taking_description_heading_as_title():
    text = f"Historia rachunku\n{HEADER}\n{DEBIT}\n{BODY}"
    fields = bank_transfer.extract(text)["przelew_bankowy"]
    assert (fields["data_operacji"], fields["kwota"], fields["tytul"]) == (
        "2033-06-04",
        361.45,
        "Zaliczka w sprawie TT-4/2033",
    )


@pytest.mark.parametrize("extra", [DEBIT, "05.06.2033 | Prowizja | −1,20 PLN", "05.06.2033 | Wpłata | 120,00 PLN"])
def test_ledger_with_competing_rows_does_not_supply_payment_amount_or_day(extra):
    fields = bank_transfer.extract(f"{HEADER}\n{DEBIT}\n{extra}\n{BODY}")["przelew_bankowy"]
    assert fields["kwota"] is fields["data_operacji"] is None


def test_executed_order_field_qualifies_date_with_order_and_preserves_number():
    text = f"""Szczegóły dyspozycji
Rodzaj zlecenia: przelew krajowy
Status zlecenia: wykonane
Data wykonania zlecenia: 08.06.2033
Data przyjęcia: 06.06.2033
Identyfikator zlecenia: PK-7183
{BODY}"""
    fields = bank_transfer.extract(text)["przelew_bankowy"]
    assert (fields["data_operacji"], fields["numer_transakcji"]) == ("2033-06-08", "PK-7183")


def test_operation_details_skip_empty_description_heading_before_printed_transfer_title():
    page = f"Szczegóły operacji\nOpis\n{BODY}\nTyp transakcji: przelew"
    assert bank_transfer.extract(page)["przelew_bankowy"]["tytul"] == "Zaliczka w sprawie TT-4/2033"


def test_payment_reference_takes_precedence_over_bank_order_number():
    page = "Status zlecenia: zrealizowane\nIdentyfikator zlecenia: PK-7183\nID transakcji: DP-92"
    assert bank_transfer.extract(page)["przelew_bankowy"]["numer_transakcji"] == "DP-92"
    assert bank_transfer.extract("Identyfikator zlecenia: PK-7183")["przelew_bankowy"]["numer_transakcji"] is None


def test_detached_history_headers_leave_room_for_explicit_remittance_title():
    text = f"Data operacji: 04.06.2033\nOpis transakcji | Kwota\nPrzelew szybki -361,45 PLN\n{BODY}"
    fields = bank_transfer.extract(text)["przelew_bankowy"]
    assert fields["tytul"] == "Zaliczka w sprawie TT-4/2033"


def test_separate_booking_day_keeps_its_priority_below_the_execution_day():
    text = "Data księgowania: 05.06.2033\nOpis Kwota\nPrzelew zewnętrzny -30,00 PLN\nPrzelew wykonano dnia 04.06.2033."
    assert bank_transfer.extract(text)["przelew_bankowy"]["data_operacji"] == "2033-06-04"


def test_marked_detail_owns_its_fields_among_other_statement_transactions():
    page = f"""Bank Zielonego Szlaku
Historia transakcji
Data operacji: 04.06.2033
Kwota: 361,45 PLN
ID transakcji: LS-45
{BODY}
Szczegóły wybranej operacji
Data operacji: 02.05.2033
Kwota: 96,85 PLN
Na rachunek: 67249000008900000001901817
ID transakcji: MG-897
Tytuł: Kaucja w sprawie SE-66
Pozostałe transakcje
{BODY}"""
    assert bank_transfer.extract(page)["przelew_bankowy"] == {
        "kwota": 96.85,
        "data_operacji": "2033-05-02",
        "tytul": "Kaucja w sprawie SE-66",
        "numer_transakcji": "MG-897",
        "z_rachunku": None,
        "na_rachunek": "67249000008900000001901817",
    }


def test_selected_detail_stops_before_another_table_starts():
    text = f"""Historia rachunku
Wybrany przelew:
{BODY}
{HEADER}
{DEBIT}
ID transakcji: LS-711"""
    fields = bank_transfer.extract(text)["przelew_bankowy"]
    assert fields["tytul"] == "Zaliczka w sprawie TT-4/2033"
    assert fields["numer_transakcji"] is fields["kwota"] is fields["data_operacji"] is None


def test_marked_transactions_on_two_pages_are_ambiguous():
    section = "Wybrana operacja:\n" + BODY
    assert bank_transfer.selected_history_section("Historia rachunku\n" + section + "\n\n" + section) is None


def test_printed_daily_transaction_number_beats_a_separate_order_identifier():
    page = "Status zlecenia: zrealizowane\nIdentyfikator zlecenia: PK-7183\nDzienny numer transakcji: 32"
    assert bank_transfer.extract(page)["przelew_bankowy"]["numer_transakcji"] == "32"


@pytest.mark.parametrize(
    ("header", "row"),
    [
        ("Kwota | Rodzaj operacji | Data księgowania", "−361,45 PLN | Przelew krajowy | 04.06.2033"),
        ("Treść operacji | Obciążenie/Uznanie | Data operacji", "Przelew wychodzący | 361,45 PLN | 04.06.2033"),
        ("Data operacji | Kwota obciążenia | Opis", "04.06.2033 | 361,45 PLN | Przelew krajowy"),
    ],
)
def test_history_binds_permuted_date_direction_and_amount_columns(header, row):
    page = f"Historia operacji\n{header}\n{row}\n{BODY}"
    fields = bank_transfer.extract(page)["przelew_bankowy"]
    assert (fields["kwota"], fields["data_operacji"]) == (361.45, "2033-06-04")


def test_an_unsigned_credit_or_extra_booking_cannot_be_a_unique_debit():
    h = "Kwota | Treść operacji | Data księgowania"
    row = "361,45 PLN | Przelew przychodzący | 04.06.2033"
    assert bank_transfer.history_debit_fields(h + "\n" + row) == {}
    assert bank_transfer.history_debit_fields(h + "\n" + row.replace("przychodzący", "wychodzący") + "\n" + row) == {}


def test_ordering_party_and_counterparty_bind_a_completed_outgoing_order():
    from kio2json.ocr_accounts import account_evidence

    p = (
        "Szczegóły zlecenia\nStatus zlecenia: wykonane\nRachunek zleceniodawcy: 56458700991234567801234567\n"
        "Rachunek kontrahenta: 78351200009981234567890123\nKwota: 96,12 PLN"
    )
    for f in (bank_transfer.printed_accounts(p), vars(account_evidence(p))):
        assert (f.get("sender"), f.get("recipient")) == ("56458700991234567801234567", "78351200009981234567890123")


def test_single_ledger_payment_can_carry_its_booked_state_outside_unsigned_money_cell():
    text = "Data | Treść transakcji | Kwota\n04.06.2033 | Przelew SEPA | 11,35 EUR\nStatus operacji: zaksięgowana"
    assert bank_transfer.history_debit_fields(text) == {"data_operacji": "2033-06-04", "kwota": 11.35}
    assert bank_transfer.history_debit_fields(text.replace("zaksięgowana", "do autoryzacji")) == {}


def test_booked_date_stays_below_execution_day_even_inside_a_ledger_row():
    page = "Data księgowania Opis Kwota\n05.06.2033 Przelew szybki -30,00 PLN\nPrzelew wykonano dnia 04.06.2033."
    assert bank_transfer.extract(page)["przelew_bankowy"]["data_operacji"] == "2033-06-04"


def test_second_row_without_repeated_currency_still_invalidates_single_transaction():
    assert bank_transfer.history_debit_fields(HEADER + "\n" + DEBIT + "\n22.06.2033 | Serwis karty | -8,00") == {}


@pytest.mark.parametrize(
    "row",
    ["Prowizja za kartę | -8,00", "Przelew SEPA | -3,99 CHF", "Przelew SEPA -8,00", "Wpłata gotówkowa 14,00"],
)
def test_two_column_history_cannot_ignore_another_amount_cell(row):
    page = "Data operacji: 09.08.2033\nOpis Kwota\nPrzelew krajowy -92,28 PLN\n" + row
    assert bank_transfer.history_debit_fields(page) == {}


@pytest.mark.parametrize("extra", ["Saldo po operacji: 419,32 PLN", "Opłata bankowa: 2,50 PLN"])
def test_labelled_balance_and_bank_fee_after_the_debit_are_not_other_entries(extra):
    page = "Potwierdzenie przelewu\nData operacji: 08.04.2033\nOpis Kwota\nPrzelew internetowy -92,28 PLN\n" + extra
    assert bank_transfer.extract(page)["przelew_bankowy"]["kwota"] == 92.28
