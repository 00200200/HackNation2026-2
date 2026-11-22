import pytest

from kio2json.classify import classify
from kio2json.history_routing import settled_history

LEDGER = """Wyciąg bankowy za luty
Właściciel rachunku: Spółka Piasek
Odbiorca: Biuro Nurt
Data waluty | Strona | Treść zapisu | PLN
11.02.2034 | Wn | Przelew, wpis od odwołania | 810,30
Saldo po operacji: 8 992,10 PLN"""

PRINTED_CELLS = """Rachunek bieżący
Data operacji
2031-03-09
Data księgowania
2031-03-10
Przelew krajowy    −180,50 zł
Z rachunku: 33 1555 0000 1020 2020 3030 9393
Na rachunek: 91 3111 0000 4060 7070 5050 0202
Tytułem: opłata skarbowa w sprawie WN/28
Data wydruku: 2031-03-11"""


@pytest.mark.parametrize(
    "text",
    [
        LEDGER,
        PRINTED_CELLS,
        """Historia obrotów
Dzień księgowania | Obciążenie (PLN) | Tytuł
17/03/2030 | 470,16 | Wpis od odwołania w postępowaniu RD-16
""",
    ],
)
def test_single_booked_entry(text):
    assert settled_history([text])


def test_explicit_checkmark_selects_one_dated_debit():
    other = "12.02.2034 | Ma | Zwrot zaliczki | 17,00"
    text = LEDGER.replace("11.02.2034", f"{other}\n[x] 11.02.2034")
    assert settled_history([text])


@pytest.mark.parametrize(
    "extra",
    [
        "11.02.2034 | Wn | Przelew na ten sam cel | 810,30",
        "12.02.2034 | Ma | Uznanie rachunku",
        "Przelew do innego dostawcy     160,00",
    ],
)
def test_extra_unselected_posting_anywhere_in_document(extra):
    assert not settled_history([LEDGER, extra])


def test_monthly_summary_amount_is_not_a_transaction():
    assert not settled_history([LEDGER.replace(" | 810,30", "")])


def test_scheduled_debits_have_no_posting_evidence():
    text = LEDGER.replace("Wyciąg bankowy za luty", "Historia dyspozycji").replace(
        "Data waluty", "Przewidywana data księgowania"
    )
    assert not settled_history([text])


def test_single_credit_for_a_refund_does_not_prove_an_outgoing_fee():
    text = LEDGER.replace("Wn | Przelew, wpis od odwołania", "Ma | Zwrot opłaty")
    assert not settled_history([text])


def test_selection_must_belong_to_the_payment():
    text = LEDGER.replace("11.02.2034", "[x] 12.02.2034 | Ma | Zwrot zaliczki | 17,00\n11.02.2034")
    assert not settled_history([text])


def test_iso_date_is_not_a_minus_sign_on_a_refund():
    text = LEDGER.replace("11.02.2034", "2034-02-11").replace("Wn | Przelew, wpis od odwołania", "Ma | Zwrot opłaty")
    assert not settled_history([text])


def test_booking_column_and_remittance_identify_payment_without_a_history_title():
    text = """Rachunek rozliczeniowy w PLN
Posiadacz: Zakład Fala
Dzień księgowania | Kontrahent | Tytuł płatności | Wartość
2031-02-04 | Gmina Głaz | Opłata skarbowa za pełnomocnictwo | 53,70"""
    assert settled_history([text])


def test_date_amount_and_account_heading_with_signed_remittance():
    text = """Rachunek nr 33 1555 0000 1020 2020 3030 9393
Data | Treść | Kwota w PLN
2033-08-19  Wpis od odwołania, znak UR/703  −305,70"""
    assert settled_history([text])


def test_unsigned_credit_is_not_a_debit_just_because_table_lists_both_sides():
    text = """Historia rachunku
Data operacji | Obciążenie | Uznanie | Tytuł
2031-04-15 | — | 120,50 zł | Zwrot opłaty"""
    assert not settled_history([text])


def test_balance_currency_does_not_supply_the_transaction_currency():
    assert not settled_history([LEDGER.replace("Treść zapisu | PLN", "Treść zapisu | Wartość")])


@pytest.mark.parametrize(
    "detail",
    [
        PRINTED_CELLS.replace("opłata skarbowa w sprawie WN/28", "dostawa tektury"),
        "Szczegóły przelewu\n" + PRINTED_CELLS,
    ],
)
def test_full_statement_does_not_confirm_an_embedded_payment_detail(detail):
    assert not settled_history(["Wyciąg z rachunku\n" + detail])


def test_full_statement_with_one_visibly_dated_transaction_row():
    text = LEDGER.replace("wpis od odwołania", "dostawa tektury")
    assert settled_history([text])


def test_split_balance_does_not_count_as_a_second_posting():
    assert settled_history([LEDGER.replace("Saldo po operacji: ", "Saldo po operacji:\n")])


def test_booking_date_printed_account_and_case_remittance_identify_a_single_debit():
    text = """Wydruk dla posiadacza
Rachunek 33 1555 0000 1020 2020 3030 9393
Dzień księgowania: 17.07.2031
Treść: Wpis w postępowaniu JN/4
Kwota obciążenia – 32,10 PLN"""
    assert settled_history([text])


@pytest.mark.parametrize("heading", ["Pismo przewodnie", "Pro forma", "Wniosek o zwrot"])
def test_document_quoting_a_posted_ledger_stays_empty(heading):
    assert classify([LEDGER]) == "bank_transfer"
    assert classify([heading + "\n" + LEDGER]) is None


def test_ledger_quoted_after_an_enclosure_list_stays_empty():
    letter = "\n".join(["Biuro wykonawcy"] + ["Dalsza treść pisma."] * 8 + ["W załączeniu:"])
    assert classify([letter, LEDGER]) is None
