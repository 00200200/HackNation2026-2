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
    parity_cases = {k for k in INPUTS if k.startswith(("task40/", "simple/", "review47/"))}
    assert len(parity_cases) == 45 and parity_cases.isdisjoint(INTENDED_CHANGES)
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


def test_approval_signatures_follow_visible_side_by_side_widgets(tmp_path):
    from hashlib import sha256

    from kio2json.grant_certificates import _visible_order

    path = tmp_path / "signed.pdf"
    path.write_bytes(b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 500 500] /Annots [4 0 R 5 0 R] >> endobj
4 0 obj << /Type /Annot /Subtype /Widget /FT /Sig /Rect [210 60 297 112] /V << /Contents (right) >> >> endobj
5 0 obj << /Type /Annot /Subtype /Widget /FT /Sig /Rect [42 48 143 96] /V << /Contents (left) >> >> endobj
trailer << /Root 1 0 R >>
%%EOF
""")
    certificates = {sha256(b"right").digest(): ["Mira Wisła"], sha256(b"left").digest(): ["Jan Rydz"]}
    assert _visible_order(path, certificates) == ["Jan Rydz", "Mira Wisła"]
    assert _visible_order(path, {**certificates, b"invisible": ["Eryk Klon"]}) == []


def test_intended_native_tax_number_from_adjacent_header_registry_rows(tmp_path):
    # The integration base leaves the NIP null after a letterhead label.
    page = """Biuro spółki:
ul. Łagodna 5
NIP: 525-00-07-738
KRS: 0000812656
PEŁNOMOCNICTWO
Mocodawca: Ciepły Żagiel S.A., KRS 0000812656, udziela pełnomocnictwa."""
    path = tmp_path / "document.pdf"
    write_native_pdf(path, [page])
    kind, result = pipeline.process_pdf(path)
    assert kind == "power_of_attorney"
    assert result["mocodawca"] == [
        {
            "data": {
                "imie_nazwisko": None,
                "krs": "0000812656",
                "nazwa": "Ciepły Żagiel S.A.",
                "nip": "5250007738",
                "typ": "osoba_prawna",
            },
            "podpisujacy": [],
        }
    ]
