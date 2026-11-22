"""A new class from one TOML file: flags, weighted cues, named checks, scaffold and trace."""

import json
import sys
from pathlib import Path

import pytest
from snapshots.generate_native import write_native_pdf

from kio2json import __main__ as cli
from kio2json import classes as tool
from kio2json import pipeline
from kio2json.batch import read_document
from kio2json.class_config import DocumentClass, class_sources, parse_classes, route

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "classes"
SAMPLE = ROOT / "examples" / "input" / "sprawa-demo" / "zgloszenie_przystapienia.pdf"
# Invented notice. The NIP and REGON are checksum-valid numbers made up for this example.
NOTICE = """Warszawa, 14.03.2026
Prezes Krajowej Izby Odwoławczej
ZGŁOSZENIE PRZYSTĄPIENIA DO POSTĘPOWANIA ODWOŁAWCZEGO
Sygnatura akt: KIO 1234/26
Przystępujący: Miedziana Czapla Sp. z o.o.
NIP: 123-456-78-83
REGON: 123456785
Po stronie: Zamawiającego
Odwołujący: Srebrny Żuraw S.A.
Data doręczenia wezwania: 11.03.2026
Działając w imieniu Przystępującego zgłaszam przystąpienie do postępowania
odwoławczego po stronie Zamawiającego. Oferta Przystępującego została wybrana.
Jan Przykładowy, Prezes Zarządu"""
EXPECTED = {
    "sygnatura": "KIO 1234/26",
    "przystepujacy": "Miedziana Czapla Sp. z o.o.",
    "nip": "1234567883",
    "regon": "123456785",
    "strona": "Zamawiającego",
    "data_wezwania": "2026-03-11",
}


def write_notice(path: Path, text: str = NOTICE) -> Path:
    write_native_pdf(path, [text], size=(595, 842), font=11, margin=56)
    return path


def run_cli(monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["kio2json", *args])
    return cli.main()


def load(tmp_path: Path, toml: str, name: str = "form.toml") -> DocumentClass:
    (tmp_path / name).write_text(toml, encoding="utf-8")
    return next(c for c in parse_classes(class_sources(extra=[tmp_path / name])) if c.source.name == name)


def test_committed_sample_is_the_invented_notice(tmp_path):
    assert write_notice(tmp_path / "notice.pdf").read_bytes() == SAMPLE.read_bytes()


def test_default_set_ignores_the_notice_and_one_flag_adds_the_class(tmp_path, monkeypatch, in_process_cli):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    inputs, output = tmp_path / "input" / "sprawa", tmp_path / "output"
    inputs.mkdir(parents=True)
    write_notice(inputs / "zgloszenie.pdf")
    target = output / "sprawa" / "zgloszenie.json"

    assert run_cli(monkeypatch, "--input", str(tmp_path / "input"), "--output", str(output)) == 0
    assert json.loads(target.read_text() or "{}") == {}

    options = ["--input", str(tmp_path / "input"), "--output", str(output)]
    assert run_cli(monkeypatch, *options, "--classes", str(EXAMPLES)) == 0
    assert json.loads(target.read_text()) == EXPECTED


def test_enable_turns_on_a_disabled_class_and_rejects_unknown_ids(tmp_path, monkeypatch, capsys, in_process_cli):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    form = "KARTA UCZESTNIKA\nUczestnik: Copper Heron\nData: 19.07.2031\nSygnatura: H-77"
    write_native_pdf(tmp_path / "form.pdf", [form])
    output = tmp_path / "out"
    assert run_cli(monkeypatch, "--input", str(tmp_path), "--output", str(output), "--enable", "participation") == 0
    assert json.loads((output / "form.json").read_text()) == {
        "participant": "Copper Heron",
        "filed": "2031-07-19",
        "reference": "H-77",
    }
    assert run_cli(monkeypatch, "--input", str(tmp_path), "--enable", "receipt") == 1
    assert "cannot enable receipt: no such class" in capsys.readouterr().err
    assert run_cli(monkeypatch, "--input", str(tmp_path), "--classes", str(tmp_path / "missing")) == 1
    assert "no such class directory or file" in capsys.readouterr().err


