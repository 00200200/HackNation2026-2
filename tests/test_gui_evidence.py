"""Viewer evidence: case ZIP uploads, cached reads, CLI-identical ZIPs and highlighted sources."""

import html
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from kio2json import gui_files
from kio2json.batch import Result, read_document
from kio2json.class_config import class_sources, parse_classes
from kio2json.gui_explain import evidence, json_view, outcome
from kio2json.gui_files import Document, analyze, archive, page_image, upload_sources

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "input" / "sprawa-demo" / "zgloszenie_przystapienia.pdf"


def zip_upload(tmp_path: Path, entries: dict[str, bytes], *, utf8: bool = True) -> dict:
    """A ZIP as an archiver writes it; utf8=False stores names in code page 852 without the UTF-8 flag."""
    path = tmp_path / "upload.zip"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as bundle:
        for index, (name, data) in enumerate(entries.items()):
            bundle.writestr(name if utf8 else f"{index:0{len(name.encode('cp852'))}d}", data)
    raw = buffer.getvalue()
    if not utf8:
        for index, name in enumerate(entries):
            encoded = name.encode("cp852")
            raw = raw.replace(f"{index:0{len(encoded)}d}".encode(), encoded)
    path.write_bytes(raw)
    return {"name": "sprawy.zip", "datapath": str(path)}


def test_zip_folders_become_cases_and_loose_pdfs_join_the_named_case(tmp_path):
    upload = zip_upload(
        tmp_path,
        {
            "sprawa-1/odwolanie.pdf": b"a",
            "sprawa-2/przelew.PDF": b"b",
            "luzem.pdf": b"c",
            "notatka.txt": b"d",
            "__MACOSX/sprawa-1/._odwolanie.pdf": b"e",
        },
    )
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    sources = upload_sources("sprawa", [upload], unpacked)
    assert [name.as_posix() for name, _ in sources] == [
        "sprawa-1/odwolanie.pdf",
        "sprawa-2/przelew.PDF",
        "sprawa/luzem.pdf",
    ]
    assert [path.read_bytes() for _, path in sources] == [b"a", b"b", b"c"]


def test_zip_from_a_polish_windows_archiver_keeps_its_names(tmp_path):
    upload = zip_upload(tmp_path, {"sprawa/pełnomocnictwo.pdf": b"x"}, utf8=False)
    sources = upload_sources("sprawa", [upload], tmp_path)
    assert sources[0][0].as_posix() == "sprawa/pełnomocnictwo.pdf"


@pytest.mark.parametrize("name", ["../x.pdf", "/abs/x.pdf", "a/NUL.pdf", "C:x/y.pdf"])
def test_zip_rejects_unsafe_entries(tmp_path, name):
    with pytest.raises(ValueError):
        upload_sources("sprawa", [zip_upload(tmp_path, {name: b"x"})], tmp_path)


def test_damaged_or_empty_zip_is_explained(tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="ZIP"):
        upload_sources("sprawa", [{"name": "broken.zip", "datapath": str(broken)}], tmp_path)
    with pytest.raises(ValueError, match="nie ma plików PDF"):
        upload_sources("sprawa", [zip_upload(tmp_path, {"notatka.txt": b"x"})], tmp_path)


def test_zip_download_keeps_the_cli_line_endings_on_every_platform(monkeypatch):
    document = Document(Path("sprawa/a.pdf"), Path("unused"), Result("appeal", '{\n  "a": 1\n}\n'))
    monkeypatch.setattr(gui_files.os, "linesep", "\r\n")
    with ZipFile(BytesIO(archive([document]))) as bundle:
        assert bundle.read("sprawa/a.json") == b'{\n  "a": 1\n}\n'


def test_a_repeated_run_reuses_results_for_the_same_file_and_classes(tmp_path, monkeypatch):
    calls = []

    def process(path, **kwargs):
        calls.append(path)
        return "appeal", {"pole": "treść"}

    monkeypatch.setattr("kio2json.batch.process_pdf", process)
    monkeypatch.setattr(gui_files, "_results", gui_files.OrderedDict())
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF one")
    for key in ("classes-1", "classes-1", "classes-2"):
        analyze([(Path("sprawa/a.pdf"), source)], tmp_path, [], key)
    assert len(calls) == 2


