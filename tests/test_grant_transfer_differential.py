"""Review reproductions and independently invented grants/receipts through the production PDF pipeline."""

import json

import pytest
from snapshots.generate_grant_transfer import (
    BASE,
    CASES,
    EXTRA_CASES,
    EXTRA_OUTPUTS,
    NATIVE_BASE,
    NATIVE_OUTPUTS,
    load_json,
)
from snapshots.generate_native import write_native_pdf
from snapshots.grant_transfer_changes import INTENDED_CHANGES, NATIVE_IMPROVEMENTS, expected_result
from test_appeal_differential import expected_native_result

from kio2json import pdf_text, pipeline

INPUTS = load_json(CASES) | load_json(EXTRA_CASES)
NATIVE = load_json(NATIVE_OUTPUTS)
EXTRA = load_json(EXTRA_OUTPUTS)
BASE_OUTPUTS = NATIVE["outputs"] | EXTRA["outputs"]


def test_base_snapshot_coverage():
    assert NATIVE["base"] == NATIVE_BASE and EXTRA["base"] == BASE
    parity_cases = {k for k in INPUTS if k.startswith(("task40/", "simple/"))}
    assert len(parity_cases) == 42 and parity_cases.isdisjoint(INTENDED_CHANGES)
    assert all(BASE_OUTPUTS[k][0] is not None for k in parity_cases)
    assert INPUTS.keys() == BASE_OUTPUTS.keys()
    assert set(INTENDED_CHANGES) <= INPUTS.keys()
    assert INTENDED_CHANGES.keys() & NATIVE["outputs"].keys() == NATIVE_IMPROVEMENTS
    assert sum(key.startswith("invented/") for key in INPUTS) >= 30
    assert {f"task32/T{i}" for i in range(1, 7)} | {f"task32/P{i}" for i in range(1, 5)} <= INPUTS.keys()
    assert {key.split("/")[0] for key in INPUTS} >= {"task1", "task4", "task11", "task22", "task30", "task32"}


@pytest.mark.parametrize("case", INPUTS)
def test_grant_transfer_matches_integration_base(case, tmp_path, monkeypatch):
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setattr(pdf_text, "_ocr", lambda *a, **kw: pytest.fail("Unexpected OCR on native fixture"))
    path = tmp_path / "document.pdf"
    write_native_pdf(path, INPUTS[case])
    actual = pipeline.process_pdf(path)
    expected = expected_result(case, expected_native_result(INPUTS[case], BASE_OUTPUTS[case]))
    # Preserve serializer key/list order and distinguish JSON numeric fields from boolean flags.
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