def test_extra_directory_may_be_empty_and_repeats_are_loaded_once(tmp_path, monkeypatch):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    registry = ROOT / "config" / "classes"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert class_sources(extra=[empty, registry / "appeal.toml"]).files == class_sources().files
    copy = tmp_path / "participation.toml"
    copy.write_text((registry / "participation.toml").read_text(), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate class id participation"):
        parse_classes(class_sources(extra=[copy]))


CUES = """id = "form"
engines = ["labelled_fields"]
[routing]
threshold = 3
forbidden = ['^Projekt\\b']
[routing.cues]
"Karta zgłoszenia" = 2
"Numer:" = 1
"Załącznik" = -2
[fields.numer]
type = "string"
instruction = "Form number."
pattern = '^Numer:[ \\t]*(.+)$'
"""


@pytest.mark.parametrize(
    ("page", "score"),
    [
        ("KARTA   ZGŁOSZENIA\nNumer: 7", 3),
        ("Karta zgłoszenia\nNumer: 7\nZałącznik nr 2", None),
        ("Numer: 7", None),
        ("Projekt\nKarta zgłoszenia\nNumer: 7", None),
        ("Kartazgłoszenia\nNumer: 7", None),
    ],
)
def test_weighted_cues_reach_the_threshold(tmp_path, page, score):
    definition = load(tmp_path, CUES)
    match = definition.routing.explain([page])
    assert (match and match["score"]) == score
    assert (route([page], [definition]) is definition) == (score is not None)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("threshold = 3\n", ""), "cues and threshold must be set together"),
        (("threshold = 3", "threshold = 4"), "threshold 4 exceeds the positive cue weights"),
        (('"Numer:" = 1', '"Numer:" = 0'), "must not be 0"),
        (('"Numer:" = 1', '"   " = 1'), "must contain text"),
        (('type = "string"', 'type = "string"\nvalidators = ["krs"]'), "validators"),
        (('type = "string"', 'type = "integer"\nvalidators = ["nip"]'), "nip does not fit an integer field"),
        (('type = "string"', 'type = "string"\nvalidators = [{ name = "date_range", min = 2020-01-01 }]'), "iso_date"),
        (('type = "string"', 'type = "string"\nvalidators = [{ name = "one_of", values = [1] }]'), "one_of"),
        (('type = "string"', 'type = "string"\nnullable = false\nvalidators = ["nip"]'), 'on_invalid = "warn"'),
    ],
)
def test_invalid_cues_and_checks_name_the_file(tmp_path, change, message):
    changed = CUES.replace(*change)
    assert changed != CUES
    with pytest.raises(ValueError, match=rf"(?s)form\.toml.*{message}"):
        load(tmp_path, changed)


def test_failed_checks_null_or_keep_the_value_and_reach_the_trace(tmp_path, monkeypatch):
    text = (
        NOTICE.replace("123-456-78-83", "123-456-78-84")
        .replace("Po stronie: Zamawiającego", "Po stronie: Wykonawcy")
        .replace("11.03.2026", "11.03.2032")
    )
    pdf = write_notice(tmp_path / "notice.pdf", text)
    classes = parse_classes(class_sources(extra=[EXAMPLES]))
    result = read_document(pdf, classes, explain=True)
    record = json.loads(result.text)
    assert record == EXPECTED | {"nip": None, "strona": None, "data_wezwania": "2032-03-11"}
    assert result.trace["warnings"] == [
        {"field": "nip", "check": "nip", "value": "1234567884", "action": "null"},
        {"field": "strona", "check": "one_of", "value": "Wykonawcy", "action": "null"},
        {"field": "data_wezwania", "check": "date_range", "value": "2032-03-11", "action": "warn"},
    ]


def test_trace_names_the_class_file_and_the_cues_found(tmp_path):
    classes = parse_classes(class_sources(extra=[EXAMPLES]))
    trace = read_document(write_notice(tmp_path / "notice.pdf"), classes, explain=True).trace
    assert trace["class"] == "accession"
    assert trace["routing"]["router"] == "config"
    assert trace["routing"]["rule"] == "accession.toml"
    match = trace["routing"]["match"]
    assert [cue["cue"] for cue in match["cues"]] == [
        "zgłoszenie przystąpienia",
        "postępowania odwoławczego",
        "Przystępujący:",
        "Sygnatura akt:",
    ]
    assert (match["score"], match["threshold"]) == (6, 4)
    fields = {field["field"]: field for field in trace["fields"]}
    assert fields["nip"]["snippet"] == "NIP: 123-456-78-83"