def test_json_view_spells_the_written_json_and_marks_located_values(tmp_path):
    classes = parse_classes(class_sources(extra=[ROOT / "examples" / "classes"]))
    result = read_document(SAMPLE, classes, explain=True)
    view = str(json_view(result.text, result.trace, selected=2))
    assert html.unescape(re.sub(r"<[^>]+>", "", view)) == result.text
    assert view.count('class="leaf located') == 6
    assert 'class="leaf located selected"' in view
    nip = next(i for i, field in enumerate(result.trace["fields"]) if field["field"] == "nip")
    assert "NIP: 123-456-78-83" in str(evidence(result.trace, nip))
    assert len(result.trace["fields"][nip]["boxes"]) == 1


def test_page_image_draws_the_selected_words():
    plain = page_image(SAMPLE, 1)
    marked = page_image(SAMPLE, 1, [[56.0, 100.0, 200.0, 112.0]])
    assert plain.startswith("data:image/png;base64,") and marked != plain


@pytest.mark.parametrize(
    ("result", "text"),
    [
        (Result(None, "{}\n"), "Nie rozpoznano typu dokumentu, więc zapisano {}."),
        (Result(None, ""), "Nie rozpoznano typu dokumentu, więc zapisano pusty plik (0 B)."),
        (Result(None, "", "no readable text after OCR"), "Na stronach nie ma czytelnego tekstu, także po OCR."),
    ],
)
def test_documents_without_fields_get_plain_polish(result, text):
    assert text in str(outcome(result))
    assert outcome(Result("appeal", json.dumps({"a": 1}))) is None


def test_two_zips_in_one_upload_keep_their_own_files(tmp_path):
    (first := tmp_path / "a").mkdir()
    (second := tmp_path / "b").mkdir()
    uploads = [zip_upload(first, {"s1/x.pdf": b"A"}), zip_upload(second, {"s2/y.pdf": b"B"})]
    sources = upload_sources("sprawa", uploads, tmp_path)
    assert [(name.as_posix(), path.read_bytes()) for name, path in sources] == [("s1/x.pdf", b"A"), ("s2/y.pdf", b"B")]


def test_an_encrypted_zip_entry_is_explained(tmp_path):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as bundle:
        bundle.writestr("sprawa/a.pdf", b"%PDF-1.4")
    raw = bytearray(buffer.getvalue())
    raw[raw.rindex(b"PK\x01\x02") + 8] |= 1  # mark the entry encrypted
    (tmp_path / "u.zip").write_bytes(raw)
    with pytest.raises(ValueError, match="zaszyfrowane"):
        upload_sources("sprawa", [{"name": "u.zip", "datapath": str(tmp_path / "u.zip")}], tmp_path)


def test_zip_names_from_a_unicode_path_field_or_flagless_utf8(tmp_path):
    import struct
    import zlib

    name = "sprawa/pełnomocnictwo.pdf"
    legacy, utf8 = name.encode("cp852"), name.encode()
    info = gui_files.ZipInfo("x" * len(legacy))
    info.extra = struct.pack("<HHBL", 0x7075, 5 + len(utf8), 1, zlib.crc32(legacy)) + utf8
    buffer = BytesIO()
    with ZipFile(buffer, "w") as bundle:
        bundle.writestr(info, b"%PDF")
    (tmp_path / "field.zip").write_bytes(buffer.getvalue().replace(b"x" * len(legacy), legacy))
    field = upload_sources("sprawa", [{"name": "field.zip", "datapath": str(tmp_path / "field.zip")}], tmp_path)
    assert field[0][0].as_posix() == name

    buffer = BytesIO()
    with ZipFile(buffer, "w") as bundle:
        bundle.writestr("y" * len(utf8), b"%PDF")
    (tmp_path / "plain.zip").write_bytes(buffer.getvalue().replace(b"y" * len(utf8), utf8))
    plain = upload_sources("sprawa", [{"name": "plain.zip", "datapath": str(tmp_path / "plain.zip")}], tmp_path)
    assert plain[0][0].as_posix() == name


