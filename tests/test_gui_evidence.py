"""Viewer evidence: case ZIP uploads, cached reads, CLI-identical ZIPs and highlighted sources."""

import html
import json
import os
import re
import sys
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
    sources = gui_files.folder_sources("input", tmp_path / "root", tmp_path)
    assert [name.as_posix() for name, _ in sources] == ["sprawa/a.pdf"]
    with pytest.raises(ValueError, match="tylko foldery"):
        gui_files.folder_sources("../..", tmp_path / "root", tmp_path)


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


@pytest.mark.parametrize(("codec", "method"), [("lzma", "ZIP_LZMA"), ("bz2", "ZIP_BZIP2")])
def test_an_lzma_or_bzip2_entry_is_refused_before_decoding(tmp_path, codec, method):
    import zipfile

    pytest.importorskip(codec)
    with ZipFile(tmp_path / "u.zip", "w", compression=getattr(zipfile, method)) as bundle:
        bundle.writestr("s/a.pdf", b"%PDF-1.4 " * 100)
    with pytest.raises(ValueError, match="metodą, której nie obsługujemy"):
        upload_sources("sprawa", [{"name": "u.zip", "datapath": str(tmp_path / "u.zip")}], tmp_path)


def test_a_zip_variant_zipfile_cannot_open_is_explained(tmp_path, monkeypatch):
    def newer(*_):
        raise NotImplementedError("zip file version 9.9")

    monkeypatch.setattr(gui_files, "ZipFile", newer)
    with pytest.raises(ValueError, match="wariantu ZIP"):
        upload_sources("sprawa", [{"name": "u.zip", "datapath": str(tmp_path / "u.zip")}], tmp_path)


def test_a_windows_separator_is_not_taken_for_a_unicode_name():
    from zipfile import ZipInfo

    raw = "s\\Pełnomocnictwo.pdf".encode("cp852").decode("cp437")
    entry = ZipInfo(raw.replace("\\", "/"))  # What zipfile builds on Windows.
    entry.orig_filename = raw
    assert gui_files.entry_name(entry) == "s\\Pełnomocnictwo.pdf"
    assert gui_files.entry_name(ZipInfo(raw)) == "s\\Pełnomocnictwo.pdf"  # On macOS and Linux the name stays.


def test_snapshots_are_hashed_only_for_the_cache(tmp_path, monkeypatch):
    import hashlib

    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF one")
    hashed = []
    monkeypatch.setattr(gui_files, "_results", type(gui_files._results)())
    monkeypatch.setattr(hashlib, "file_digest", lambda file, name: hashed.append(name) or hashlib.sha256(file.read()))
    monkeypatch.setattr(gui_files, "read_document", lambda *_, **__: Result(None))
    analyze([(Path("sprawa/a.pdf"), source)], tmp_path, [], "")
    assert hashed == []
    analyze([(Path("sprawa/b.pdf"), source)], tmp_path, [], "key")
    assert hashed == ["sha256"]


def test_the_upload_limit_stops_a_second_zip_before_unpacking(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_files, "ZIP_MAX_FILES", 1)
    (first := tmp_path / "a").mkdir()
    (second := tmp_path / "b").mkdir()
    uploads = [zip_upload(first, {"s1/x.pdf": b"A"}), zip_upload(second, {"s2/y.pdf": b"B"})]
    with pytest.raises(ValueError, match="Przekroczono limit przesyłania"):
        upload_sources("sprawa", uploads, tmp_path)
    assert not list(tmp_path.glob("zip1-*.pdf"))


def test_the_cache_key_covers_every_kio_setting(monkeypatch):
    from kio2json import gui

    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.delenv("KIO_LLM_OUTPUT", raising=False)
    before = gui.load_classes()[2]
    monkeypatch.setenv("KIO_LLM_OUTPUT", "spans")
    assert gui.load_classes()[2] != before


def test_an_empty_folder_field_opens_the_folder_root(tmp_path):
    (tmp_path / "sprawa").mkdir()
    (tmp_path / "sprawa" / "a.pdf").write_bytes(b"%PDF")
    (copies := tmp_path / "copies").mkdir()
    assert [name.as_posix() for name, _ in gui_files.folder_sources("", tmp_path, copies)] == ["sprawa/a.pdf"]


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