def test_scaffold_writes_a_class_that_routes_and_reads_its_sample(tmp_path, monkeypatch, capsys):
    out = tmp_path / "classes"
    monkeypatch.setattr(sys, "argv", ["classes", "new", "accession", "--from-pdf", str(SAMPLE), "--out", str(out)])
    assert tool.main() == 0
    printed = capsys.readouterr().out
    assert "routes with score" in printed
    definition = next(c for c in parse_classes(class_sources(extra=[out])) if c.id == "accession")
    assert definition.id == "accession" and definition.enabled
    assert definition.name == "Zgłoszenie przystąpienia do postępowania odwoławczego"
    assert set(definition.fields) == {
        "sygnatura_akt",
        "przystepujacy",
        "nip",
        "regon",
        "po_stronie",
        "odwolujacy",
        "data_doreczenia_wezwania",
    }
    assert definition.fields["nip"].validators[0].name == "nip"
    assert definition.fields["data_doreczenia_wezwania"].normalizer == "iso_date"
    pages = pipeline.read_pages(SAMPLE)
    assert route(pages, [definition]) is definition
    record = json.loads(printed[printed.index("{") : printed.rindex("}") + 1])
    assert record["nip"] == "1234567883"
    assert record["data_doreczenia_wezwania"] == "2026-03-11"

    assert tool.main() == 1
    assert "Pass --force" in capsys.readouterr().err


def test_scaffold_keeps_a_class_in_the_default_directory_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "DEFAULT_DIR", tmp_path.resolve())
    monkeypatch.setattr(sys, "argv", ["classes", "new", "accession", "--from-pdf", str(SAMPLE), "--out", str(tmp_path)])
    assert tool.main() == 0
    assert "enabled = false" in (tmp_path / "accession.toml").read_text()
    assert "--enable accession" in capsys.readouterr().out


def test_list_shows_files_state_and_routing(monkeypatch, capsys):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["classes", "list", "--classes", str(EXAMPLES), "--enable", "participation"])
    assert tool.main() == 0
    rows = {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()[1:]}
    assert rows["appeal"][1:4] == ["yes", "appeal.toml", "classifier"]
    assert rows["participation"][1] == "yes"
    assert rows["accession"][1:5] == ["yes", "accession.toml", "cues", ">="]


def test_explain_writes_traces_to_their_own_folder_outside_output(tmp_path, monkeypatch, in_process_cli):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    inputs, output, evidence = tmp_path / "input", tmp_path / "output", tmp_path / "evidence"
    (inputs / "sprawa").mkdir(parents=True)
    write_notice(inputs / "sprawa" / "zgloszenie.pdf")
    options = ["--input", str(inputs), "--output", str(output), "--classes", str(EXAMPLES)]
    assert run_cli(monkeypatch, *options, "--explain", str(evidence)) == 0
    assert sorted(p.relative_to(output).as_posix() for p in output.rglob("*")) == ["sprawa", "sprawa/zgloszenie.json"]
    trace = json.loads((evidence / "sprawa" / "zgloszenie.trace.json").read_text())
    assert (trace["document"], trace["class"], trace["error"]) == ("sprawa/zgloszenie.pdf", "accession", None)
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, *options, "--explain", str(output / "trace"))


def test_scaffold_refuses_a_class_id_already_in_use(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["classes", "new", "appeal", "--from-pdf", str(SAMPLE), "--out", str(tmp_path)])
    assert tool.main() == 1
    assert "already in use" in capsys.readouterr().err
    assert not (tmp_path / "appeal.toml").exists()


def test_review_fixes_for_cues_checks_and_traces(tmp_path):
    # Float weights reach their threshold, a spaced label matches its cue and headings keep their printed form.
    definition = load(
        tmp_path,
        CUES.replace("threshold = 3", "threshold = 0.8")
        .replace('"Karta zgłoszenia" = 2', '"Karta zgłoszenia" = 0.7')
        .replace('"Numer:" = 1', '"Numer:" = 0.1\n')
        .replace("[routing]", "[routing]\nheadings = ['KARTAZGŁOSZENIA']"),
    )
    match = definition.routing.explain(["Karta zgłoszenia\nNumer : 7"])
    assert match["headings"] == ["Karta zgłoszenia"]
    assert [cue["cue"] for cue in match["cues"]] == ["Karta zgłoszenia", "Numer:"]
    # An impossible month in a labelled value cannot break the trace or the JSON.
    form = load(tmp_path, CUES, "form2.toml")
    pdf = tmp_path / "form.pdf"
    write_native_pdf(pdf, ["Karta zgłoszenia\nNumer: 2024-13-05"])
    result = read_document(pdf, [form], explain=True)
    assert json.loads(result.text) == {"numer": "2024-13-05"}
    assert result.trace["fields"][0]["snippet"] == "Numer: 2024-13-05"


