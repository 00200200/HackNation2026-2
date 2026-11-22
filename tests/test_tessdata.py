import hashlib

import pytest

from kio2json import pdf_text


def test_vendored_models_match_pinned_hashes():
    pdf_text._language_dir.cache_clear()
    assert pdf_text._language_dir() == str(pdf_text.TESSDATA_DIR)
    assert (pdf_text.TESSDATA_DIR / "LICENSE").read_text().lstrip().startswith("Apache License")


def test_missing_or_altered_model_names_the_file(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_text, "TESSDATA_DIR", tmp_path)
    payload = b"model"
    monkeypatch.setattr(pdf_text, "TESSDATA_SHA256", {"pol.traineddata": hashlib.sha256(payload).hexdigest()})
    pdf_text._language_dir.cache_clear()
    with pytest.raises(FileNotFoundError, match="pol.traineddata"):
        pdf_text._language_dir()
    (tmp_path / "pol.traineddata").write_bytes(b"altered")
    with pytest.raises(RuntimeError, match="SHA-256"):
        pdf_text._language_dir()
    (tmp_path / "pol.traineddata").write_bytes(payload)
    assert pdf_text._language_dir() == str(tmp_path)
    pdf_text._language_dir.cache_clear()
