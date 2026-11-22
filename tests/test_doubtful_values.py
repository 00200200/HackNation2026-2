"""A model may only choose a printed alternative in the disputed field's own block."""

import json

import pytest

from kio2json import bank_transfer, engines, llm
from kio2json.class_config import load_classes
from kio2json.doubtful_values import reassess
from kio2json.endpoint_error import EndpointError


def test_one_schema_for_both_populated_payment_fields(monkeypatch):
    for key, value in {
        "API_KEY": "fixture",
        "BASE_URL": "https://example.invalid",
        "MODEL": "m",
        "MODE": "RL",
        "OUTPUT": "spans",
    }.items():
        monkeypatch.setenv("KIO_LLM_" + key, value)
    definition = next(c for c in load_classes() if c.id == "bank_transfer")
    page = (
        "Kwota: 80,10 PLN\nKwota przelewu: 79,90 PLN\nData zlecenia: 01.02.2025\nDzień wykonania przelewu: 03.02.2025"
    )
    record = bank_transfer.extract(page)
    record["przelew_bankowy"].update(tytul="Opłata", z_rachunku="1", na_rachunek="2", numer_transakcji="T/1")
    calls = []

    def choose(schema, instructions, prompt, **settings):
        fields = json.loads(prompt)["fields"]
        calls.append(fields)
        assert settings["single_request"]
        choices = {}
        for field, label in (("kwota", "Kwota przelewu"), ("data_operacji", "Dzień wykonania przelewu")):
            enum = schema.model_json_schema()["properties"][field]["enum"]
            assert "rule" in enum and "abstain" in enum
            for key, (printed_label, start, end, raw) in fields[field]["choices"].items():
                assert page[start:end] == raw and key in enum
                if printed_label == label:
                    choices[field] = key
        return schema(**choices)

    monkeypatch.setattr(llm, "structured", choose)
    out = engines.extract(definition, page, ocr_python=lambda: record, first_page=page, check_core_fields=True)
    assert len(calls) == 1
    assert (out["przelew_bankowy"]["kwota"], out["przelew_bankowy"]["data_operacji"]) == (79.9, "2025-02-03")


@pytest.mark.parametrize("response", ["rule", "abstain", "timeout"])
def test_failed_or_declined_choice_retains_prior(monkeypatch, response):
    def choose(schema, *args, **kwargs):
        if response == "timeout":
            raise EndpointError(TimeoutError())
        return schema(kwota=response)

    monkeypatch.setattr(llm, "structured", choose)
    page = "Kwota: 12,00\nKwota przelewu: 13,00"
    record = bank_transfer.extract(page)
    reassess("bank_transfer", record, page)
    assert record["przelew_bankowy"]["kwota"] == 12


@pytest.mark.parametrize("extra", ["Opłata: 10,00", "Kwota: 13,00", "Saldo: 17,00", "Kwota przelewu: 14,00 90,00"])
def test_unowned_or_ambiguous_amount_does_not_trigger(monkeypatch, extra):
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    page = "Kwota: 12,00\n" + extra
    reassess("bank_transfer", bank_transfer.extract(page), page)


def test_only_singleton_owner_can_get_a_shorter_printed_name(monkeypatch):
    page = "Odwołujący: Biały Las\nAdres siedziby: Polna 7\nZamawiający: Zielony Port\nul. Morska 9"
    rows = {"Odwolujacy": [{"nazwa": "Biały Las Adres siedziby"}], "Zamawiajacy": [{"nazwa": "Zielony Port"}]}

    def choose(schema, instructions, prompt, **kwargs):
        evidence = json.loads(prompt)
        assert evidence["owner"] == "Odwolujacy" and "Zielony" not in prompt
        return schema(nazwa="nazwa_1")

    monkeypatch.setattr(llm, "structured", choose)
    reassess("appeal", rows, page)
    assert rows["Odwolujacy"] == [{"nazwa": "Biały Las"}]
    rows["Odwolujacy"] *= 2
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    reassess("appeal", rows, page)


def test_branch_locality_can_complete_a_truncated_name(monkeypatch):
    name = "Towarzystwo Sosna Oddział Nadmorski"
    page = f"Zamawiający: {name}\nz siedzibą w Porcie\nul. Koralowa 8\nODWOŁANIE\nZarzuty:\n1. Wybór oferty"
    record = {"Zamawiajacy": [{"nazwa": name}]}
    monkeypatch.setattr(llm, "structured", lambda schema, *args, **kwargs: schema(nazwa="nazwa_1"))
    reassess("appeal", record, page)
    assert record["Zamawiajacy"][0]["nazwa"] == name + " z siedzibą w Porcie"


def test_posting_day_cannot_displace_a_narrative_execution_date(monkeypatch):
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    page = "Data księgowania: 03.06.2025\nWykonano przelew w dniu 02.06.2025"
    reassess("bank_transfer", {"przelew_bankowy": {"data_operacji": "2025-06-02"}}, page)


@pytest.mark.parametrize("extra", ["03 - 405 Doliny", "Małe Pole", "00—345 Doliny"])
def test_a_mailing_locality_cannot_extend_the_registered_name(monkeypatch, extra):
    page = f"Odwołujący: Różowy Koral S.A.\n{extra}\nul. Główna 7"
    record = {"Odwolujacy": [{"nazwa": "Różowy Koral S.A."}]}
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    reassess("appeal", record, page)


def test_receipt_cannot_replace_a_rule_from_an_unseen_page(monkeypatch):
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    page = "Kwota przelewu: 64,90\nData operacji: 07.04.2025"
    reassess("bank_transfer", {"przelew_bankowy": {"kwota": 95, "data_operacji": "2025-05-03"}}, page)


def test_fee_block_does_not_own_transaction_amount(monkeypatch):
    page = "Kwota przelewu: 89,00 PLN\nSzczegóły prowizji\nKwota: 4,00 PLN"
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    reassess("bank_transfer", bank_transfer.extract(page), page)


def test_procurement_subject_can_contain_a_named_project(monkeypatch):
    page = "Przedmiot zamówienia: Dostawa czujników w ramach projektu pod nazwą „Cicha Rzeka”\nZnak sprawy: X/2"
    record = {"ZamowieniePubliczne": {"tytul": "Cicha Rzeka"}}
    monkeypatch.setattr(llm, "structured", lambda schema, *args, **kwargs: schema(tytul="tytul_1"))
    reassess("appeal", record, page)
    assert record["ZamowieniePubliczne"]["tytul"] == "Dostawa czujników w ramach projektu pod nazwą „Cicha Rzeka”"
    record["ZamowieniePubliczne"]["tytul"] = "Inny przedmiot"
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    reassess("appeal", record, page)


def test_row_after_nested_project_is_not_part_of_purchase_title(monkeypatch):
    page = "Nazwa postępowania: Budowa sieci w ramach projektu pn. „Cicha Rzeka”\nWartość 500,00 zł\nNumer: AB/1"
    record = {"ZamowieniePubliczne": {"tytul": "Cicha Rzeka"}}
    monkeypatch.setattr(llm, "structured", lambda *args, **kwargs: pytest.fail("unexpected request"))
    reassess("appeal", record, page)