def test_failed_check_is_a_gap_for_the_next_engine():
    from kio2json import engines, trace

    definition = next(c for c in parse_classes(class_sources(extra=[EXAMPLES])) if c.id == "accession")
    definition = definition.model_copy(update={"engines": ["labelled_fields", "python"]})
    page = NOTICE.replace("123-456-78-83", "123-456-78-84")
    second = {key: None for key in definition.fields} | {"nip": "1234567883"}
    with trace.recording() as events:
        record = engines.extract(definition, page, ocr_python=lambda: dict(second))
    assert record["nip"] == "1234567883"
    assert events["warnings"] == []


ACCESSION_PAGE = "\n".join(line for line in NOTICE.splitlines() if not line.startswith(("Warszawa", "Prezes")))


def traced_extract(definition, page, second=None):
    from kio2json import engines, trace

    rules = (lambda: {key: None for key in definition.fields} | second) if second else None
    with trace.recording() as events:
        record = engines.extract(definition, page, ocr_python=rules)
    events["pages"], events["ocr_pages"] = [page], []
    return record, events


def accession_with_second_engine():
    definition = next(c for c in parse_classes(class_sources(extra=[EXAMPLES])) if c.id == "accession")
    return definition.model_copy(update={"engines": ["labelled_fields", "python"]})


def test_a_kept_reading_keeps_its_warning_when_a_later_engine_also_fails():
    page = ACCESSION_PAGE.replace("11.03.2026", "11.03.2032").replace("REGON: 123456785\n", "")
    record, events = traced_extract(
        accession_with_second_engine(), page, {"regon": "123456785", "data_wezwania": "2033-01-01"}
    )
    assert record["data_wezwania"] == "2032-03-11"
    assert [(w["field"], w["value"]) for w in events["warnings"]] == [("data_wezwania", "2032-03-11")]


def test_a_corrected_value_is_not_cited_from_the_rejected_line():
    from kio2json import trace

    page = ACCESSION_PAGE.replace("123-456-78-83", "123-456-78-84") + "\nNIP spółki 1234567883"
    record, events = traced_extract(accession_with_second_engine(), page, {"nip": "1234567883"})
    nip = next(f for f in trace.build("accession", record, events)["fields"] if f["field"] == "nip")
    assert (nip["value"], nip["snippet"]) == ("1234567883", "NIP spółki 1234567883")


def test_a_nested_labelled_integer_is_located_by_its_pattern(tmp_path):
    from kio2json import trace

    form = load(
        tmp_path,
        """id = "form"
engines = ["labelled_fields"]
[routing]
required = ['^Formularz$']
[fields.osoba]
type = "object"
instruction = "Person."
[fields.osoba.fields.wiek]
type = "integer"
instruction = "Age."
pattern = '^Wiek:[ \\t]*(\\d+)$'
""",
    )
    record, events = traced_extract(form, "Formularz\nWiek: 42")
    (field,) = trace.build("form", record, events)["fields"]
    assert (field["value"], field["page"], field["snippet"]) == (42, 1, "Wiek: 42")


def test_trace_failures_keep_the_json_and_impossible_months_are_not_dates(monkeypatch):
    from kio2json import batch
    from kio2json.trace import value_pattern

    assert value_pattern("2024-13-05").search("kod 2024-13-05")
    assert not value_pattern("2024-13-05").search("5 grudnia 2024")

    def broken(*args):
        raise RuntimeError("trace bug")

    monkeypatch.setattr(batch, "build", broken)
    classes = parse_classes(class_sources(extra=[EXAMPLES]))
    result = read_document(SAMPLE, classes, explain=True)
    assert json.loads(result.text) == EXPECTED
    assert result.trace["trace_error"] == "RuntimeError: trace bug"


def test_a_partial_classifier_routes_without_a_qualname():
    from functools import partial

    from kio2json.class_config import ClassifierRouting

    definition = next(c for c in parse_classes(class_sources()) if c.id == "appeal")
    routing = ClassifierRouting.model_construct(classifier=partial(lambda pages, label: label, label="appeal"))
    custom = definition.model_copy(update={"routing": routing})
    assert route(["any page"], [custom]) is custom


