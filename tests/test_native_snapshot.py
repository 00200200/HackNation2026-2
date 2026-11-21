"""Differential check through the same text-layer PDF path used by the CLI."""

import json

import pdfplumber
import pytest
from snapshots.generate_native import BASE, CASES, write_native_pdf
from snapshots.grant_transfer_changes import expected_result
from test_appeal_differential import expected_native_result

from kio2json import pdf_text, pipeline

INPUTS = json.loads(CASES.read_text(encoding="utf-8"))
SNAPSHOT = json.loads(CASES.with_name("native_outputs.json").read_text(encoding="utf-8"))


def test_snapshot_coverage():
    assert SNAPSHOT["base"] == BASE
    assert INPUTS.keys() == SNAPSHOT["outputs"].keys()
    assert sum(name.startswith("new/") for name in INPUTS) >= 30


@pytest.mark.parametrize("name", INPUTS)
def test_native_pdf_matches_base(name, tmp_path, monkeypatch):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(pdf_text, "_ocr", lambda *a, **kw: pytest.fail("OCR requested on native fixture"))
    path = tmp_path / "document.pdf"
    pages = INPUTS[name]
    write_native_pdf(path, pages)
    with pdfplumber.open(path) as pdf:
        assert [page.extract_text() for page in pdf.pages] == [page.rstrip("\n") for page in pages]
    result = pipeline.process_pdf(path)
    # Serialization also checks field order and distinguishes booleans from integer flags.
    expected = expected_result(name, expected_native_result(pages, SNAPSHOT["outputs"][name]))
    assert json.dumps(result, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
