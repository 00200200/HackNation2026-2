import hashlib
import io
import runpy
from pathlib import Path
from urllib import request
from urllib.error import URLError

import pytest


@pytest.fixture
def read_model():
    setup = Path(__file__).resolve().parents[1] / "packaging/polish_ocr_data/setup.py"
    return runpy.run_path(str(setup))["read_model"]


def test_fetch_failure_explains_manual_install(read_model, monkeypatch):
    def offline(url, *, timeout):
        assert 0 < timeout <= 60
        raise URLError("network unavailable")

    monkeypatch.delenv("KIO_TESSDATA_SOURCE", raising=False)
    monkeypatch.setattr(request, "urlopen", offline)
    with pytest.raises(RuntimeError) as caught:
        read_model("pol.traineddata", "unused")
    message = str(caught.value)
    assert "https://raw.githubusercontent.com/" in message
    assert "/pol.traineddata" in message
    assert "eng.traineddata" in message
    assert "KIO_TESSDATA_SOURCE" in message
    assert "pip install -r requirements.txt" in message


def test_models_use_pinned_hash_for_download_and_manual_supply(read_model, monkeypatch, tmp_path):
    name = "eng.traineddata"
    payload = b"sample model"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.delenv("KIO_TESSDATA_SOURCE", raising=False)
    monkeypatch.setattr(request, "urlopen", lambda url, *, timeout: io.BytesIO(payload))
    assert read_model(name, digest) == payload
    with pytest.raises(RuntimeError, match="SHA-256"):
        read_model(name, "0" * 64)

    def unexpected_download(*args, **kwargs):
        pytest.fail("supplying models by hand must work without a download")

    monkeypatch.setenv("KIO_TESSDATA_SOURCE", str(tmp_path))
    monkeypatch.setattr(request, "urlopen", unexpected_download)
    with pytest.raises(RuntimeError, match="eng.traineddata"):
        read_model(name, digest)
    (tmp_path / name).write_bytes(b"wrong model")
    with pytest.raises(RuntimeError, match="SHA-256"):
        read_model(name, digest)
    (tmp_path / name).write_bytes(payload)
    assert read_model(name, digest) == payload
