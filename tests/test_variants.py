import io
from collections import Counter

import pdfplumber

from evals.run import DATA
from evals.variant_cases import NEGATIVES, PROFILES, SEED, generate
from evals.variants import schedule


def test_balanced_first_cycle_and_stable_prefix():
    cases = list(schedule(60, SEED))
    assert {row[1] for row in cases} == set(range(1, 61))
    assert Counter(row[2] for row in cases) == dict.fromkeys(PROFILES, 10)
    assert Counter(row[3] for row in cases) == dict.fromkeys(NEGATIVES, 10)
    assert cases == list(schedule(120, SEED))[:60]


def test_generated_pdf_matches_printed_reference(monkeypatch):
    args = (DATA / "przyklad_03", 0, SEED, "alternative-formats", "invoice")
    docs = generate(*args)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1800000000")
    assert docs == generate(*args)
    assert len(docs) == 4
    receipt = next((gold["przelew_bankowy"], pdf) for _, gold, pdf in docs if "przelew_bankowy" in gold)
    tx, raw = receipt
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        text = " ".join(page.extract_text() for page in doc.pages)
    assert tx["tytul"] in " ".join(text.split())
    for key in ("na_rachunek", "z_rachunku", "numer_transakcji"):
        assert tx[key] in "".join(text.split())
    appeal = next(gold for _, gold, _ in docs if "OdwolanieKIO" in gold)
    assert appeal["ZamowieniePubliczne"]["numer_postepowania"] in tx["tytul"]


def test_scans_contain_no_text_layer():
    docs = generate(DATA / "przyklad_03", 1, SEED, "scan", "invoice")
    for _, _, raw in docs:
        with pdfplumber.open(io.BytesIO(raw)) as doc:
            assert all(page.images and not page.chars for page in doc.pages)


def test_gate_detects_regression_and_preserves_baseline(tmp_path, monkeypatch):
    import json

    from evals import run
    from evals.variants import evaluate_variants

    monkeypatch.setenv("KIO_OCR_ENGINE", "rapidocr")
    monkeypatch.setenv("KIO_CLASSES_DIR", "custom-config")

    def empty_predictions(cmd, source, output, *, env):
        assert not env["KIO_LLM_API_KEY"]
        assert "KIO_OCR_ENGINE" not in env
        assert "KIO_CLASSES_DIR" not in env
        for pdf in source.glob("*/*.pdf"):
            prediction = output / pdf.relative_to(source).with_suffix(".json")
            prediction.parent.mkdir(exist_ok=True)
            prediction.write_text("{}\n", encoding="utf-8")
        return 0, None

    monkeypatch.setattr(run, "run_app", empty_predictions)
    baseline = tmp_path / "baseline.json"
    assert evaluate_variants(1, DATA, "fixture", baseline, None) == 0
    expected = json.loads(baseline.read_text())
    assert expected["outputs_complete"] == 1
    assert expected["negatives_empty"] == 1
    assert expected["micro_f1"] == 0
    expected["micro_f1"] = 0.5
    baseline.write_text(json.dumps(expected))
    candidate = tmp_path / "candidate.json"
    assert evaluate_variants(1, DATA, "fixture", candidate, baseline) == 1
    assert json.loads(candidate.read_text())["micro_f1"] == 0
    assert json.loads(baseline.read_text()) == expected
