from kio2json.llm import bounded_text


def test_document_budget_counts_utf8_bytes_and_keeps_complete_characters():
    text = "Długie pismo " * 2000
    result = bounded_text(text)
    assert text.startswith(result)
    assert 16382 <= len(result.encode()) <= 16384


def test_resolve_quote_recovers_one_original_wrapped_span():
    from kio2json.llm import source_quote

    assert source_quote("Tytuł: Opłata wstępna", "Tytuł: Opłata\n wstępna.") == "Tytuł: Opłata\n wstępna"
    assert source_quote("Konto: 123 456", "Konto: 123\n456") is None
    assert source_quote("A B", "A\n\nB") is None
    assert source_quote("A B", "A\nB / A\tB") is None
    assert source_quote("Łódź", "Lodz") is None


def test_hidden_repeat_cannot_establish_role_or_complete_clipped_token():
    from kio2json.class_config import OutputField
    from kio2json.llm import grounded

    role = OutputField(type="integer", instruction="Whether appellant has counsel", grounding="przez-pelnomocnika")
    shown = "Zamawiający działa przez pełnomocnika."
    full = shown + "\nOdwołujący działa przez pełnomocnika."
    assert grounded(role, {"value": 1, "quote": "działa przez pełnomocnika"}, full, shown) is None

    field = OutputField(type="string", instruction="Complete reference")
    assert grounded(field, {"value": "ABC", "quote": "ABC"}, "Reference ABCD\nABC", "Reference ABC") is None


def test_reasoning_budget_depends_on_explicit_provider_model_and_task(monkeypatch):
    from types import SimpleNamespace
    from pydantic import BaseModel
    from kio2json import llm

    class Record(BaseModel):
        name: str

    captured = []

    class CaptureAgent:
        def __init__(self, model, **options):
            self.settings = options["model_settings"]

        def run_sync(self, text, timeout):
            captured.append((self.settings, timeout))
            return SimpleNamespace(output=None)

    monkeypatch.setattr(llm, "Agent", CaptureAgent)
    monkeypatch.setenv("KIO_LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("KIO_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("KIO_LLM_API_KEY", "invented")
    monkeypatch.delenv("KIO_LLM_TIMEOUT_SECONDS", raising=False)
    llm.structured(llm.RouteDecision, "test", "test", max_tokens=32)
    llm.structured(Record, "test", "test", max_tokens=1800)
    monkeypatch.setenv("KIO_LLM_BASE_URL", "http://127.0.0.1:8089/v1")
    llm.structured(Record, "test", "test", max_tokens=1800)
    assert [(s.get("thinking"), s["max_tokens"], t) for s, t in captured] == [
        ("low", 24576, 480),
        ("high", 32768, 480),
        (None, 1800, 180),
    ]