def test_a_damaged_entry_gets_a_polish_message_and_a_disk_error_keeps_its_own(tmp_path, monkeypatch):
    import errno

    upload = zip_upload(tmp_path, {"s1/a.pdf": b"%PDF-1.4"})
    monkeypatch.setattr(gui_files, "bounded_copy", lambda *_: (_ for _ in ()).throw(OSError("bad data")))
    with pytest.raises(ValueError, match="Nie udało się rozpakować s1/a.pdf"):
        upload_sources("sprawa", [upload], tmp_path)
    full = OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(gui_files, "bounded_copy", lambda *_: (_ for _ in ()).throw(full))
    with pytest.raises(OSError, match="No space left"):
        upload_sources("sprawa", [upload], tmp_path)


def test_the_fallback_trace_keeps_the_expired_optional_ocr(monkeypatch):
    from kio2json import batch

    monkeypatch.setattr(batch, "build", lambda *_: 1 / 0)
    trace = batch.explained("appeal", {}, {"warnings": [], "optional_ocr_expired": True})
    assert trace["optional_ocr_expired"] is True
    assert trace["trace_error"].startswith("ZeroDivisionError")


@pytest.mark.parametrize("name", ["../../x.pdf", "/tmp/abs/x.pdf", "C:\\cases\\x.pdf", "sprawa/../../x.pdf"])
def test_a_zip_entry_cannot_name_a_path_outside_its_case(tmp_path, name):
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    with pytest.raises(ValueError, match="Niedozwolona nazwa"):
        upload_sources("sprawa", [zip_upload(tmp_path, {name: b"%PDF-1.4"})], unpacked)
    assert not list(unpacked.iterdir()) and not (tmp_path.parent / "x.pdf").exists()


def test_a_zip_entry_that_is_a_symlink_is_refused(tmp_path):
    import stat
    from zipfile import ZipInfo

    link = ZipInfo("sprawa/link.pdf")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    path = tmp_path / "upload.zip"
    with ZipFile(path, "w") as bundle:
        bundle.writestr(link, "/etc/passwd")
    with pytest.raises(ValueError, match="dowiązanie"):
        upload_sources("sprawa", [{"name": "sprawy.zip", "datapath": str(path)}], tmp_path)


SYMLINKS = pytest.mark.skipif(sys.platform == "win32", reason="creating links on Windows needs extra rights")


@SYMLINKS
def test_a_link_inside_the_folder_root_cannot_open_a_file_outside(tmp_path):
    from kio2json.gui_files import folder_sources

    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "sprawa").mkdir(parents=True)
    outside.mkdir()
    (root / "sprawa" / "pismo.pdf").write_bytes(b"%PDF-1.4")
    (outside / "obcy.pdf").write_bytes(b"%PDF-1.4")
    (root / "sprawa" / "skrot.pdf").symlink_to(root / "sprawa" / "pismo.pdf")
    assert len(folder_sources("sprawa", root, tmp_path)) == 2  # A link that stays inside the root still opens.
    (root / "sprawa" / "link.pdf").symlink_to(outside / "obcy.pdf")
    with pytest.raises(ValueError, match="prowadzi poza"):
        folder_sources("sprawa", root, tmp_path)
    assert len(folder_sources(str(root / "sprawa"))) == 3  # On localhost, without a root, links are the user's own.


