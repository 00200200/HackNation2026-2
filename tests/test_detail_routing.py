import pytest

from kio2json.detail_routing import settled_details

PAYER = "23 4000 1500 3100 8000 1100 9200"
PAYEE = "67 2000 1300 7100 4000 9900 5400"

ORDER = f"""Bank Testowy • Panel klienta
Moje dyspozycje / podgląd zlecenia
Rodzaj: przelew krajowy
Rachunek płatnika | Rachunek beneficjenta
{PAYER}  {PAYEE}
Planowana data wykonania: 03.03.2035
Stan dyspozycji
| * Zrealizowana
Kwota: 417,28 PLN
Tytuł: wadium do sprawy T/33
"""

OPERATION = f"""Bank Testowy
Operacja na rachunku
Typ płatności                   przelew wychodzący
Strona Winien                    Strona Ma
{PAYER}             {PAYEE}
Dzień obciążenia
3 marca 2035
Waluta i wartość                 −417,28 PLN
Informacja dla beneficjenta       wadium do sprawy T/33
"""

DATED_RECORD = f"""Bank Testowy
Karta operacji
Identyfikator transakcji: TR-802/43
Dzień transakcji: 12.07.2034
Konto płatnika {PAYER}
Konto odbiorcy {PAYEE}
Kwota 912,15 PLN
Tytuł płatności: licencja do umowy UM/55
"""


@pytest.mark.parametrize("record", [ORDER, OPERATION])
def test_details_route_one_settled_transaction(record):
    assert settled_details([record])


def test_no_heading_but_bank_fields_declare_a_single_posted_transfer():
    record = OPERATION.replace("Operacja na rachunku\n", "")
    assert settled_details([record])


def test_decorated_status_cell_may_survive_a_missing_status_caption():
    record = ORDER.replace("Stan dyspozycji\n| * Zrealizowana", "» Zrealizowana")
    assert settled_details([record])


def test_bank_detail_can_identify_a_payment_without_the_literal_transfer_type():
    record = ORDER.replace("Rodzaj: przelew krajowy", "Kanał mobilny").replace(PAYER, "23 … 9200")
    assert settled_details([record])


def test_negative_or_unfilled_actual_date_does_not_inherit_order_date():
    record = ORDER.replace("Planowana data wykonania", "Data dyspozycji").replace(
        "Stan dyspozycji\n| * Zrealizowana", "Data wykonania: —"
    )
    assert not settled_details([record])


def test_status_or_payment_date_may_be_the_only_dated_cell():
    record = OPERATION.replace("3 marca 2035", "3 września 2035")
    assert settled_details([record])


def test_past_operation_date_belongs_to_a_typed_outgoing_debit():
    record = OPERATION.replace("Dzień obciążenia", "Data operacji")
    assert settled_details([record])


@pytest.mark.parametrize("date_label", ["Dzień transakcji", "Data operacji"])
def test_dated_operation_has_a_bank_transaction_identifier_and_remittance(date_label):
    assert settled_details([DATED_RECORD.replace("Dzień transakcji", date_label)])


@pytest.mark.parametrize(
    ("printed", "replacement"),
    [
        ("Karta operacji", "Podgląd zlecenia"),
        ("Karta operacji", "Polecenie przelewu"),
        ("Dzień transakcji", "Planowany dzień transakcji"),
        ("Dzień transakcji", "Data przyjęcia dyspozycji"),
        ("Identyfikator transakcji", "Identyfikator wniosku"),
        ("TR-802/43", "—"),
        ("Konto płatnika", "Pierwsze konto"),
        ("Tytuł płatności: licencja do umowy UM/55", "Tytuł płatności: —"),
        ("Karta operacji", "Karta operacji\nRodzaj: wypłata z bankomatu"),
    ],
)
def test_dated_operation_needs_posted_payment_evidence(printed, replacement):
    assert not settled_details([DATED_RECORD.replace(printed, replacement)])


def test_typed_card_debit_is_not_a_payment_transfer():
    record = OPERATION.replace("przelew wychodzący", "płatność kartą")
    assert not settled_details([record])


def test_free_text_note_with_case_number_cannot_substitute_for_two_accounts():
    record = ORDER.replace(PAYER, PAYEE)
    assert not settled_details([record])


def test_booked_bank_order_with_two_damaged_account_numbers():
    record = ORDER.replace(PAYER, "23 4000 … 9200").replace(PAYEE, "67 2000 … 5400")
    assert settled_details([record])


def test_empty_account_cells_do_not_support_a_transfer():
    record = ORDER.replace(PAYER, "—").replace(PAYEE, "—")
    assert not settled_details([record])


def test_currency_beside_a_separate_amount_cell():
    record = ORDER.replace("Kwota: 417,28 PLN", "Waluta: PLN\nWartość: 417,28")
    assert settled_details([record])


def test_detail_can_print_a_status_column_beside_other_labels():
    record = ORDER.replace("Stan dyspozycji\n| * Zrealizowana", "Stan dyspozycji | kanał\nZrealizowana | mobilny")
    assert settled_details([record])


def test_date_can_appear_between_the_words_in_its_caption():
    record = OPERATION.replace("Dzień obciążenia\n3 marca 2035", "Data   2035-03-03\nksięgowania")
    assert settled_details([record])


@pytest.mark.parametrize("status", ["Złożona", "Wysłana do banku", "Oczekuje na autoryzację", "Odrzucona"])
def test_requested_execution_date_does_not_confirm_settlement(status):
    assert not settled_details([ORDER.replace("Zrealizowana", status)])


@pytest.mark.parametrize(
    "date_cell",
    [
        "Data wykonania: 03.03.2035 (planowana)",
        "Wybrana data realizacji: 03.03.2035",
        "Data realizacji: 03.03.2035 — żądana przez klienta",
        "Wskazana przez płatnika data wykonania: 03.03.2035",
    ],
)
def test_qualified_execution_date_does_not_prove_an_order_was_settled(date_cell):
    page = ORDER.replace("Planowana data wykonania: 03.03.2035", date_cell)
    assert not settled_details([page.replace("| * Zrealizowana", "")])
    assert settled_details([page])


@pytest.mark.parametrize("separator", ["\n", " | ", "    "])
def test_planned_date_in_an_adjacent_field_does_not_qualify_actual_booking(separator):
    dates = f"Data księgowania: 04.03.2035{separator}Wybrana data realizacji: 03.03.2035"
    page = ORDER.replace("Planowana data wykonania: 03.03.2035", dates).replace("| * Zrealizowana", "")
    assert settled_details([page])


def test_payment_purpose_cannot_confirm_execution():
    record = ORDER.replace("| * Zrealizowana", "").replace("wadium do sprawy T/33", "wykonana usługa nr 80")
    assert not settled_details([record])


def test_future_booking_date_does_not_confirm_settlement():
    record = OPERATION.replace("Dzień obciążenia", "Przewidywany dzień obciążenia")
    assert not settled_details([record])


def test_two_payment_rows_are_ambiguous_even_with_the_same_value():
    assert not settled_details([OPERATION + "\n04.03.2035 | inny przelew wychodzący | −417,28 PLN"])


def test_parties_and_amount_without_bank_payment_context_are_insufficient():
    record = OPERATION.replace("Bank Testowy\nOperacja na rachunku\n", "").replace(
        "Typ płatności                   przelew wychodzący\n", ""
    )
    assert not settled_details([record])
