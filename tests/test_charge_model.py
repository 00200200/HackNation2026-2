"""Invented excerpts for the optional rules-first appeal request."""

import json

import httpx2
import pytest

from kio2json import engines
from kio2json.class_config import load_classes


@pytest.fixture
def appeal(monkeypatch):
    for name, value in {
        "BASE_URL": "https://example.invalid/v1",
        "MODEL": "fixture",
        "API_KEY": "fixture",
        "MODE": "RL",
        "OUTPUT": "spans",
        "CHARGE_FOCUS": "only",
        "EXTRACT_MAX_TOKENS": "7000",
    }.items():
        monkeypatch.setenv("KIO_LLM_" + name, value)
    return next(c for c in load_classes() if c.id == "appeal")


INTRO = "Wnoszę odwołanie wobec odrzucenia oferty dokonanego dnia 09.04.2025."
FIRST = "Zarzut pierwszy: odrzucenie oferty wbrew warunkom procedury."
LATER = "Zarzut drugi: wybór oferty dnia 10.04.2025."
SOURCE = "Toruń, 14.04.2025\n" + INTRO + "\n" + FIRST + "\n" + LATER


def run_focus(appeal, monkeypatch, reply, *, source=SOURCE, existing=None, model_text=None):
    calls = []

    async def send(transport, request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx2.Response(
            200,
            json={
                "id": "offline",
                "model": "fixture",
                "created": 1,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(reply)},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", send)
    rules = appeal.extractor("")
    rules["OdwolanieKIO"].update(existing or {})
    out = engines.extract(appeal, source, model_text=model_text, ocr_python=lambda: rules)
    return out["OdwolanieKIO"], calls


def test_one_bounded_call_with_first_charge_and_dated_intro(appeal, monkeypatch):
    header, calls = run_focus(
        appeal,
        monkeypatch,
        {
            "reason_id": 1,
            "act_quote": "odrzucenie oferty",
            "dated_act_quote": "odrzucenia oferty dokonanego dnia 09.04.2025",
        },
    )
    assert len(calls) == 1
    prompt = calls[0]["messages"][-1]["content"]
    assert "odrzucenie oferty" in prompt and "09.04.2025" in prompt
    assert "14.04.2025" not in prompt and "10.04.2025" not in prompt
    assert len(prompt.encode()) <= 4096
    assert (calls[0].get("max_tokens") or calls[0].get("max_completion_tokens")) <= 320
    assert header == {
        "data": None,
        "czynnosc_dzien": "2025-04-09",
        "czynnosc_powod_id": 1,
        "czynnosc_opis": "Decyzja o odrzuceniu oferty",
        "miejscowosc": None,
    }


@pytest.mark.parametrize(
    "reply",
    [
        {"reason_id": 2, "act_quote": "wybór oferty", "dated_act_quote": LATER},
        {"reason_id": 7, "act_quote": "odrzucenie oferty", "dated_act_quote": INTRO},
        {"reason_id": 1, "act_quote": "odrzucenie wymyślonej oferty", "dated_act_quote": INTRO},
        {"invalid": "malformed endpoint output"},
    ],
)
def test_invalid_evidence_or_schema_preserves_rules_without_retry(appeal, monkeypatch, reply):
    header, calls = run_focus(appeal, monkeypatch, reply)
    assert len(calls) == 1
    assert header["czynnosc_powod_id"] is header["czynnosc_opis"] is header["czynnosc_dzien"] is None


def test_preserves_rule_reason_and_rejects_unrelated_date(appeal, monkeypatch):
    reply = {"reason_id": 1, "act_quote": "odrzucenie oferty", "dated_act_quote": "14.04.2025"}
    header, calls = run_focus(
        appeal, monkeypatch, reply, existing={"czynnosc_powod_id": 1, "czynnosc_opis": "Decyzja o odrzuceniu oferty"}
    )
    assert len(calls) == 1
    assert header["czynnosc_dzien"] is None and header["czynnosc_powod_id"] == 1
    header, calls = run_focus(
        appeal,
        monkeypatch,
        reply,
        existing={
            "czynnosc_powod_id": 1,
            "czynnosc_opis": "Decyzja o odrzuceniu oferty",
            "czynnosc_dzien": "2025-05-01",
        },
    )
    assert not calls and header["czynnosc_dzien"] == "2025-05-01"


def test_quote_from_later_sentence_cannot_displace_first_substantive_act(appeal, monkeypatch):
    header, _ = run_focus(
        appeal,
        monkeypatch,
        {"reason_id": 3, "act_quote": "wykluczenie wykonawcy", "dated_act_quote": None},
        source="Zarzut pierwszy: odrzucenie oferty. Osobnym zagadnieniem jest wykluczenie wykonawcy.",
    )
    assert header["czynnosc_powod_id"] is None


def test_indirect_intro_mention_does_not_date_first_act(appeal, monkeypatch):
    opening = "Zamawiający w dniu 05.02.2025 omawiał zagadnienie odrzucenia oferty"
    header, _ = run_focus(
        appeal,
        monkeypatch,
        {"reason_id": 1, "act_quote": "odrzucenie oferty", "dated_act_quote": opening},
        source=opening + ".\n" + FIRST,
    )
    assert header["czynnosc_powod_id"] == 1 and header["czynnosc_dzien"] is None


def test_optional_request_handles_service_overload_without_transport_retry(appeal, monkeypatch):
    calls = []

    async def overloaded(transport, request):
        calls.append(request)
        return httpx2.Response(503, json={"error": {"message": "synthetic overload"}})

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", overloaded)
    rules = appeal.extractor("")
    assert engines.extract(appeal, SOURCE, ocr_python=lambda: rules) == rules
    assert len(calls) == 1


def test_full_sentence_quote_including_its_punctuation(appeal, monkeypatch):
    header, calls = run_focus(
        appeal,
        monkeypatch,
        {
            "reason_id": 1,
            "act_quote": "odrzucenie oferty wbrew warunkom procedury.",
            "dated_act_quote": None,
        },
    )
    assert len(calls) == 1 and header["czynnosc_powod_id"] == 1


def test_known_rule_id_establishes_missing_description_without_a_request(appeal, monkeypatch):
    header, calls = run_focus(
        appeal, monkeypatch, {}, existing={"czynnosc_powod_id": 1, "czynnosc_dzien": "2025-04-09"}
    )
    assert not calls and header["czynnosc_opis"] == "Decyzja o odrzuceniu oferty"


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("false", ["general"]),
        ("true", ["focus", "general"]),
        ("only", ["focus"]),
    ],
)
def test_opt_in_selects_general_or_specialist_calls(appeal, monkeypatch, choice, expected):
    from kio2json import llm
    from kio2json.charge_model import ChargeEvidence

    monkeypatch.setenv("KIO_LLM_CHARGE_FOCUS", choice)
    calls = []
    rules = appeal.extractor("")

    def general(*args, **kwargs):
        calls.append("general")
        return rules

    def specialist(*args, **kwargs):
        calls.append("focus")
        return ChargeEvidence(reason_id=None, act_quote=None, dated_act_quote=None)

    monkeypatch.setattr(llm, "extract_llm", general)
    monkeypatch.setattr(llm, "structured", specialist)
    assert engines.extract(appeal, SOURCE, ocr_python=lambda: rules) == rules
    assert calls == expected


