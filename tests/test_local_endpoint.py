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


def test_reasoning_overrides_on_openai_compatible_wire(monkeypatch, tmp_path):
    import json
    import os

    import httpx2

    from kio2json import llm

    class Extracted(llm.RouteDecision):
        pass

    requests = []
    deadlines = []
    run = llm.Agent.run_sync

    def run_with_deadline(agent, *args, **kwargs):
        deadlines.append(kwargs["timeout"])
        return run(agent, *args, **kwargs)

    async def respond(transport, request):
        body = json.loads(request.content)
        assert body["model"] == "invented-model"
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0] == {"role": "system", "content": "Return JSON"}
        assert body["messages"][-1] == {"role": "user", "content": "synthetic"}
        assert '"label"' in body["messages"][1]["content"]
        options = {"max_tokens", "max_completion_tokens", "reasoning_effort", "thinking", "temperature"}
        requests.append({k: v for k, v in body.items() if k in options})
        return httpx2.Response(
            200,
            json={
                "id": "offline",
                "model": body["model"],
                "created": 1,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"label":"unrelated"}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", respond)
    monkeypatch.setattr(llm.Agent, "run_sync", run_with_deadline)
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("KIO_LLM_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("KIO_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("KIO_LLM_MODEL", "invented-model")
    monkeypatch.setenv("KIO_LLM_API_KEY", "invented")
    with monkeypatch.context() as legacy:
        legacy.setenv("KIO_LLM_TOKEN_PARAMETER", "max_tokens")
        legacy.setenv("KIO_LLM_INLINE_SYSTEM_PROMPTS", "false")
        with monkeypatch.context() as reasoning:
            for key, value in {
                "ROUTE_REASONING": "low",
                "EXTRACT_REASONING": "high",
                "THINKING_TYPE": "enabled",
                "ROUTE_MAX_TOKENS": "24576",
                "EXTRACT_MAX_TOKENS": "32768",
                "TIMEOUT_SECONDS": "480",
            }.items():
                reasoning.setenv(f"KIO_LLM_{key}", value)
            llm.structured(llm.RouteDecision, "Return JSON", "synthetic", max_tokens=32)
            llm.structured(Extracted, "Return JSON", "synthetic", max_tokens=1800)
        legacy.setenv("KIO_LLM_EXTRACT_REASONING", "none")
        llm.structured(Extracted, "Return JSON", "synthetic", max_tokens=1800)
    llm.structured(Extracted, "Return JSON", "synthetic", max_tokens=1800)
    for key, value in {
        "ROUTE_REASONING": "low",
        "EXTRACT_REASONING": "high",
        "ROUTE_MAX_TOKENS": "120",
        "EXTRACT_MAX_TOKENS": "1400",
        "TIMEOUT_SECONDS": "89",
        "EXTRACT_TIMEOUT_SECONDS": "137",
    }.items():
        monkeypatch.setenv(f"KIO_LLM_{key}", value)
    llm.structured(llm.RouteDecision, "Return JSON", "synthetic", max_tokens=32)
    llm.structured(Extracted, "Return JSON", "synthetic", max_tokens=1800)
    assert requests == [
        {"max_tokens": 24576, "reasoning_effort": "low", "thinking": {"type": "enabled"}},
        {"max_tokens": 32768, "reasoning_effort": "high", "thinking": {"type": "enabled"}},
        {"max_tokens": 1800, "reasoning_effort": "none", "temperature": 0},
        {"max_completion_tokens": 1800, "temperature": 0},
        {"max_completion_tokens": 120, "reasoning_effort": "low"},
        {"max_completion_tokens": 1400, "reasoning_effort": "high"},
    ]
    assert deadlines == [480, 480, 180, 180, 89, 137]
