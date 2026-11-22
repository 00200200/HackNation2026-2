"""Ground payment fields in the bank's execution clause, including wrapped bank accounts."""

import pytest

from kio2json import bank_transfer
from kio2json.ocr_accounts import account_evidence

SENDER = "PL78351200009981234567890123"
RECIPIENT = "56458700991234567801234567"
LETTER = f"""Zaświadczenie bankowe
Gdańsk, 15.11.2031
Poświadczamy realizację płatności dnia 11.11.2031 z konta nr {SENDER}
w wysokości 82,35 EUR na konto {RECIPIENT[:22]}
{RECIPIENT[22:]} prowadzone na rzecz wykonawcy.
Tytuł płatności: Udział w przetargu MT/60
Z wyrazami szacunku,
Biuro Obsługi"""


def test_attested_execution_binds_only_payment_date_and_roles_across_wrapped_lines():
    assert bank_transfer.extract(LETTER)["przelew_bankowy"] == {
        "data_operacji": "2031-11-11",
        "kwota": 82.35,
        "z_rachunku": SENDER,
        "na_rachunek": RECIPIENT,
        "tytul": "Udział w przetargu MT/60",
        "numer_transakcji": None,
    }


def test_prose_roles_survive_scanned_receipt_account_processing():
    evidence = account_evidence(LETTER)
    assert (evidence.sender, evidence.recipient) == (SENDER, RECIPIENT)


@pytest.mark.parametrize("intro", ["Nie poświadczamy", "Czy poświadczamy", "Prosimy o"])
def test_absent_execution_attestation_supplies_no_date_or_amount(intro):
    fields = bank_transfer.extract(LETTER.replace("Poświadczamy", intro))["przelew_bankowy"]
    assert fields["data_operacji"] is fields["kwota"] is None


def test_explicit_attested_payment_day_takes_priority_over_posting_day():
    page = LETTER.replace("Zaświadczenie bankowe", "Zaświadczenie bankowe\nData księgowania: 12.11.2031")
    assert bank_transfer.extract(page)["przelew_bankowy"]["data_operacji"] == "2031-11-11"


def test_newline_before_a_directional_account_does_not_end_execution_evidence():
    page = LETTER.replace(" z konta nr ", "\nz konta nr ").replace(" na konto ", "\nna konto ")
    fields = bank_transfer.attested_payment_fields(page)
    assert (fields["kwota"], fields["z_rachunku"], fields["na_rachunek"]) == (82.35, SENDER, RECIPIENT)


def test_ocr_role_label_and_complete_iban_may_occupy_separate_lines():
    page = LETTER.replace("z konta nr ", "z rachunku nr ").replace("na konto ", "na rachunek nr\nPL")
    evidence = account_evidence(page)
    assert evidence.recipient == "PL" + RECIPIENT