@SYMLINKS
def test_a_link_chain_too_long_to_resolve_cannot_leave_the_folder_root(tmp_path):
    from kio2json.gui_files import folder_sources

    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "obcy.pdf").write_bytes(b"%PDF-secret")
    current, links = root, []
    for level in range(24):  # Each link adds 200 characters, past PATH_MAX once expanded.
        name = f"{level:02d}" + "d" * 198
        (current / name).mkdir()
        (current / f"l{level}").symlink_to(name)
        current, links = current / f"l{level}", [*links, f"l{level}"]
    (current / "esc").symlink_to("../" * 25 + "outside")
    with pytest.raises(ValueError, match="tylko foldery w"):
        folder_sources("/".join([*links, "esc"]), root, tmp_path)
    # Inside a real case folder, only the check of each PDF's real target catches the same chain.
    (root / "sprawa").mkdir()
    (root / "sprawa" / "obcy.pdf").symlink_to("../" + "/".join([*links, "esc", "obcy.pdf"]))
    with pytest.raises(ValueError, match="prowadzi poza"):
        folder_sources("sprawa", root, tmp_path)
    (root / "pismo.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="istniejącego folderu"):
        folder_sources("pismo.pdf/x", root, tmp_path)


def test_plain_pdfs_count_toward_the_upload_byte_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_files, "ZIP_MAX_BYTES", 12)
    plain = tmp_path / "plain.pdf"
    plain.write_bytes(b"%PDF-1.4")  # 8 bytes
    (zipped := tmp_path / "z").mkdir()
    uploads = [{"name": "a.pdf", "datapath": str(plain)}, zip_upload(zipped, {"s/b.pdf": b"%PDF-"})]
    with pytest.raises(ValueError, match="Przekroczono limit"):
        upload_sources("sprawa", uploads, tmp_path)


@SYMLINKS
def test_a_link_changed_after_the_check_cannot_redirect_the_copy(tmp_path, monkeypatch):
    from kio2json.gui_files import folder_sources, opened_path

    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "sprawa").mkdir(parents=True)
    outside.mkdir()
    (root / "sprawa" / "pismo.pdf").write_bytes(b"%PDF-inside")
    (outside / "obcy.pdf").write_bytes(b"%PDF-outside")
    link = root / "sprawa" / "skrot.pdf"
    link.symlink_to(root / "sprawa" / "pismo.pdf")

    seen = []

    def swap_after_check(descriptor):
        real = opened_path(descriptor)
        seen.append(real.name)
        if seen.count("pismo.pdf") == 2:  # The link's open file names its target; swap the link once checked.
            link.unlink()
            link.symlink_to(outside / "obcy.pdf")
        return real

    monkeypatch.setattr(gui_files, "opened_path", swap_after_check)
    (copies := tmp_path / "copies").mkdir()
    read = {name.name: path.read_bytes() for name, path in folder_sources("sprawa", root, copies)}
    assert read == {"pismo.pdf": b"%PDF-inside", "skrot.pdf": b"%PDF-inside"}
    assert link.resolve() == (outside / "obcy.pdf").resolve()  # The swap happened after the check.


def test_a_forged_upload_path_outside_the_session_upload_folder_is_refused(tmp_path):
    from shiny.testserver import test_server

    from kio2json import gui

    secret = tmp_path / "server.pdf"
    secret.write_bytes(b"%PDF-secret")
    forged = [{"name": "a.pdf", "size": 11, "type": "application/pdf", "datapath": str(secret)}]
    with test_server(gui.app) as session:
        session.set_inputs(mode="upload", case="sprawa", files=forged, run=1)
        assert "spoza tego wgrania" in session.get_output("notice").value


