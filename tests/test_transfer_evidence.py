import pytest

from kio2json.bank_transfer import extract
from kio2json.classify import classify

SENDER = "46137900000000000000471362"
RECIPIENT = "97298300000000000000836412"
ACCOUNT_FIELDS = f"Rachunek nadawcy: {SENDER}\nRachunek odbiorcy: {RECIPIENT}"
TRANSFER = f"Potwierdzenie przelewu\n{ACCOUNT_FIELDS}\nData obciążenia: 09.06.2026\nKwota: 782,14 PLN"


@pytest.mark.parametrize(
    "extra",
    [
        "Data księgowania Kwota\n10.06.2026 -782,14 PLN",
        "Konto zwrotu: 88381900000000000000026512",
        "Rachunek do rozliczenia prowizji: 88381900000000000000026512",
    ],
)
def test_independent_party_fields_survive_extra_banking_information(extra):
    text = f"{TRANSFER}\n{extra}"
    assert classify([text]) == "bank_transfer"
    record = extract(text)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (SENDER, RECIPIENT)


@pytest.mark.parametrize(
    "header, row",
    [
        ("Data waluty Data księgowania Kwota", "01.07.2026 02.07.2026 -14,88 PLN"),
        ("Kwota Data księgowania Data waluty", "-14,88 PLN 02.07.2026 01.07.2026"),
        ("Data księgowania Kwota Data waluty", "02.07.2026 -14,88 PLN 01.07.2026"),
    ],
)
def test_single_row_dates_are_bound_to_their_columns(header, row):
    text = f"Potwierdzenie wykonanej operacji\n{ACCOUNT_FIELDS}\n{header}\n{row}"
    assert classify([text]) == "bank_transfer"
    record = extract(text)["przelew_bankowy"]
    assert (record["data_operacji"], record["kwota"]) == ("2026-07-02", 14.88)
    explicit = text + "\nData operacji: 30.06.2026\nIdentyfikator transakcji: VR842317\nDzienny numer transakcji: 3"
    record = extract(explicit)["przelew_bankowy"]
    assert (record["data_operacji"], record["numer_transakcji"]) == ("2026-06-30", "VR842317")


def test_visible_tail_of_masked_payer_does_not_claim_the_payees_account():
    text = TRANSFER.replace(SENDER, "**** **** **** 1362")
    assert classify([text]) == "bank_transfer"
    record = extract(text)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (None, RECIPIENT)


LETTER = (
    f"Zaświadczenie o wykonaniu przelewu\nPoświadczamy, że 09.06.2026 obciążyliśmy konto {SENDER}\n"
    f"kwotą 782,14 PLN. Środki przekazaliśmy na konto {RECIPIENT}.\n"
    "Zapisana przez zleceniodawcę treść płatności: Dostawa magnesów.\n"
    "Pod identyfikatorem QJ684291 bank zarejestrował wykonanie dyspozycji."
)


def test_bank_letter_assigns_values_from_the_completed_payment():
    assert classify([LETTER]) == "bank_transfer"
    assert extract(LETTER)["przelew_bankowy"] == {
        "data_operacji": "2026-06-09",
        "kwota": 782.14,
        "z_rachunku": SENDER,
        "na_rachunek": RECIPIENT,
        "tytul": "Dostawa magnesów",
        "numer_transakcji": "QJ684291",
    }


@pytest.mark.parametrize("heading", ["Faktura VAT", "Wezwanie do zapłaty", "Wyciąg z rachunku"])
def test_embedded_bank_letter_does_not_reclassify_a_negative_document(heading):
    assert classify([heading + "\n" + LETTER]) is None


def test_negated_payment_is_not_completion_evidence():
    assert (
        classify([LETTER.replace("obciążyliśmy", "nie obciążyliśmy").replace("przekazaliśmy", "nie przekazaliśmy")])
        is None
    )


def test_two_ancillary_accounts_do_not_establish_payment_parties():
    text = (
        f"Potwierdzenie przelewu\nRachunek do zwrotów: {SENDER}\nKonto opłat: {RECIPIENT}\n"
        "Kwota: 45,17 PLN\nData operacji: 06.06.2026"
    )
    assert classify([text]) is None


@pytest.mark.parametrize(
    "note",
    ["Stan rachunku po operacji: 98,50 PLN", "Stan konta\n4 000,00 PLN", "Tytuł: Zwrot za usługę, której nie wykonano"],
)
def test_balance_and_free_text_do_not_change_execution_status(note):
    assert classify([TRANSFER + "\n" + note]) == "bank_transfer"


def test_explicit_bank_refusal_wins_over_account_details():
    assert classify([TRANSFER + "\nBank oświadcza, że nie wykonano przelewu."]) is None


def test_order_status_can_refuse_a_transfer():
    assert classify([TRANSFER + "\nStatus dyspozycji: odrzucona"]) is None


def test_dotted_field_leaders_do_not_hide_an_executed_status():
    assert classify([TRANSFER + "\nSTATUS ........ Wykonany"]) == "bank_transfer"


def test_undelimited_pending_status_can_have_several_words():
    assert classify([TRANSFER + "\nStatus oczekuje na realizację"]) is None


