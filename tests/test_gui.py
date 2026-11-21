from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

import pytest
from shiny.pytest import create_app_fixture
from shiny.testserver import test_server as shiny_session

from kio2json import gui
from kio2json.gui_files import analyze, archive, folder_sources, upload_sources

live_app = create_app_fixture(Path(__file__).resolve().parents[1] / "kio2json/gui.py")


def test_headless_page(live_app):
    with urlopen(live_app.url, timeout=5) as page:
        html = page.read().decode()
    assert 'lang="pl"' in html
    assert "Analizuj dokumenty" in html


def test_results_preserve_cases_empty_files_and_failures(tmp_path, monkeypatch):
    root = tmp_path / "input"
    for case, name in (("a", "same.PDF"), ("b", "same.pdf"), ("b", "broken.pdf")):
        folder = root / case
        folder.mkdir(exist_ok=True, parents=True)
        (folder / name).write_text(name)

    def process(path, **kwargs):
        match path.read_text():
            case "same.PDF":
                return "appeal", {"pole": "treść"}
            case "same.pdf":
                return None, {}
            case _:
                raise ValueError("uszkodzony plik")

    monkeypatch.setattr("kio2json.batch.process_pdf", process)
    results = analyze(folder_sources(str(root)), tmp_path)
    with ZipFile(BytesIO(archive(results))) as files:
        assert files.read("a/same.json").decode() == '{\n  "pole": "treść"\n}\n'
        assert files.read("b/same.json") == files.read("b/broken.json") == b""
    assert [r.result.error for r in results] == [None, "ValueError: uszkodzony plik", None]
    assert folder_sources(str(root / "a"))[0][0].as_posix() == "a/same.PDF"


@pytest.mark.parametrize("name", ["../x.pdf", r"C:\tmp\x.pdf", "x.txt", "NUL.pdf", "C:file.pdf"])
def test_reject_unsafe_upload_names(name):
    with pytest.raises(ValueError):
        upload_sources("sprawa", [{"name": name, "datapath": "unused"}])


def test_windows_drive_in_case_name():
    with pytest.raises(ValueError):
        upload_sources("C:case", [{"name": "x.pdf", "datapath": "unused"}])


def test_unknown_user_folder():
    with pytest.raises(ValueError, match="folder"):
        folder_sources("~nonexistent_hn_test_account")


def test_upload_collision_and_empty_folder(tmp_path):
    paths = [{"name": name, "datapath": "unused"} for name in ["one.PDF", "ONE.pdf"]]
    with pytest.raises(ValueError, match="nazw"):
        analyze(upload_sources("sprawa", paths), tmp_path)
    with pytest.raises(ValueError, match="PDF"):
        folder_sources(str(tmp_path))


def test_session_reports_failed_document_and_invalid_new_run(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"broken")
    with shiny_session(gui.app) as session:
        session.set_inputs(mode="folder", folder=str(tmp_path), run=1, document="0", page="1")
        assert session.get_output("classification") == "Nie udało się odczytać dokumentu"
        assert "No /Root object" in session.get_output("result_text").value
        session.set_inputs(folder=str(tmp_path / "missing"), run=2)
        assert "folder" in session.get_output("notice").value.lower()