def test_fallback_results_are_not_cached(tmp_path, monkeypatch):
    calls = []

    def process(path, **kwargs):
        calls.append(path)
        kwargs["on_recovery"]("Used rules after document processing failed.")
        return "appeal", {"pole": "treść"}

    monkeypatch.setattr("kio2json.batch.process_pdf", process)
    monkeypatch.setattr(gui_files, "_results", gui_files.OrderedDict())
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF one")
    for _ in range(2):
        analyze([(Path("sprawa/a.pdf"), source)], tmp_path, [], "key")
    assert len(calls) == 2


def test_the_cache_key_follows_the_ocr_engine(monkeypatch):
    from kio2json import gui

    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.delenv("KIO_OCR_ENGINE", raising=False)
    before = gui.load_classes()[2]
    monkeypatch.setenv("KIO_OCR_ENGINE", "rapidocr")
    assert gui.load_classes()[2] != before


def test_a_folder_root_confines_folder_mode(tmp_path):
    case = tmp_path / "root" / "input" / "sprawa"
    case.mkdir(parents=True)
    (case / "a.pdf").write_bytes(b"%PDF")
    sources = gui_files.folder_sources("input", tmp_path / "root")
    assert [name.as_posix() for name, _ in sources] == ["sprawa/a.pdf"]
    with pytest.raises(ValueError, match="tylko foldery"):
        gui_files.folder_sources("../..", tmp_path / "root")


@pytest.mark.parametrize(
    ("result", "text"),
    [
        (Result(None, "", "OCRRecognitionError: timeout"), "Nie udało się przetworzyć dokumentu."),
        (Result(None, "", "PdfiumError: Failed to load document"), "Plik może być uszkodzony"),
        (Result(None, "", used_recovery=True), "awaryjny odczyt regułami nie powiodły się"),
    ],
)
def test_failures_are_described_by_their_cause(result, text):
    assert text in str(outcome(result))


def test_an_empty_optional_capture_keeps_the_trace(tmp_path):
    from kio2json.class_config import class_sources

    toml = tmp_path / "form.toml"
    toml.write_text(
        """id = "form"
engines = ["labelled_fields"]
[routing]
required = ['^Formularz$']
[fields.numer]
type = "string"
instruction = "Number."
pattern = '^Numer:[ \\t]*([A-Z]\\d+)?.*$'
""",
        encoding="utf-8",
    )
    from snapshots.generate_native import write_native_pdf

    pdf = tmp_path / "form.pdf"
    write_native_pdf(pdf, ["Formularz\nNumer: brak\nNumer: A7"])
    form = next(c for c in parse_classes(class_sources(extra=[toml])) if c.id == "form")
    trace = read_document(pdf, [form], explain=True).trace
    assert "trace_error" not in trace and trace["class"] == "form"


def test_worker_processes_read_a_case_and_report_each_file(tmp_path, monkeypatch):
    from kio2json.class_config import class_sources

    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(gui_files, "_results", gui_files.OrderedDict())
    files = class_sources(extra=[ROOT / "examples" / "classes"])
    classes = parse_classes(files)
    sources = [(Path("sprawa/a.pdf"), SAMPLE), (Path("sprawa/b.pdf"), SAMPLE)]
    seen = []
    documents = analyze(
        sources,
        tmp_path,
        classes,
        "key",
        class_files=files,
        workers=2,
        on_progress=lambda n, name: seen.append((n, name)),
    )
    assert [d.result.label for d in documents] == ["accession", "accession"]
    assert all(d.result.trace["fields"] for d in documents)
    assert seen == [(1, Path("sprawa/a.pdf")), (2, Path("sprawa/b.pdf"))]


def test_an_expired_ocr_budget_is_recorded_and_not_cached(tmp_path, monkeypatch):
    from time import monotonic

    from kio2json import trace
    from kio2json.ocr_budget import document_budget

    with trace.recording() as events, document_budget(monotonic() - 1):
        pass
    assert events.get("optional_ocr_expired") is True

    calls = []

    def process(path, **kwargs):
        calls.append(path)
        trace.note("optional_ocr_expired", True)
        return "appeal", {"pole": "treść"}

    monkeypatch.setattr("kio2json.batch.process_pdf", process)
    monkeypatch.setattr(gui_files, "_results", gui_files.OrderedDict())
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF one")
    for _ in range(2):
        analyze([(Path("sprawa/a.pdf"), source)], tmp_path, [], "key")
    assert len(calls) == 2


