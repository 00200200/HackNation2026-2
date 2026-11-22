"""The class file decides the fields of an organizer class's record, without a change to Python (#104)."""

import json
import shutil
from pathlib import Path

import pytest

from kio2json import engines, trace
from kio2json.batch import read_document
from kio2json.class_config import class_sources, parse_classes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "uzp" / "dane"
CLASS_OF = {"Odwolujacy": "appeal", "mocodawca": "power_of_attorney", "przelew_bankowy": "bank_transfer"}
WALUTA = 'waluta = { type = "string", instruction = "Currency code.", pattern = \'[0-9][0-9 ,.]* (PLN|EUR)\' }\n'


def edited_classes(tmp_path: Path, name: str, edit) -> list:
    """The shipped class files with one of them edited, loaded as KIO_CLASSES_DIR would load the copy."""
    folder = tmp_path / "classes"
    shutil.copytree(ROOT / "config" / "classes", folder)
    path = folder / name
    path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
    return parse_classes(class_sources(folder))


def read(pdf: Path, classes) -> dict:
    return json.loads(read_document(pdf, classes).text)


def test_a_class_file_adds_and_removes_fields_of_the_transfer(tmp_path):
    def edit(text: str) -> str:
        kept = "".join(line for line in text.splitlines(keepends=True) if not line.startswith("numer_transakcji = "))
        return kept + WALUTA

    pdf = DATA / "przyklad_01" / "przelew.pdf"
    payment = read(pdf, edited_classes(tmp_path, "bank_transfer.toml", edit))["przelew_bankowy"]
    default = read(pdf, parse_classes(class_sources()))["przelew_bankowy"]
    assert "numer_transakcji" not in payment and payment["waluta"] == "PLN"
    assert list(payment) == [key for key in default if key != "numer_transakcji"] + ["waluta"]
    assert {key: payment[key] for key in default if key != "numer_transakcji"} == {
        key: value for key, value in default.items() if key != "numer_transakcji"
    }


def test_a_field_added_to_list_rows_comes_out_null(tmp_path):
    def edit(text: str) -> str:
        line = 'przez-pelnomocnika = { grounding = "przez-pelnomocnika"'
        return text.replace(line, 'adres = { type = "string", instruction = "Address." }\n' + line, 1)

    pdf = DATA / "przyklad_01" / "odwolanie.pdf"
    record = read(pdf, edited_classes(tmp_path, "appeal.toml", edit))
    default = read(pdf, parse_classes(class_sources()))
    row = record["Odwolujacy"][0]
    assert list(row)[:5] == ["krs", "nazwa", "nip", "regon", "adres"] and row["adres"] is None
    assert {key: value for key, value in row.items() if key != "adres"} == default["Odwolujacy"][0]
    assert {key: value for key, value in record.items() if key != "Odwolujacy"} == {
        key: value for key, value in default.items() if key != "Odwolujacy"
    }


def test_a_class_file_pattern_fills_an_amount_the_rules_left_empty(tmp_path):
    def edit(text: str) -> str:
        return text.replace("kwota = { ", "kwota = { pattern = '^Suma:[ \\t]*([0-9][0-9 ,.]*)', ", 1)

    definition = next(c for c in edited_classes(tmp_path, "bank_transfer.toml", edit) if c.id == "bank_transfer")
    empty = {"przelew_bankowy": dict.fromkeys(definition.fields["przelew_bankowy"].fields)}
    record = engines.extract(definition, "Potwierdzenie\nSuma: 1 234,56 PLN", ocr_python=lambda: empty)
    assert record["przelew_bankowy"]["kwota"] == 1234.56


def test_a_class_file_that_does_not_fit_keeps_the_record_as_read(tmp_path):
    def edit(text: str) -> str:
        return text + 'licznik = { type = "integer", nullable = false, instruction = "Counter." }\n'

    pdf = DATA / "przyklad_01" / "przelew.pdf"
    classes = edited_classes(tmp_path, "bank_transfer.toml", edit)
    result = read_document(pdf, classes, explain=True)
    assert json.loads(result.text) == read(pdf, parse_classes(class_sources()))
    assert "licznik" in result.trace["schema_error"]


def references():
    for path in sorted(DATA.glob("przyklad_*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        label = next((CLASS_OF[key] for key in record if key in CLASS_OF), None)
        if label:
            yield pytest.param(label, record, id=f"{path.parent.name}/{path.stem}")


@pytest.mark.parametrize(("label", "reference"), references())
def test_the_shipped_class_files_have_the_reference_keys_in_reference_order(label, reference):
    definition = next(c for c in parse_classes(class_sources()) if c.id == label)
    shaped = {key: engines.conform(field, reference.get(key)) for key, field in definition.fields.items()}
    assert json.dumps(shaped, ensure_ascii=False) == json.dumps(reference, ensure_ascii=False)


@pytest.mark.parametrize("name", ["odwolanie", "pelnomocnictwo", "przelew"])
def test_outputs_fit_the_class_file_strictly(name):
    classes = parse_classes(class_sources())
    with trace.recording():
        result = read_document(DATA / "przyklad_02" / f"{name}.pdf", classes)
    definition = next(c for c in classes if c.id == result.label)
    definition.output_model.model_validate(json.loads(result.text), strict=True)


def test_a_field_removed_from_attorney_rows_keeps_the_grant(tmp_path):
    def edit(text: str) -> str:
        section = text.index("[fields.pelnomocnicy]")
        head, rest = text[:section], text[section:]
        dropped = ('match_by = "imie_nazwisko"', "imie_nazwisko = ")
        return head + "".join(line for line in rest.splitlines(keepends=True) if not line.startswith(dropped))

    pdf = DATA / "przyklad_02" / "pelnomocnictwo.pdf"
    result = read_document(pdf, edited_classes(tmp_path, "power_of_attorney.toml", edit))
    assert result.error is None
    attorneys = json.loads(result.text)["pelnomocnicy"]
    assert attorneys and all("imie_nazwisko" not in row for row in attorneys)


def test_a_field_turned_into_an_object_keeps_the_record_as_read(tmp_path):
    def edit(text: str) -> str:
        kept = "".join(line for line in text.splitlines(keepends=True) if not line.startswith("kwota = {"))
        return kept + (
            '\n[fields.przelew_bankowy.fields.kwota]\ntype = "object"\ninstruction = "Amount."\n'
            "[fields.przelew_bankowy.fields.kwota.fields]\n"
            'liczba = { type = "string", instruction = "Digits.", pattern = \'Kwota[^0-9]*([0-9][0-9 ,.]*)\' }\n'
        )

    pdf = DATA / "przyklad_01" / "przelew.pdf"
    result = read_document(pdf, edited_classes(tmp_path, "bank_transfer.toml", edit), explain=True)
    assert json.loads(result.text) == read(pdf, parse_classes(class_sources()))
    assert "kwota" in result.trace["schema_error"]
