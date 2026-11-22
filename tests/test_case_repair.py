import json
from pathlib import Path

import pytest
from stdnum.pl import nip

from kio2json import batch
from kio2json.case_repair import printed_readings
from kio2json.pdf_text import OCRWord


def document(label, data, pages, scanned=(), scores=()):
    boxes = [OCRWord(1, word, 0, 0, 1, 1, score) for word, score in scores]
    return batch.Result(label, json.dumps(data), readings=printed_readings(label, data, pages, scanned, boxes))


def appeal(party, pages, *args):
    return document("appeal", {"Odwolujacy": [party]}, pages, *args)


def grant(party, pages):
    return document("power_of_attorney", {"mocodawca": [{"data": party}]}, pages)


def reconcile(*docs):
    paths = [Path("one", f"{i}.pdf") for i in range(len(docs))]
    return [json.loads(r.text) for r in batch.reconcile_cases(paths, list(docs))]


def test_checksum_requires_same_owner_and_independent_literal():
    good = "1234563218"
    assert nip.is_valid(good)
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    party = {"nazwa": "Witraż", "nip": bad, "krs": None}
    target = appeal(party, ["Witraż NIP " + bad])
    donor = grant({**party, "nip": good, "krs": "0001234123"}, ["Witraż NIP " + good])
    fixed, unchanged = reconcile(target, donor)
    assert fixed["Odwolujacy"] == [{**party, "nip": good}]
    assert unchanged == json.loads(donor.text)
    for sibling in (
        grant({"nazwa": "Inna firma", "nip": good}, ["Inna firma NIP " + good]),
        grant({"nazwa": "Witraż", "nip": good}, ["Witraż"]),
        grant({"nip": good}, [good]),
        grant({"nazwa": "Witraż", "nip": good}, ["Inna firma NIP " + good]),
        grant({"nazwa": "Witraż", "nip": good}, ["Zamawiający: Witraż NIP " + good]),
        grant({"nazwa": "Witraż", "nip": good}, [f"Mocodawca: Inna firma\nNIP: {good}\nZamawiający: Witraż"]),
    ):
        assert reconcile(target, sibling)[0] == json.loads(target.text)
    assert batch.reconcile_cases([Path("one/a.pdf"), Path("two/b.pdf")], [target, donor]) == [target, donor]


def test_native_ocr_and_missing_values_in_one_case():
    donor = grant({"nazwa": "Witrola"}, ["Witrola"])
    party = {"nazwa": "Witr0la", "pelnomocnik": None}
    target = appeal(party, ["Witr0la"], [1], [("Witr0la", 35)])
    assert reconcile(target, donor)[0]["Odwolujacy"][0] == {**party, "nazwa": "Witrola"}
    for other in (
        appeal(party, ["Witr0la"]),
        appeal(party, ["Witr0la", "Witr0la"], [1], [("Witr0la", 35)]),
        appeal({**party, "nazwa": None}, ["Witrola"]),
        appeal({**party, "nazwa": "Witrula"}, ["Witrula"], [1], [("Witrula", 95)]),
        appeal({**party, "nazwa": "Witroli"}, ["Witroli"], [1], [("Witroli", 28)]),
    ):
        assert reconcile(other, donor)[0] == json.loads(other.text)


def test_second_plausible_spelling_prevents_repair_in_any_order():
    target = appeal({"nazwa": "Po|ara"}, ["Po|ara"], [1])
    a, b = [grant({"nazwa": v}, [v]) for v in ("Polara", "Potara")]
    assert reconcile(target, a, b)[0] == reconcile(target, b, a)[0] == json.loads(target.text)
    assert reconcile(target, a, appeal({}, []))[0] == json.loads(target.text)


def test_transfer_preserves_title_around_reference_and_ignores_unrelated_numbers():
    reference = "DZT.51/2026"
    donor = document("appeal", {"ZamowieniePubliczne": {"numer_postepowania": reference}}, [reference])
    for label, repair in (("nr postępowania:", True), ("identyfikator transakcji:", False)):
        title = f"Wpis. {label} DZT.5I/2026 dla wykonawcy."
        receipt = document("bank_transfer", {"przelew_bankowy": {"tytul": title}}, [title], [1], [("DZT.5I/2026", 38)])
        result = reconcile(donor, receipt)[1]["przelew_bankowy"]
        assert result["tytul"] == (title.replace("5I", "51") if repair else title)


@pytest.mark.parametrize(("score", "expected"), [(35, "0001234567"), (96, "0001234568")])
def test_krs_requires_a_weak_scan_read_and_owner(score, expected):
    name = "Witrola"
    target = appeal({"nazwa": name, "krs": "0001234568"}, [f"{name} 0001234568"], [1], [("0001234568", score)])
    sibling = grant({"nazwa": name, "krs": "0001234567"}, [f"{name} 0001234567"])
    assert reconcile(target, sibling)[0]["Odwolujacy"][0]["krs"] == expected


def test_attorney_bound_to_appointment_and_sender_bound_to_label():
    person = "Jan Po|ski"
    party = {"nazwa": "Witr0la", "pelnomocnik": {"imie_nazwisko": person}}
    target = appeal(party, [f"Witr0la {person}"], [1], [("Witr0la", 25)])
    mandate = document("power_of_attorney", {"pelnomocnicy": [{"imie_nazwisko": "Jan Polski"}]}, ["Jan Polski"])
    transfer = document("bank_transfer", {"przelew_bankowy": {}}, ["Odbiorca: Witrola"])
    fixed = reconcile(target, transfer, mandate)[0]["Odwolujacy"][0]
    assert fixed == {**party, "pelnomocnik": {"imie_nazwisko": "Jan Polski"}}
    sender = document("bank_transfer", {"przelew_bankowy": {}}, ["Nadawca: Witrola"])
    assert reconcile(target, sender)[0]["Odwolujacy"][0]["nazwa"] == "Witrola"