def test_explicit_identifier_accepts_separators_before_digits():
    text = TRANSFER + "\nIdentyfikator transakcji: TRX/2026/067821\nDzienny numer transakcji: 7"
    assert extract(text)["przelew_bankowy"]["numer_transakcji"] == "TRX/2026/067821"


def test_archive_reference_is_not_a_transaction_identifier():
    text = TRANSFER + "\nReferencja: 981/ARCH (archiwum wydruków)"
    assert extract(text)["przelew_bankowy"]["numer_transakcji"] is None


def test_wrapped_dash_between_words_preserves_the_space():
    assert extract(TRANSFER + "\nTytuł: Dostawa -\nrata druga")["przelew_bankowy"]["tytul"] == "Dostawa - rata druga"


def test_commission_account_cannot_fill_an_unprinted_payee_role():
    text = TRANSFER.replace("Rachunek odbiorcy:", "Rachunek do rozliczenia prowizji:")
    assert extract(text)["przelew_bankowy"]["na_rachunek"] is None


def test_currency_before_amount_in_a_booking_table():
    text = f"Potwierdzenie przelewu\n{ACCOUNT_FIELDS}\nKwota Data operacji\nPLN 782,14 09.06.2026"
    assert classify([text]) == "bank_transfer"
    fields = extract(text)["przelew_bankowy"]
    assert (fields["data_operacji"], fields["kwota"]) == ("2026-06-09", 782.14)


@pytest.mark.parametrize("payer,payee", [("Z konta", "Na konto"), ("Konto źródłowe", "Konto docelowe")])
def test_accounts_with_directional_labels(payer, payee):
    text = TRANSFER.replace("Rachunek nadawcy", payer).replace("Rachunek odbiorcy", payee)
    assert classify([text]) == "bank_transfer"
    record = extract(text)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (SENDER, RECIPIENT)


def test_conflicting_sender_in_second_ocr_read_does_not_complete_receipt(monkeypatch):
    from kio2json import pipeline

    first = (
        f"Potwierdzenie wykonanej operacji\nRachunek nadawcy: {SENDER}\nData operacji: 09.06.2026\nKwota: 782,14 PLN"
    )
    second = first.replace(SENDER, "88381900000000000000026512") + f"\nRachunek odbiorcy: {RECIPIENT}"

    def read(path, *, engine, ocr_pages=None, **kwargs):
        if ocr_pages is not None:
            ocr_pages.append(1)
        return [first if engine == "tesseract-dpi" else second]

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(pipeline, "DEFAULT_OCR_ENGINE", "tesseract-dpi")
    assert pipeline.process_pdf("document.pdf") == (None, {})


def test_internal_period_is_part_of_the_printed_reference():
    fields = extract(TRANSFER + "\nNumer transakcji: RM937411.05")["przelew_bankowy"]
    assert fields["numer_transakcji"] == "RM937411.05"


def test_state_about_authorization_does_not_deny_execution():
    assert classify([TRANSFER + "\nStan płatności: nie wymaga autoryzacji"]) == "bank_transfer"


def test_conditional_denial_can_continue_on_a_new_line():
    notice = "\nInformacja: Jeśli bank\nnie wykonał przelewu w terminie, prosimy o kontakt."
    assert classify([TRANSFER + notice]) == "bank_transfer"


def test_bank_can_introduce_a_refusal_with_a_colon():
    assert classify([TRANSFER + "\nBank informuje: nie wykonano przelewu."]) is None


@pytest.mark.parametrize(
    "statement",
    [
        "Przelew zrealizowano dnia 07.06.2026.",
        "W dniu 07.06.2026 wykonano przelew.",
        "Bank potwierdza, że przelew wykonano w dniu 07.06.2026.",
    ],
)
def test_execution_statement_precedes_debit_date_even_with_labelled_amount(statement):
    record = extract(TRANSFER + "\n" + statement)["przelew_bankowy"]
    assert (record["data_operacji"], record["kwota"]) == ("2026-06-07", 782.14)


@pytest.mark.parametrize(
    "note",
    [
        "Tytuł: Przelew zrealizowano dnia 07.06.2026.",
        "Tytuł: Opis faktury\nPrzelew zrealizowano dnia 07.06.2026.",
        "Przelew zrealizowano zgodnie z umową z dnia 07.06.2026.",
        "W dniu 07.06.2026 nie wykonano przelewu.",
        "W dniu 07.06.2026 wykonano przelew?",
        "Jeżeli rachunek był aktywny,\nw dniu 07.06.2026 wykonano przelew.",
    ],
)
def test_unrelated_date_does_not_displace_debit_date(note):
    assert extract(TRANSFER + "\n" + note)["przelew_bankowy"]["data_operacji"] == "2026-06-09"


@pytest.mark.parametrize(
    "status",
    ["Status operacji: Rozliczona", "Status realizacji: Zakończona", "Status płatności: Zapłacona"],
)
def test_completed_status_on_an_evidenced_confirmation(status):
    assert classify([TRANSFER + "\n" + status]) == "bank_transfer"
    assert classify([TRANSFER.replace("Potwierdzenie przelewu", "Wezwanie do zapłaty") + "\n" + status]) is None
    assert classify([TRANSFER + "\n" + status + " częściowo"]) is None
