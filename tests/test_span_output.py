import json

import httpx2
import pytest

from kio2json.class_config import OutputField, load_classes
from kio2json.llm import extract_llm, grounded


def test_native_transfer_spans_round_trip(monkeypatch):
    for option, value in {
        "BASE_URL": "https://example.invalid/v1",
        "MODEL": "test-model",
        "API_KEY": "fixture",
        "OUTPUT": "spans",
    }.items():
        monkeypatch.setenv("KIO_LLM_" + option, value)
    source = (
        "Data operacji: 05.04.2024\nKwota: 125,50 zł\nTytuł: Opłata próbna\nNumer: REF-123\n"
        "Z rachunku: PL74 1234 5123 4512 3451 2345 1234\nNa rachunek: GB82 WEST 1234 5698 7654 32"
    )
    transfer = {
        "data_operacji": "05.04.2024",
        "kwota": "125,50 zł",
        "na_rachunek": "GB82 WEST 1234 5698 7654 32",
        "numer_transakcji": "REF-12",
        "tytul": "wymyślony opis",
        "z_rachunku": "PL74 1234 5123 4512 3451 2345 1234",
    }
    requests = []

    async def respond(transport, request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["response_format"]["type"] == "json_schema"
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
        assert source in body["messages"][-1]["content"]
        return httpx2.Response(
            200,
            json={
                "id": "offline",
                "model": "test-model",
                "created": 1,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps({"przelew_bankowy": transfer})},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", respond)
    definition = next(c for c in load_classes() if c.id == "bank_transfer")
    values = extract_llm(definition, source)["przelew_bankowy"]
    assert len(requests) == 1
    assert values == {
        **transfer,
        "kwota": 125.5,
        "data_operacji": "2024-04-05",
        "na_rachunek": "GB82WEST12345698765432",
        "z_rachunku": "PL74123451234512345123451234",
        "numer_transakcji": None,
        "tytul": None,
    }


@pytest.mark.parametrize(
    ("quote", "expected"),
    [("działa przez pełnomocnika", 1), ("pełnomocnika", None), ("działa samodzielnie", None)],
)
def test_spans_derive_representation_from_source(quote, expected):
    field = OutputField(type="integer", instruction="Representation", grounding="przez-pelnomocnika")
    text = "Odwołujący działa przez pełnomocnika."
    assert grounded(field, quote, text, text) == expected