def test_cli_reconciles_each_explicit_folder_after_all_worker_results(tmp_path, monkeypatch):
    import sys

    from kio2json import __main__ as cli

    source, output = tmp_path / "input", tmp_path / "out"
    readings = {
        "a": appeal({"nazwa": "Po|ana"}, ["Po|ana"], [1]),
        "b": grant({"nazwa": "Polana"}, ["Polana"]),
    }
    for name in ("case/a.pdf", "case/b.pdf", "alone/a.pdf", "a.pdf", "b.pdf"):
        path = source / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.touch()
    monkeypatch.setattr(cli, "read_batch", lambda paths, *_: (readings[p.stem] for p in paths))
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(source), "--output", str(output), "--jobs", "2"])
    monkeypatch.setenv("KIO_CASE_REPAIR", "1")
    assert cli.main() == 0
    assert json.loads((output / "case/a.json").read_bytes())["Odwolujacy"][0]["nazwa"] == "Polana"
    assert (output / "a.json").read_text() == (output / "alone/a.json").read_text() == readings["a"].text
    monkeypatch.setenv("KIO_CASE_REPAIR", "0")
    assert cli.main() == 0
    assert (output / "case/a.json").read_text() == readings["a"].text


def test_partial_sibling_reference_and_appeal_docket_cannot_supply_procedure():
    from kio2json.case_repair import procedure_references

    reference = "DZT.51/2026"
    donor = document("appeal", {"ZamowieniePubliczne": {"numer_postepowania": reference}}, [reference + "/02"])
    assert not donor.readings
    extended = reference + "–02"
    donor = document("appeal", {"ZamowieniePubliczne": {"numer_postepowania": reference}}, [extended])
    assert not donor.readings
    assert [m[1] for m in procedure_references("Nr postępowania: " + extended)] == [extended]
    assert not list(procedure_references("Wpis od odwołania, nr sprawy KIO/123/24"))


def test_configured_class_can_reuse_an_organizer_id_with_its_own_fields(tmp_path, monkeypatch):
    from kio2json import pipeline
    from kio2json.case_checks import case_warnings
    from kio2json.class_config import parse_classes

    custom = b"""id = "appeal"
engines = ["labelled_fields"]
[routing]
required = ["custom"]
[fields.Odwolujacy]
type = "string"
instruction = "Custom scalar"
pattern = "custom (.*)"
"""
    classes = parse_classes({tmp_path / "custom.toml": custom})
    monkeypatch.setenv("KIO_CASE_REPAIR", "1")
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: ["custom scalar"])
    item = batch.read_document(tmp_path / "a.pdf", classes)
    assert json.loads(item.text) == {"Odwolujacy": "scalar"}
    assert not item.readings and item.custom_schema
    docs = [item, grant({"nazwa": "Próba"}, ["Próba"])]
    assert not case_warnings([Path("case/a.pdf"), Path("case/b.pdf")], docs)


@pytest.mark.parametrize("heading", ["Pełnomocnik odwołującego", "Pełnomocnicy", "Podpisujący", "Zamawiający"])
def test_competing_printed_card_cannot_donate_a_name_or_its_identifier(heading):
    donor = grant(
        {"nazwa": "Polara", "nip": "1234563218"}, [f"Mocodawca: Inna spółka\n{heading}: Polara NIP 1234563218"]
    )
    assert not donor.readings


def test_two_native_pdfs_repair_a_checksum_failure_through_the_viewer(tmp_path, monkeypatch):
    from snapshots.generate_native import write_native_pdf

    from kio2json.gui_files import analyze, folder_sources

    case = tmp_path / "input/case"
    case.mkdir(parents=True)
    write_native_pdf(
        case / "a.pdf",
        ["Odwołujący: Witraż S.A.\nNIP: 1234563219\nZamawiający: Dom Kredy\nODWOŁANIE\nWnoszę odwołanie."],
    )
    write_native_pdf(
        case / "b.pdf",
        [
            (
                "Mocodawca: Witraż S.A., NIP: 1234563218\nPEŁNOMOCNICTWO\n"
                "Witraż S.A. udziela pełnomocnictwa radcy prawnemu Igorowi Rudemu."
            )
        ],
    )
    sources = folder_sources(str(case))
    for enabled, expected in [("0", "1234563219"), ("1", "1234563218")]:
        monkeypatch.setenv("KIO_CASE_REPAIR", enabled)
        appeal_doc, grant_doc = analyze(sources, tmp_path)
        assert json.loads(appeal_doc.result.text)["Odwolujacy"][0]["nip"] == expected
        assert json.loads(grant_doc.result.text)["mocodawca"][0]["data"]["nip"] == "1234563218"


def test_recipient_cannot_confirm_a_weak_sender_on_another_page():
    target = appeal({"nazwa": "Po|ara"}, ["Po|ara"], [1])
    receipt = {"przelew_bankowy": {}}
    sender = "Nadawca: Polara"
    recipient = "Odbiorca: Polara"
    weak = document("bank_transfer", receipt, [sender, recipient], [1], [("Polara", 22)])
    strong = document("bank_transfer", receipt, [recipient, sender], [1], [("Polara", 22)])
    assert reconcile(target, weak)[0] == json.loads(target.text)
    assert reconcile(target, strong)[0]["Odwolujacy"][0]["nazwa"] == "Polara"
