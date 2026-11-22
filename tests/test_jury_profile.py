from pathlib import Path

import pytest

from kio2json import jury_budget, pipeline
from kio2json.endpoint_error import EndpointError
from kio2json.model_profile import ProfileSettings


@pytest.fixture
def jury(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in ("MODE", "ROUTING", "GAP_SCOPE", "DUAL_OCR"):
        monkeypatch.delenv("KIO_LLM_" + name, raising=False)
    monkeypatch.setenv("KIO_LLM_BASE_URL", "https://api.eu.mistral.ai/v1")
    monkeypatch.setenv("KIO_LLM_MODEL", "ministral-3b-2512")
    monkeypatch.setenv("KIO_LLM_API_KEY", "offline")
    return ProfileSettings().profile()


def test_three_regional_settings_select_rules_then_model(jury, monkeypatch):
    assert jury.jury and jury.keyed and jury.mode == "RL" and jury.routing == "rules" and not jury.dual_ocr
    monkeypatch.setenv("KIO_LLM_MODE", "LR")
    assert ProfileSettings().profile().mode == "LR"
    assert not ProfileSettings().profile().jury
    monkeypatch.setenv("KIO_LLM_API_KEY", "")
    assert not ProfileSettings().profile().keyed


def test_model_failure_preserves_rule_bytes_after_partial_update(jury, monkeypatch):
    from kio2json import jury_fields
    from kio2json.batch import read_document
    from kio2json.class_config import load_classes

    calls = []

    def fail(class_id, record, pages, **kwargs):
        calls.append(class_id)
        record["przelew_bankowy"]["kwota"] = 0
        raise ValueError("sensitive body excluded from all diagnostics")

    monkeypatch.setattr(jury_fields, "enrich", fail)
    pages = ["Potwierdzenie przelewu\n" + "3" * 26 + "\n" + "4" * 26 + "\nKwota: 12,00\nTytuł: Wpis do KIO"]
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: pages)
    result = read_document(Path("file.pdf"), load_classes(), explain=True)
    monkeypatch.setenv("KIO_LLM_API_KEY", "")
    base = read_document(Path("file.pdf"), load_classes())
    assert calls == ["bank_transfer"] and result.text == base.text and result.label == "bank_transfer"
    assert result.used_recovery and result.error is None and "sensitive" not in str(result.trace)


def test_rejected_document_never_calls_provider(jury, monkeypatch):
    from kio2json import llm

    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: ["Zaproszenie na koncert"])
    monkeypatch.setattr(llm, "structured", lambda *a, **kw: pytest.fail("unexpected API call"))
    assert pipeline.process_pdf(Path("unknown.pdf")) == (None, {})


def test_budget_and_quota_are_shared_across_documents(monkeypatch):
    clock = [100.0]
    budget = jury_budget.JuryBudget(150)
    monkeypatch.setattr(jury_budget, "_batch", budget)
    monkeypatch.setattr(jury_budget, "monotonic", lambda: clock[0])
    assert budget.seconds.value == 300
    with jury_budget.jury_document(), pytest.raises(EndpointError), jury_budget.request_slot() as seconds:
        assert seconds == 10
        clock[0] += 2
        cause = RuntimeError("secret response body")
        cause.status_code = 429
        raise EndpointError(cause)
    assert budget.seconds.value == 298
    with jury_budget.jury_document(), pytest.raises(EndpointError), jury_budget.request_slot():
        pytest.fail("A second document called a rate-limited API")
    clock[0] += 61
    budget.seconds.value = 0.75
    with jury_budget.jury_document(), jury_budget.request_slot() as seconds:
        assert seconds == 0.75
        clock[0] += seconds
    with jury_budget.jury_document(), pytest.raises(EndpointError), jury_budget.request_slot():
        pytest.fail("Exhausted batch budget")


def test_gui_uploads_share_quota_cooldown(jury, tmp_path, monkeypatch):
    from kio2json import gui_files
    from kio2json.batch import Result
    from kio2json.class_config import load_classes

    attempted = []

    def read(*args, **kwargs):
        with jury_budget.jury_document(), pytest.raises(EndpointError), jury_budget.request_slot():
            attempted.append(True)
            failure = RuntimeError()
            failure.status_code = 429
            raise EndpointError(failure)
        return Result(None)

    source = tmp_path / "upload.pdf"
    source.touch()
    monkeypatch.setattr(gui_files, "read_document", read)
    docs = gui_files.analyze([(Path("case/a.pdf"), source), (Path("case/b.pdf"), source)], tmp_path, load_classes())
    assert len(docs) == 2 and attempted == [True]


@pytest.mark.parametrize("failure", ["quota", "timeout"])
def test_failed_regional_call_keeps_both_pdfs_and_stops_further_requests(jury, monkeypatch, failure):
    import httpx2

    from kio2json.batch import read_document
    from kio2json.class_config import load_classes

    pages = [
        (
            "Odwołujący: Most S.A.\nZamawiający: Instytut Portu\nODWOŁANIE\n"
            "Zarzut pierwszy: Pozostawiono w grze ofertę mimo obowiązku jej eliminacji."
        )
    ]
    monkeypatch.setattr(pipeline, "read_pages", lambda *a, **kw: pages)
    attempts = []

    async def respond(_transport, request):
        attempts.append(True)
        if failure == "quota":
            return httpx2.Response(429, json={"error": "private provider body"})
        raise httpx2.ReadTimeout("private provider body", request=request)

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", respond)
    keyed = load_classes()
    rules = [c.rules_only for c in keyed]
    with jury_budget.jury_document(jury_budget.JuryBudget(2)):
        for name in ["a.pdf", "b.pdf"]:
            result = read_document(Path(name), keyed, explain=True)
            assert result.text == read_document(Path(name), rules).text
            assert result.label == "appeal" and result.used_recovery and result.error is None
            assert "private provider body" not in str(result.trace)
    assert len(attempts) == 1