def test_scaffold_ids_in_the_output_folder_and_regeneration(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    out = tmp_path / "classes"
    out.mkdir()
    (out / "old.toml").write_text((EXAMPLES / "accession.toml").read_text(), encoding="utf-8")
    command = ["classes", "new", "accession", "--from-pdf", str(SAMPLE), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", command)
    assert tool.main() == 1
    assert "already in use" in capsys.readouterr().err
    (out / "old.toml").unlink()
    assert tool.main() == 0
    monkeypatch.setattr(sys, "argv", [*command, "--force"])
    assert tool.main() == 0
    monkeypatch.setenv("KIO_CLASSES_DIR", str(tmp_path / "missing"))
    assert tool.main() == 1
    assert "Class configuration" in capsys.readouterr().err


def test_explain_into_a_file_stops_before_any_pdf(tmp_path, monkeypatch, in_process_cli):
    (tmp_path / "input").mkdir()
    blocker = tmp_path / "trace.json"
    blocker.write_text("x")
    with pytest.raises(SystemExit):
        run_cli(
            monkeypatch,
            "--input",
            str(tmp_path / "input"),
            "--output",
            str(tmp_path / "out"),
            "--explain",
            str(blocker),
        )


def test_a_tiny_threshold_still_needs_its_cue(tmp_path):
    definition = load(
        tmp_path,
        CUES.replace("threshold = 3", "threshold = 1e-10").replace(
            '"Karta zgłoszenia" = 2', '"Karta zgłoszenia" = 1e-10'
        ),
    )
    assert definition.routing.explain(["Inny dokument\nNumer: 7"]) is not None  # "Numer:" weighs 1
    sparse = load(
        tmp_path,
        CUES.replace("threshold = 3", "threshold = 1e-10")
        .replace('"Numer:" = 1', '"Numer:" = 1e-10')
        .replace('"Karta zgłoszenia" = 2', '"Karta zgłoszenia" = 1e-10'),
        "sparse.toml",
    )
    assert sparse.routing.explain(["Faktura"]) is None


def test_explain_folder_may_not_contain_the_output(tmp_path, monkeypatch, in_process_cli):
    (tmp_path / "input").mkdir()
    run = tmp_path / "run"
    with pytest.raises(SystemExit):
        run_cli(monkeypatch, "--input", str(tmp_path / "input"), "--output", str(run / "output"), "--explain", str(run))


def test_force_replaces_a_generated_file_that_no_longer_parses(tmp_path, monkeypatch):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    out = tmp_path / "classes"
    out.mkdir()
    (out / "accession.toml").write_text("id = \n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["classes", "new", "accession", "--from-pdf", str(SAMPLE), "--out", str(out), "--force"]
    )
    assert tool.main() == 0
    assert next(c for c in parse_classes(class_sources(extra=[out])) if c.id == "accession")


@pytest.mark.parametrize(
    ("value", "found", "missed"),
    [
        (15.75, "Kwota: 15,75", "Saldo: 15,00"),
        (15.0, "Kwota: 15,00 zł", "Saldo: 15,75"),
        (15.0, "razem 15 zł.", "kod 155"),
    ],
)
def test_an_amount_does_not_match_another_amounts_integer_part(value, found, missed):
    from kio2json.trace import value_pattern

    assert value_pattern(value).search(found)
    assert not value_pattern(value).search(missed)


def test_a_case_repair_shows_in_the_trace():
    from kio2json.trace import repaired

    trace = {"fields": [{"field": "a.nip", "value": "1234567884", "page": 1, "snippet": "NIP: 1234567884"}]}
    fixed = repaired(trace, {"a": {"nip": "1234567883"}})["fields"][0]
    assert fixed["value"] == "1234567883" and fixed["note"] == "corrected from another document in the case folder"
    assert trace["fields"][0]["value"] == "1234567884"


def test_the_page_of_a_field_is_a_keyboard_button():
    from kio2json.gui_explain import field_table

    trace = {"class": "x", "fields": [{"field": "a", "value": 1, "page": 2, "engine": "rule", "snippet": "a: 1"}]}
    import html

    shown = html.unescape(str(field_table(trace)))
    assert "<button" in shown and 'type="button"' in shown and 'class="page-link"' in shown
    assert "Shiny.setInputValue('trace_page', 2" in shown
