from pathlib import Path

import pytest

from kio2json import llm, pipeline, rapid_worker
from kio2json.class_config import DEFAULT_DIR, load_classes


def test_displayed_readings_have_separate_quote_boundaries_and_fit_utf8_budget():
    from kio2json.model_pages import model_readings

    pages = ["ół" * 60, "B" * 200]
    prompt, sources = model_readings("A", pages, 340)
    assert len(prompt.encode()) <= 340
    assert sources[0] == ("A", "A")
    assert sources[1] == (pages[0], pages[0])
    assert sources[2][0] == pages[1]
    assert 0 < len(sources[2][1]) < len(pages[1])
    assert prompt.endswith(sources[1][1] + "\n" + sources[2][1])
    prompt, sources = model_readings("ąć" * 50, [""], 17)
    assert len(prompt.encode()) <= 17 and sources == [("ąć" * 50, prompt)]


@pytest.fixture
def keyed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KIO_CLASSES_DIR", raising=False)
    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract-dpi")
    for k, v in {
        "BASE_URL": "http://127.0.0.1",
        "MODEL": "test",
        "API_KEY": "fake",
        "MODE": "LR",
        "ROUTING": "fallback",
        "DUAL_OCR": "true",
    }.items():
        monkeypatch.setenv("KIO_LLM_" + k, v)


def test_scanned_model_route_and_extract_share_first_page_but_rules_get_only_primary(keyed, monkeypatch):
    primary = ["Unknown layout", "Native attached note", "Third page"]

    def read(path, *, ocr_pages, **kw):
        ocr_pages.extend([1, 3])
        return primary

    calls = []

    def recognize(path, page, word_boxes, timeout):
        calls.append(page)
        return {1: "PEŁNOMOCNICTWO", 3: "Osobny odczyt"}[page], []

    seen = []

    def route(prompt):
        assert "Unknown layout" in prompt and "PEŁNOMOCNICTWO" in prompt and "Osobny odczyt" not in prompt
        seen.append(prompt)
        return "power_of_attorney"

    def extract_model(definition, text, model=None, *, alternate_pages=None):
        assert alternate_pages == ["PEŁNOMOCNICTWO", "Osobny odczyt"]
        assert text == "\n".join(primary)
        return {"mocodawca": [], "pelnomocnicy": []}

    def rules(pages, seen):
        assert pages == primary and seen == [1, 3]
        return {"mocodawca": [], "pelnomocnicy": []}

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(rapid_worker, "recognize", recognize)
    monkeypatch.setattr(llm, "classify_llm", route)
    monkeypatch.setattr(llm, "extract_llm", extract_model)
    monkeypatch.setattr(pipeline.ocr_extract, "extract_power_of_attorney", rules)
    assert pipeline.process_pdf(Path("scan.pdf"))[0] == "power_of_attorney"
    assert len(seen) == 1 and calls == [1, 3]


@pytest.mark.parametrize("variant", ["keyless", "off", "rules", "custom", "native", "rapidocr"])
def test_dual_reading_respects_class_profile_and_ocr_provenance(keyed, monkeypatch, tmp_path, variant):
    if variant == "keyless":
        monkeypatch.delenv("KIO_LLM_API_KEY")
    if variant == "off":
        monkeypatch.setenv("KIO_LLM_DUAL_OCR", "false")
    if variant == "rules":
        monkeypatch.setenv("KIO_LLM_MODE", "R")
        monkeypatch.setenv("KIO_LLM_ROUTING", "rules")
    if variant == "rapidocr":
        monkeypatch.setenv("KIO_OCR_ENGINE", "rapidocr")
    custom = tmp_path / "classes"
    if variant == "custom":
        custom.mkdir()
        (custom / "power.toml").write_bytes((DEFAULT_DIR / "power_of_attorney.toml").read_bytes())
    classes = load_classes(custom if variant == "custom" else None)

    def read(path, *, ocr_pages, **kw):
        if variant != "native":
            ocr_pages.append(1)
        return ["PEŁNOMOCNICTWO"]

    def extract_model(definition, text, model=None, *, alternate_pages=None):
        assert alternate_pages is None
        return {"mocodawca": [], "pelnomocnicy": []}

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(rapid_worker, "recognize", lambda *a: pytest.fail("unexpected second reading"))
    monkeypatch.setattr(llm, "extract_llm", extract_model)
    assert pipeline.process_pdf(Path("invented.pdf"), classes=classes)[0] == "power_of_attorney"


def test_model_extraction_cannot_quote_across_alternate_pages():
    from pydantic_ai.models.test import TestModel as OfflineModel

    from kio2json.class_config import DocumentClass

    definition = DocumentClass(
        id="receipt",
        routing={"required": ["Receipt"]},
        engines=["llm"],
        fields={name: {"type": "string", "instruction": "Copy the reference."} for name in ("printed", "spliced")},
    )
    output = {
        "printed": {"value": "BETA-123", "quote": "BETA-123"},
        "spliced": {"value": "ALPHA BETA-123", "quote": "ALPHA\nBETA-123"},
    }
    prediction = llm.extract_llm(
        definition, "Receipt", model=OfflineModel(custom_output_args=output), alternate_pages=["ALPHA", "BETA-123"]
    )
    assert prediction == {"printed": "BETA-123", "spliced": None}


@pytest.mark.parametrize("policy", ["fallback", "model"])
def test_model_routing_can_use_dual_ocr_with_rule_only_extraction(keyed, monkeypatch, policy):
    monkeypatch.setenv("KIO_LLM_MODE", "R")
    monkeypatch.setenv("KIO_LLM_ROUTING", policy)
    primary = ["Unknown layout", "Other scanned page"]

    def read(path, *, ocr_pages, **kw):
        ocr_pages.extend([1, 2])
        return primary

    def recognize(path, page, word_boxes, timeout):
        assert page == 1
        return "PEŁNOMOCNICTWO", []

    def route(prompt):
        assert "Unknown layout" in prompt and "PEŁNOMOCNICTWO" in prompt
        return "power_of_attorney"

    def rules(pages, scanned_pages):
        assert pages == primary and scanned_pages == [1, 2]
        return {"mocodawca": [], "pelnomocnicy": []}

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(rapid_worker, "recognize", recognize)
    monkeypatch.setattr(llm, "classify_llm", route)
    monkeypatch.setattr(llm, "extract_llm", lambda *a, **kw: pytest.fail("unexpected model extraction"))
    monkeypatch.setattr(pipeline.ocr_extract, "extract_power_of_attorney", rules)
    assert pipeline.process_pdf(Path("invented.pdf")) == ("power_of_attorney", {"mocodawca": [], "pelnomocnicy": []})
