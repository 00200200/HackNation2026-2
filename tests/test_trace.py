"""--explain writes a sidecar trace and leaves the organizer JSON unchanged."""

import json
from pathlib import Path

import pytest

from kio2json import pipeline
from kio2json.batch import read_document
from kio2json.class_config import load_classes
from kio2json.trace import field_source, value_pattern

RECEIPT = """Potwierdzenie przelewu
Rachunek nadawcy: PL11 1111 1111 1111 1111 1111 1111
Rachunek odbiorcy: PL22 2222 2222 2222 2222 2222 2222
Kwota: 15 000,00 PLN
Data operacji: 9 października 2025
Tytuł: wpis od odwołania
w postępowaniu ZP.1.2025
Numer referencyjny: ABC123456789
"""


def fake_reader(text: str, scanned: list[int]):
    def read_pages(path, *, ocr_pages, **kwargs):
        ocr_pages.extend(scanned)
        return [text, "Informacja dodatkowa"]

    return read_pages


@pytest.mark.parametrize("scanned, engine", [([], "rule"), ([1], "ocr")])
def test_receipt_trace_names_route_page_snippet_and_engine(monkeypatch, scanned, engine):
    monkeypatch.setattr(pipeline, "read_pages", fake_reader(RECEIPT, scanned))
    classes = load_classes()
    plain = read_document(Path("doc.pdf"), classes)
    explained = read_document(Path("doc.pdf"), classes, explain=True)
    assert plain.trace is None
    assert explained.text == plain.text and explained.label == plain.label == "bank_transfer"

    trace = explained.trace
    assert trace["class"] == "bank_transfer"
    assert trace["routing"]["router"] == "rules"
    assert trace["routing"]["cue"] == {"page": 1, "line": "Potwierdzenie przelewu"}
    assert trace["pages"] == {"read": 2, "ocr": scanned}
    fields = {f["field"]: f for f in trace["fields"]}
    assert set(fields) == {f"przelew_bankowy.{key}" for key in json.loads(plain.text)["przelew_bankowy"]}
    assert fields["przelew_bankowy.kwota"]["snippet"] == "Kwota: 15 000,00 PLN"
    assert fields["przelew_bankowy.data_operacji"]["snippet"] == "Data operacji: 9 października 2025"
    assert fields["przelew_bankowy.na_rachunek"]["snippet"].startswith("Rachunek odbiorcy:")
    assert fields["przelew_bankowy.tytul"]["snippet"] == "Tytuł: wpis od odwołania\nw postępowaniu ZP.1.2025"
    found = [f for f in fields.values() if f["value"] is not None]
    assert {f["page"] for f in found} == {1}
    assert {f["engine"] for f in found} == {engine}
    assert all(f["note"] == "no value extracted" for f in fields.values() if f["value"] is None)


def test_unrelated_document_has_no_route_or_fields(monkeypatch):
    monkeypatch.setattr(pipeline, "read_pages", fake_reader("Faktura VAT nr 1/2025", []))
    result = read_document(Path("doc.pdf"), load_classes(), explain=True)
    assert result.text == "{}\n"
    assert result.trace == {"class": None, "routing": None, "pages": None, "fields": [], "warnings": []}


@pytest.mark.parametrize(
    "value, text",
    [
        ("2025-03-04", "Warszawa, dnia 4.03.2025 r."),
        ("2025-03-14", "14 marca 2025"),
        (1234.5, "kwota 1 234,50 zł"),
        ("5260250995", "NIP: 526-025-09-95"),
        ("Gmina Mosty", "Zamawiający: GMINA\nMOSTY"),
    ],
)
def test_value_patterns_accept_printed_forms(value, text):
    assert value_pattern(value).search(text)


def test_unlocated_and_derived_values_say_so():
    missing = field_source("a.nazwa", "Nieobecna", ["inny tekst"], [], [("python", {"a": {"nazwa": "Nieobecna"}})])
    assert (missing["page"], missing["snippet"], missing["engine"]) == (None, None, "rule")
    assert missing["note"] == "value not found verbatim in the text read"
    code = field_source("a.id", 7, ["7"], [], [])
    assert code["page"] is None and code["engine"] is None
    assert code["note"] == "derived code or flag, not a printed value; producing engine not recorded"