@pytest.mark.parametrize(
    ("source", "dated"),
    [
        (
            "Zarzut pierwszy: odrzucenie oferty Alfa. W innej sprawie odrzucenie oferty Beta w dniu 03.02.2025.",
            "odrzucenie oferty Beta w dniu 03.02.2025",
        ),
        (
            "Zarzut pierwszy: odrzucenie oferty Alfa oraz odrzucenie oferty Beta w dniu 03.02.2025.",
            "odrzucenie oferty Beta w dniu 03.02.2025",
        ),
        (
            "Wnoszę odwołanie wobec odrzucenia oferty Beta w dniu 03.02.2025.\nZarzut pierwszy: odrzucenie oferty Alfa.",
            "odrzucenia oferty Beta w dniu 03.02.2025",
        ),
        (
            "Wnoszę odwołanie wobec odrzucenia oferty w dniu 03.02.2025.\nZarzut pierwszy: odrzucenie oferty Alfa.",
            "odrzucenia oferty w dniu 03.02.2025",
        ),
        (
            "Zamawiający w dniu 03.02.2025 odrzucił ofertę Beta.\nZarzut pierwszy: odrzucenie oferty Alfa.",
            "Zamawiający w dniu 03.02.2025 odrzucił ofertę Beta",
        ),
    ],
)
def test_other_rejection_cannot_date_first_offer(appeal, monkeypatch, source, dated):
    header, _ = run_focus(
        appeal,
        monkeypatch,
        {
            "reason_id": 1,
            "act_quote": "odrzucenie oferty Alfa",
            "dated_act_quote": dated,
        },
        source=source,
    )
    assert header["czynnosc_powod_id"] == 1 and header["czynnosc_dzien"] is None


def test_specialist_quotes_only_the_primary_model_reading(appeal, monkeypatch):
    header, calls = run_focus(
        appeal,
        monkeypatch,
        {
            "reason_id": 1,
            "act_quote": "odrzucenie oferty Alfa",
            "dated_act_quote": None,
        },
        source="Zarzut pierwszy: odrzucenie oferty Alfa.",
        model_text="Zarzut pierwszy: wybór oferty Gamma.",
    )
    assert len(calls) == 1
    prompt = calls[0]["messages"][-1]["content"]
    assert "Gamma" in prompt and "Alfa" not in prompt
    assert header["czynnosc_powod_id"] is None


def test_filing_which_names_same_offer_can_supply_its_date(appeal, monkeypatch):
    header, _ = run_focus(
        appeal,
        monkeypatch,
        {
            "reason_id": 1,
            "act_quote": "odrzucenie oferty Alfa",
            "dated_act_quote": "odrzucenia oferty Alfa w dniu 03.02.2025",
        },
        source="Wnoszę odwołanie wobec odrzucenia oferty Alfa w dniu 03.02.2025.\nZarzut pierwszy: odrzucenie oferty Alfa.",
    )
    assert header["czynnosc_powod_id"] == 1 and header["czynnosc_dzien"] == "2025-02-03"
