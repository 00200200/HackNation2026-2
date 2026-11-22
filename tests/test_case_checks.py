import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from shiny.testserver import test_server as shiny_session

from kio2json import gui
from kio2json.batch import Result
from kio2json.gui_files import analyze, archive


def appeal(*parties, reference=None, title=None):
    return Result(
        "appeal",
        json.dumps(
            {
                "Odwolujacy": list(parties),
                "ZamowieniePubliczne": {"numer_postepowania": reference, "tytul": title},
            }
        ),
    )


def grant(parties=(), attorneys=()):
    return Result(
        "power_of_attorney",
        json.dumps(
            {
                "mocodawca": [{"data": row} for row in parties],
                "pelnomocnicy": [{"imie_nazwisko": name} for name in attorneys],
            }
        ),
    )


def transfer(title, amount):
    return Result("bank_transfer", json.dumps({"przelew_bankowy": {"tytul": title, "kwota": amount}}))


def checks(*entries):
    from kio2json.case_checks import case_warnings

    return case_warnings([Path(name) for name, _ in entries], [result for _, result in entries])


APPEAL = (
    "a/appeal.pdf",
    appeal(
        {"nazwa": "Alfa SA", "nip": "1234567890", "pelnomocnik": {"imie_nazwisko": "Maria Kot"}},
        reference="ZP.12/24",
        title="Dostawa komputerów",
    ),
)
GRANT = ("a/grant.pdf", grant([{"nazwa": "Beta", "nip": "9876543210"}], ["Adam Lis"]))
TRANSFER = ("a/transfer.pdf", transfer("Wpis od odwołania w postępowaniu ZP.21/24", 10000))


def test_four_disagreements_identify_their_source_files_and_fields():
    warnings = {warning.code: warning for warning in checks(APPEAL, GRANT, TRANSFER)}
    assert set(warnings) == {"grantor", "attorney", "procedure", "fee"}
    for code, doc in (("grantor", GRANT), ("attorney", GRANT), ("procedure", TRANSFER), ("fee", TRANSFER)):
        assert warnings[code].documents == (Path(APPEAL[0]), Path(doc[0]))
    assert "ZP.21/24" in warnings["procedure"].message
    assert "ZP.12/24" in warnings["procedure"].message
    assert "7 500" in warnings["fee"].message and "15 000" in warnings["fee"].message


def test_matching_joint_grantor_or_attorney_short_circuits_disagreement():
    for matching in ({"nazwa": "ALFA Spółka Akcyjna"}, {"nazwa": "Alfa", "nip": "1234567890"}):
        several = grant([{"nazwa": "Beta"}, matching], ["Adam Lis", "Maria Kot"])
        assert not checks(APPEAL, ("a/one.pdf", several), GRANT)
    same_name_wrong_id = grant([{"nazwa": "Alfa SA", "nip": "9999999999"}])
    assert [w.code for w in checks(APPEAL, ("a/grant.pdf", same_name_wrong_id))] == ["grantor"]


def test_missing_fields_errors_or_a_different_parent_cannot_create_a_warning():
    unresolved = grant([{}], [None])
    assert not checks(
        APPEAL,
        ("a/grant.pdf", unresolved),
        ("a/transfer.pdf", transfer(None, 42)),
        ("other/a/grant.pdf", GRANT[1]),
        ("a/error.pdf", Result(None, "", "bad")),
    )
    assert not checks(APPEAL, ("a/other-appeal.pdf", appeal()), TRANSFER)


@pytest.mark.parametrize(
    ("title", "amount", "procurement", "expected"),
    [
        ("Wpis od odwołania", -7500, "Dostawa mebli", []),
        ("Wpis od odwołania", 15000, "Usługi ochrony", []),
        ("Wpis od odwołania", 10000, "Wykonanie robót budowlanych na moście", []),
        ("Wpis od odwołania", 20000, "Roboty budowlane", []),
        ("Wpis od odwołania", 15000, "Roboty budowlane", ["fee"]),
        ("Wpis od odwołania", 10000, "Usługa nadzoru nad robotami budowlanymi", ["fee"]),
        ("Wpis od odwołania", 42, "Modernizacja systemu", []),
        ("Wpis od odwołania", None, "Dostawa mebli", []),
        ("Opłata skarbowa za pełnomocnictwo", 17, "Dostawa mebli", []),
        ("Dopłata do wpisu od odwołania", 500, "Dostawa mebli", []),
        ("Zwrot wpisu od odwołania", 42, "Dostawa mebli", []),
        ("Wpis od odwołania, część wpłaty", 3000, "Dostawa mebli", []),
        ("Wpis od odwołania, faktura FV-99/25", 7500, "Dostawa mebli", []),
        ("Wpis od odwołania, nr postępowania: zp.12/24", 7500, "Dostawa mebli", []),
        ("Wpis od odwołania, nr postępowania ZP/3; nr postępowania ZP/4", 7500, "Dostawa mebli", []),
    ],
)
def test_only_compare_supported_fee_and_procedure_evidence(title, amount, procurement, expected):
    a = appeal(reference="ZP.12/24", title=procurement)
    assert [w.code for w in checks(("a/appeal.pdf", a), ("a/receipt.pdf", transfer(title, amount)))] == expected


def test_local_gui_warns_for_selected_document_and_exports_only_organizer_output(tmp_path, monkeypatch):
    results = dict([APPEAL, GRANT, TRANSFER])
    paths = []
    folder = tmp_path / "a"
    folder.mkdir()
    for name in results:
        path = tmp_path / name
        path.write_text(name)
        paths.append((Path(name), path))
    monkeypatch.setattr("kio2json.gui_files.read_document", lambda path, *a, **kw: results[path.read_text()])
    # The stub replaces in-process reading; worker processes would not see it.
    monkeypatch.setattr("kio2json.gui.WORKERS", 1)
    documents = analyze(paths, tmp_path)
    with ZipFile(BytesIO(archive(documents))) as bundle:
        assert {name: bundle.read(name).decode() for name in bundle.namelist()} == {
            name.replace(".pdf", ".json"): result.text for name, result in results.items()
        }
    monkeypatch.setattr(gui.options, "local_folders", True)  # As launched with python -m kio2json.gui.
    with shiny_session(gui.app, timeout_secs=30) as session:
        session.set_inputs(mode="folder", folder=str(folder), run=1, document="0", page="1")
        html = session.get_output("consistency_warnings").value["html"]
        assert "grant.pdf" in html and "transfer.pdf" in html and "appeal.pdf" in html
        session.set_inputs(document="2")
        html = session.get_output("consistency_warnings").value["html"]
        assert "transfer.pdf" in html and "grant.pdf" not in html
