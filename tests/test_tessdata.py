import hashlib

import pytest

from kio2json import pdf_text


@pytest.fixture(autouse=True)
def fresh_language_dir_cache():
    # monkeypatch is undone before this teardown runs, so a failing test cannot leave a temporary directory cached.
    pdf_text._language_dir.cache_clear()
    yield
    pdf_text._language_dir.cache_clear()


def test_vendored_models_match_pinned_hashes():
    assert pdf_text._language_dir() == str(pdf_text.TESSDATA_DIR)
    assert (pdf_text.TESSDATA_DIR / "LICENSE").read_text(encoding="utf-8").lstrip().startswith("Apache License")


def test_missing_or_altered_model_names_the_file(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_text, "TESSDATA_DIR", tmp_path)
    payload = b"model"
    monkeypatch.setattr(pdf_text, "TESSDATA_SHA256", {"pol.traineddata": hashlib.sha256(payload).hexdigest()})
    with pytest.raises(FileNotFoundError, match="pol.traineddata"):
        pdf_text._language_dir()
    (tmp_path / "pol.traineddata").write_bytes(b"altered")
    with pytest.raises(RuntimeError, match="SHA-256"):
        pdf_text._language_dir()
    (tmp_path / "pol.traineddata").write_bytes(payload)
    assert pdf_text._language_dir() == str(tmp_path)
