from pathlib import Path

import pytest

from kio2json import bank_transfer, pipeline, power_of_attorney
from kio2json.classify import classify

GRANT = "Mocodawca: Miedziane Studio sp. z o.o. udziela pełnomocnictwa adw. Ewie Niebieskiej."
ACCOUNT = "87432198765432198765432123"
OTHER = "73" * 13


@pytest.mark.parametrize("heading", ["Osoba do kontaktu:", "Świadek:", "Dane koordynatora", "Biuro Obsługi:"])
def test_representation_role_under_a_foreign_heading_is_not_a_signature(heading):
    text = f"{GRANT}\n{heading}\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == []


@pytest.mark.parametrize("heading", ["Mocodawca:", "Podpis", "W imieniu Miedziane Studio sp. z o.o.:", "___________"])
def test_signature_evidence_stops_at_the_next_heading(heading):
    text = f"{GRANT}\n{heading}\nIga Biała\nOsoba do kontaktu:\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Iga Biała"}]


@pytest.mark.parametrize(
    ("fields", "expected", "route"),
    [
        (
            f"Informacja dla nadawcy: przelew na konto {ACCOUNT}\nRachunek nadawcy: ****\nRachunek odbiorcy: {ACCOUNT}",
            (None, ACCOUNT),
            "bank_transfer",
        ),
        (
            f"Informacja dla odbiorcy: konto {ACCOUNT}\nRachunek nadawcy: {ACCOUNT}\nRachunek odbiorcy: ****",
            (ACCOUNT, None),
            "bank_transfer",
        ),
        (
            f"Informacja dla nadawcy: konto {OTHER}\nRachunek nadawcy:\nRachunek odbiorcy: {ACCOUNT}",
            (None, ACCOUNT),
            "bank_transfer",
        ),
        (
            f"Konto archiwalne: {ACCOUNT}\nRachunek odbiorcy: {OTHER}\nRachunek nadawcy: {ACCOUNT}",
            (ACCOUNT, OTHER),
            "bank_transfer",
        ),
    ],
)
def test_only_the_labelled_occurrence_assigns_an_account(fields, expected, route):
    text = f"Potwierdzenie przelewu\n{fields}\nKwota: 17,25 PLN\nData operacji: 03.04.2025"
    assert classify([text]) == route
    result = bank_transfer.extract(text)["przelew_bankowy"]
    assert (result["z_rachunku"], result["na_rachunek"]) == expected


def test_masked_route_keeps_its_account_evidence_through_extraction(monkeypatch):
    pages = [
        (
            f"Potwierdzenie przelewu\nRachunek nadawcy: ****\nRachunek odbiorcy: {ACCOUNT}\n"
            "Kwota: 17,25 PLN\nData operacji: 03.04.2025"
        ),
        f"Informacje dodatkowe\nRachunek nadawcy: {OTHER}\nRachunek odbiorcy: {OTHER}",
    ]
    monkeypatch.setattr(pipeline, "read_pages", lambda *args, **kwargs: pages)
    label, result = pipeline.process_pdf(Path("przelew.pdf"))
    assert label == "bank_transfer"
    assert (result["przelew_bankowy"]["z_rachunku"], result["przelew_bankowy"]["na_rachunek"]) == (None, ACCOUNT)


@pytest.mark.parametrize(
    ("row", "expected"),
    [(f"**** {ACCOUNT}", (None, ACCOUNT)), (f"{ACCOUNT} ****", (ACCOUNT, None))],
)
def test_column_headers_bind_a_masked_cell_to_its_position(row, expected):
    record = bank_transfer.extract(f"Nadawca Odbiorca\n{row}")["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == expected


def test_missing_account_is_not_filled_from_a_different_field():
    text = f"Rachunek nadawcy:\nKod archiwalny: {OTHER}\nRachunek odbiorcy: {ACCOUNT}"
    record = bank_transfer.extract(text)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (None, ACCOUNT)


def test_unknown_principal_cannot_share_a_signature_by_name_suffix():
    text = GRANT + "\nW imieniu Inne Miedziane Studio sp. z o.o.:\nMira Różana"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == []


@pytest.mark.parametrize("rule", ["...................", "________________"])
def test_contact_line_under_its_own_heading_is_not_a_grantor_signature(rule):
    text = f"{GRANT}\nOsoba do kontaktu:\n{rule}\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == []


@pytest.mark.parametrize(
    "field", ["Osoba do kontaktu\n__________", "Osoba do kontaktu: __________", "Biuro Obsługi\n.............."]
)
def test_drawn_line_belongs_to_the_field_immediately_above_it(field):
    text = f"{GRANT}\n{field}\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == []


def test_signature_heading_covers_its_name_row_only():
    text = f"{GRANT}\nPodpis\nIga Biała\nBiuro Obsługi\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Iga Biała"}]