def test_a_file_in_the_session_upload_folder_is_read(tmp_path, monkeypatch):
    from shiny.testserver import test_server

    from kio2json import gui

    (folder := tmp_path / "uploads" / "0").mkdir(parents=True)
    (folder / "0.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(gui, "upload_folder", lambda session: tmp_path / "uploads")
    files = [{"name": "a.pdf", "size": 8, "type": "application/pdf", "datapath": str(folder / "0.pdf")}]
    with test_server(gui.app) as session:
        session.set_inputs(mode="upload", case="sprawa", files=files, run=1)
        assert "Liczba dokumentów: 1" in session.get_output("notice").value


def test_a_folder_root_typed_in_another_case_still_opens(tmp_path):
    from kio2json.gui_files import folder_sources

    (tmp_path / "Cases" / "sprawa").mkdir(parents=True)
    (tmp_path / "Cases" / "sprawa" / "a.pdf").write_bytes(b"%PDF-1.4")
    if not (tmp_path / "cases").exists():
        pytest.skip("this file system tells letter case apart")
    (copies := tmp_path / "copies").mkdir()
    assert [name.as_posix() for name, _ in folder_sources("sprawa", tmp_path / "cases", copies)] == ["sprawa/a.pdf"]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs file permissions that bind a user")
def test_an_unreadable_pdf_under_the_folder_root_names_the_read_error(tmp_path):
    from kio2json.gui_files import folder_sources

    (tmp_path / "root" / "s").mkdir(parents=True)
    (tmp_path / "root" / "s" / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "root" / "s" / "b.pdf").chmod(0)
    try:
        with pytest.raises(ValueError, match="Nie udało się odczytać pliku b.pdf"):
            folder_sources("s", tmp_path / "root", tmp_path)
    finally:
        (tmp_path / "root" / "s" / "b.pdf").chmod(0o644)


def test_a_real_shiny_upload_passes_the_upload_folder_check_and_the_folder_itself_does_not(tmp_path):
    from shiny._fileupload import FileUploadManager

    manager = FileUploadManager()
    try:
        operation = manager.get_upload_operation(
            manager.create_upload_operation([{"name": "a.pdf", "size": 8, "type": "application/pdf"}])
        )
        operation.file_begin()
        operation.write_chunk(b"%PDF-1.4")
        operation.file_end()
        uploaded = operation.finish()
        uploads = Path(manager._basedir)
        assert [name.as_posix() for name, _ in upload_sources("sprawa", uploaded, tmp_path, uploads)] == [
            "sprawa/a.pdf"
        ]
        folder = [{"name": "a.pdf", "size": 8, "type": "application/pdf", "datapath": str(uploads)}]
        with pytest.raises(ValueError, match="spoza tego wgrania"):
            upload_sources("sprawa", folder, tmp_path, uploads)
    finally:
        manager.rm_upload_dir()


def test_a_zip_bomb_is_refused_before_it_is_unpacked(tmp_path):
    import zipfile

    with ZipFile(tmp_path / "u.zip", "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("s/bomb.pdf", b"%PDF-1.4" + b"\0" * (4 << 20))  # 4 MB of zeros pack into a few KB.
    with pytest.raises(ValueError, match="razy większy niż w archiwum"):
        upload_sources("sprawa", [{"name": "u.zip", "datapath": str(tmp_path / "u.zip")}], tmp_path)
    assert not list(tmp_path.glob("zip0-*.pdf"))


def test_a_zip_with_too_many_entries_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(gui_files, "ZIP_MAX_ENTRIES", 2)
    upload = zip_upload(tmp_path, {"s/a.pdf": b"%PDF", "s/b.pdf": b"%PDF", "s/c.txt": b"x"})
    with pytest.raises(ValueError, match="pozycji"):
        upload_sources("sprawa", [upload], tmp_path)


def test_a_stream_longer_than_its_limit_is_refused_while_copying():
    copy = BytesIO()
    assert gui_files.bounded_copy(BytesIO(b"12345"), copy, 5) == 5
    with pytest.raises(ValueError, match="Przekroczono limit"):
        gui_files.bounded_copy(BytesIO(b"123456"), BytesIO(), 5)


@SYMLINKS
def test_a_folder_root_is_refused_where_the_system_cannot_name_an_open_file(tmp_path, monkeypatch):
    from kio2json.gui_files import folder_sources

    (tmp_path / "root" / "sprawa").mkdir(parents=True)
    (tmp_path / "root" / "sprawa" / "a.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(gui_files, "opened_path", lambda descriptor: None)
    with pytest.raises(ValueError, match="bezpiecznie"):
        folder_sources("sprawa", tmp_path / "root", tmp_path)


def test_a_snapshot_that_cannot_be_read_back_fails_alone(tmp_path, monkeypatch):
    import hashlib

    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    first.write_bytes(b"%PDF one")
    second.write_bytes(b"%PDF two")
    calls = []

    def flaky(file, name):
        calls.append(name)
        if len(calls) == 1:
            raise OSError("readback failed")
        return hashlib.sha256(file.read())

    monkeypatch.setattr(gui_files, "_results", type(gui_files._results)())
    monkeypatch.setattr(hashlib, "file_digest", flaky)
    monkeypatch.setattr(gui_files, "read_document", lambda *_, **__: Result("appeal"))
    documents = analyze([(Path("s/a.pdf"), first), (Path("s/b.pdf"), second)], tmp_path, [], "key")
    assert [document.result.error for document in documents] == ["readback failed", None]