def test_a_damaged_lzma_entry_is_explained(tmp_path):
    import zipfile

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=zipfile.ZIP_LZMA) as bundle:
        bundle.writestr("s/a.pdf", b"%PDF-1.4 " * 100)
    raw = bytearray(buffer.getvalue())
    raw[30 + len("s/a.pdf") + 4] = 0xFF  # damage the first LZMA property byte
    (tmp_path / "u.zip").write_bytes(raw)
    with pytest.raises(ValueError, match="rozpakować"):
        upload_sources("sprawa", [{"name": "u.zip", "datapath": str(tmp_path / "u.zip")}], tmp_path)


def test_the_upload_limit_stops_a_second_zip_before_unpacking(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_files, "ZIP_MAX_FILES", 1)
    (first := tmp_path / "a").mkdir()
    (second := tmp_path / "b").mkdir()
    uploads = [zip_upload(first, {"s1/x.pdf": b"A"}), zip_upload(second, {"s2/y.pdf": b"B"})]
    with pytest.raises(ValueError, match="za duże"):
        upload_sources("sprawa", uploads, tmp_path)
    assert not list(tmp_path.glob("zip1-*.pdf"))


def test_the_cache_key_covers_every_kio_setting(monkeypatch):
    from kio2json import gui

    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    before = gui.load_classes()[2]
    monkeypatch.setenv("KIO_LLM_OUTPUT", "spans")
    assert gui.load_classes()[2] != before


def test_an_empty_folder_field_opens_the_folder_root(tmp_path):
    (tmp_path / "sprawa").mkdir()
    (tmp_path / "sprawa" / "a.pdf").write_bytes(b"%PDF")
    assert [name.as_posix() for name, _ in gui_files.folder_sources("", tmp_path)] == ["sprawa/a.pdf"]


@pytest.mark.parametrize(
    ("recovery", "text"),
    [
        ("Could not read document. Returning {}.", "Nie udało się odczytać pliku"),
        ("Used rules after document processing failed.", "reguły nie rozpoznały jego typu"),
        ("Document processing and rule recovery failed. Returning {}.", "nie powiodły się"),
    ],
)
def test_recovery_messages_follow_what_happened(recovery, text):
    result = Result(None, used_recovery=True, trace={"class": None, "fields": [], "recovery": recovery})
    assert text in str(outcome(result))


def test_a_nested_label_marks_the_words_inside_its_own_object(tmp_path):
    from kio2json.class_config import class_sources

    toml = tmp_path / "pair.toml"
    toml.write_text(
        r"""id = "pair"
engines = ["labelled_fields"]
[routing]
required = ['^Wniosek$']
[fields.wnioskodawca]
type = "object"
instruction = "Applicant."
pattern = '(?s)^Wnioskodawca:\n(.*?)^Zamawiający:'
[fields.wnioskodawca.fields.nip]
type = "string"
instruction = "Applicant NIP."
pattern = '^NIP:[ \t]*(\d+)$'
[fields.zamawiajacy]
type = "object"
instruction = "Contracting authority."
pattern = '(?s)^Zamawiający:\n(.*)'
[fields.zamawiajacy.fields.nip]
type = "string"
instruction = "Authority NIP."
pattern = '^NIP:[ \t]*(\d+)$'
""",
        encoding="utf-8",
    )
    from snapshots.generate_native import write_native_pdf

    pdf = tmp_path / "pair.pdf"
    write_native_pdf(pdf, ["Wniosek\nWnioskodawca:\nNIP: 111\nZamawiający:\nNIP: 222"])
    pair = next(c for c in parse_classes(class_sources(extra=[toml])) if c.id == "pair")
    result = read_document(pdf, [pair], explain=True)
    assert json.loads(result.text) == {"wnioskodawca": {"nip": "111"}, "zamawiajacy": {"nip": "222"}}
    fields = {field["field"]: field for field in result.trace["fields"]}
    assert fields["zamawiajacy.nip"]["snippet"] == "NIP: 222"