@pytest.mark.parametrize("title", [" – Prezes Zarządu", ", Prokurent", " (Dyrektor)"])
def test_named_signature_with_title_on_the_same_line(title):
    text = f"{GRANT}\nW imieniu Miedziane Studio sp. z o.o.:\n...................\nMira Różana{title}"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Mira Różana"}]


@pytest.mark.parametrize(
    "closing",
    [
        "Zakres pełnomocnictwa:\na) składania wniosków w\npostępowaniu.",
        "Upoważniam do odbioru dokumentacji.\nLeszno, 03.02.2031",
        "Zakres pełnomocnictwa:\n1. udzielania dalszych pełnomocnictw.\nmiejsce na pieczęć firmową",
    ],
)
def test_signer_after_the_closing_grant_clause_has_role_evidence(closing):
    text = f"{GRANT}\n{closing}\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Mira Różana"}]


def test_account_below_a_named_participant():
    fields = f"Nadawca: Miedziane Studio sp. z o.o.\n{OTHER}\nOdbiorca: Różane Studio sp. z o.o.\n{ACCOUNT}"
    assert bank_transfer._accounts(fields) == (OTHER, ACCOUNT)


def test_mask_and_number_with_explicit_labels_on_the_same_line():
    text = (
        f"Potwierdzenie przelewu\nRachunek nadawcy: **** Rachunek odbiorcy: {ACCOUNT}\n"
        "Kwota: 17,25 PLN\nData operacji: 03.04.2025"
    )
    assert classify([text]) == "bank_transfer"
    assert bank_transfer._accounts(text) == (None, ACCOUNT)


@pytest.mark.parametrize("mask", ["—", "XXXX"])
def test_masked_column_precedes_an_archive_field(mask):
    text = f"Nadawca Odbiorca\n{mask} {ACCOUNT}\nNr archiwalny {OTHER}"
    assert bank_transfer._accounts(text) == (None, ACCOUNT)


def test_ambiguous_single_cell_under_two_headers_cannot_borrow_an_archive_number():
    text = f"Nadawca Odbiorca\n{ACCOUNT}\nNr archiwalny {OTHER}"
    assert bank_transfer._accounts(text) == (None, None)


def test_adjacent_name_and_role_pairs_keep_the_signature_block_owner():
    text = f"{GRANT}\nPodpis\nIga Biała\nProkurent\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [
        {"imie_nazwisko": "Iga Biała"},
        {"imie_nazwisko": "Mira Różana"},
    ]


def test_signature_beside_attorney_acceptance_and_wrapped_grant():
    block = (
        "Zakres pełnomocnictwa:\n1. odbioru listów kierowanych do\nWykonawcy w sprawie.\nData 14 lipca 2030\n"
        ".....................\nMira Różana\nDyrektor"
    )
    assert power_of_attorney.extract(f"{GRANT}\n{block}")["mocodawca"][0]["podpisujacy"] == [
        {"imie_nazwisko": "Mira Różana"}
    ]
    parallel = "Mocodawca: Pełnomocnictwo przyjmuję:\n................ adw. Ewie Niebieskiej\nIga Biała"
    assert power_of_attorney.extract(f"{GRANT}\n{parallel}")["mocodawca"][0]["podpisujacy"] == [
        {"imie_nazwisko": "Iga Biała"}
    ]


@pytest.mark.parametrize("missing", ["", "XXXX", "—"])
def test_explicit_inline_field_after_a_missing_account(missing):
    assert bank_transfer._accounts(f"Rachunek nadawcy: {missing} Rachunek odbiorcy: {ACCOUNT}") == (None, ACCOUNT)


@pytest.mark.parametrize(
    "note",
    [
        "Kontakt w sprawie odbioru dokumentów.",
        "Osoba do odbioru dokumentów.",
        "Kontakt w sprawie\nodbioru dokumentów.",
        "Osoba do kontaktu:\nodbioru dokumentów.",
        "Mocodawca udziela informacji do kontaktu.",
        "Biuro udziela informacji o umocowaniu.",
        "Koordynator udziela informacji o pełnomocnictwach.",
        "Instrukcja składania odwołania.",
        "Osoba do kontaktu:\nZ poważaniem,\n...................",
    ],
)
def test_contact_note_mentioning_an_operational_action_cannot_support_a_signature(note):
    text = f"{GRANT}\n{note}\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == []


def test_formal_signoff_above_a_signature_rule_closes_the_grant():
    text = f"{GRANT}\nZ poważaniem,\n...................\nMira Różana\nDyrektor"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Mira Różana"}]
