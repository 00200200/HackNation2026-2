"""Engine contract tests use invented document text and an offline Pydantic AI model."""

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel as OfflineModel

from kio2json.class_config import DocumentClass, load_classes
from kio2json.endpoint_error import EndpointError


def scalar(instruction, **options):
    return {"type": "string", "instruction": instruction, **options}


def form(fields, engines, **options):
    return DocumentClass.model_validate(
        {
            "id": "receipt",
            "routing": {"required": ["Receipt"]},
            "fields": fields,
            "engines": engines,
            **options,
        }
    )


def test_labelled_types_and_repeated_rows():
    from kio2json.engines import extract

    amount = scalar("Line amount", type="number", normalizer="money", pattern=r"Amount: (.+)")
    account = scalar("Recipient", normalizer="account_number", pattern=r"Account: (.+)")
    tax = scalar("Tax ID", normalizer="nip", pattern=r"ID: (.+)")
    rows = {
        "type": "list",
        "instruction": "Line items",
        "pattern": r"Line: (.+)",
        "items": {
            "type": "object",
            "instruction": "Item",
            "fields": {
                "count": scalar("Quantity", type="integer", pattern=r"Qty (\d+)"),
                "name": scalar("Item name", pattern=r"Name (\w+)"),
            },
        },
    }
    cfg = form({"amount": amount, "account": account, "tax": tax, "rows": rows}, ["labelled_fields"])
    text = (
        "Amount: 7 421,35\nAccount: PL"
        + "4" * 26
        + "\nID: 888-111-22-39\nLine: Qty 2 Name Pins\nLine: Qty 3 Name Clips"
    )
    values = extract(cfg, text)
    assert values == {
        "amount": 7421.35,
        "account": "4" * 26,
        "tax": "8881112239",
        "rows": [{"count": 2, "name": "Pins"}, {"count": 3, "name": "Clips"}],
    }
    assert extract(cfg, "Amount: 7x421,35\nAccount: unreadable\nID: 123")["amount"] is None


def test_llm_checks_each_nested_value_before_returning_public_json(monkeypatch):
    from kio2json.engines import extract

    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    cfg = next(c for c in load_classes() if c.id == "power_of_attorney").model_copy(update={"engines": ["llm"]})
    payload = {
        "mocodawca": [],
        "pelnomocnicy": [
            {
                "imie_nazwisko": {"value": "Eva Finch", "quote": "Eva Finch signed"},
                "pesel": {"value": "98765432102", "quote": "not on the page"},
            },
            {"imie_nazwisko": None, "pesel": None},
        ],
    }
    result = extract(cfg, "Eva Finch signed the form.", model=OfflineModel(custom_output_args=payload))
    assert result == {
        "mocodawca": [],
        "pelnomocnicy": [{"imie_nazwisko": "Eva Finch", "pesel": None}, {"imie_nazwisko": None, "pesel": None}],
    }


def test_python_then_llm_fills_only_null_fields(monkeypatch):
    from kio2json.engines import extract

    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    cfg = next(c for c in load_classes() if c.id == "bank_transfer").model_copy(update={"engines": ["python", "llm"]})
    payload = dict.fromkeys(cfg.fields["przelew_bankowy"].fields)
    payload.update(kwota={"value": 13.00, "quote": "Fee 13.00"}, numer_transakcji={"value": "HX", "quote": "ref HX"})
    result = extract(
        cfg,
        "Kwota: 12,00\nFee 13.00\nAlternate ref HX",
        model=OfflineModel(custom_output_args={"przelew_bankowy": payload}),
    )
    assert result["przelew_bankowy"]["kwota"] == 12.0
    assert result["przelew_bankowy"]["numer_transakcji"] == "HX"
    assert result["przelew_bankowy"]["tytul"] is None


def test_complete_primary_skips_unconfigured_llm():
    from kio2json.engines import extract

    cfg = form({"count": scalar("Count", type="integer", pattern=r"Count: (\d+)")}, ["labelled_fields", "llm"])
    assert extract(cfg, "Count: 0") == {"count": 0}


def test_missing_model_configuration_is_visible(monkeypatch, tmp_path):
    from kio2json.engines import extract

    monkeypatch.chdir(tmp_path)
    for key in ("KIO_LLM_BASE_URL", "KIO_LLM_MODEL", "KIO_LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    cfg = form({"ref": scalar("Reference")}, ["llm"])
    with pytest.raises(EndpointError, match="^ValidationError$"):
        extract(cfg, "Receipt")


def test_invalid_primary_date_can_be_filled_by_grounded_fallback():
    from kio2json.engines import extract

    cfg = form(
        {"date": scalar("Receipt date", normalizer="iso_date", pattern=r"Date: (.+)")}, ["labelled_fields", "llm"]
    )
    text = "Date: smudged\nFiled on 7 April 2031."
    model = OfflineModel(custom_output_args={"date": {"value": "2031-04-07", "quote": "Filed on 7 April 2031"}})
    assert extract(cfg, text, model=model) == {"date": "2031-04-07"}


def test_missing_evidence_nulls_even_a_mandatory_value():
    from kio2json.engines import extract

    cfg = form({"ref": scalar("Reference", nullable=False)}, ["llm"])
    model = OfflineModel(custom_output_args={"ref": {"value": "HX", "quote": "unseen"}})
    assert extract(cfg, "Receipt", model=model) == {"ref": None}


def test_nested_fallback_uses_identity_instead_of_position():
    from kio2json.engines import extract

    cfg = next(c for c in load_classes() if c.id == "power_of_attorney").model_copy(
        update={"engines": ["python", "llm"]}
    )
    text = "Udzielam pełnomocnictwa adw. Iga Wymyślna oraz adw. Ewa Wymyślna. Identifier 88888888881 belongs to Ewa."
    model = OfflineModel(
        custom_output_args={
            "mocodawca": [],
            "pelnomocnicy": [
                {
                    "imie_nazwisko": {"value": "Ewa Wymyślna", "quote": "Ewa Wymyślna"},
                    "pesel": {"value": "88888888881", "quote": "Identifier 88888888881 belongs to Ewa."},
                },
                {"imie_nazwisko": {"value": "Iga Wymyślna", "quote": "Iga Wymyślna"}, "pesel": None},
            ],
        }
    )
    assert extract(cfg, text, model=model)["pelnomocnicy"] == [
        {"imie_nazwisko": "Iga Wymyślna", "pesel": None},
        {"imie_nazwisko": "Ewa Wymyślna", "pesel": "88888888881"},
    ]


def test_missing_quote_exhausts_one_schema_retry():
    from kio2json.engines import extract

    attempts = []

    def omit_quote(messages, info):
        attempts.append(len(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"ref": {"value": "H"}})])

    cfg = form({"ref": scalar("Reference")}, ["llm"])
    with pytest.raises(EndpointError, match="^UnexpectedModelBehavior$"):
        extract(cfg, "H", model=FunctionModel(omit_quote))
    assert len(attempts) == 2


def test_endpoint_reads_dotenv_and_prioritizes_environment(tmp_path, monkeypatch):
    from kio2json.llm import Endpoint

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KIO_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("KIO_LLM_MODEL", "process-model")
    monkeypatch.setenv("KIO_LLM_API_KEY", "offline-test-value")
    (tmp_path / ".env").write_text("KIO_LLM_MODEL=file-model\nKIO_LLM_BASE_URL=http://localhost:8100/v1\n")
    model = Endpoint().chat_model()
    assert model.model_name == "process-model"
    assert str(model.provider.base_url).rstrip("/") == "http://localhost:8100/v1"


@pytest.mark.parametrize(
    ("field", "value", "quote", "expected"),
    [
        (scalar("Customer reference"), "MIST-901", "Receipt", None),
        (scalar("Customer reference"), "LARK-83", "Supplier ref FINCH-61", None),
        (scalar("Customer reference"), "LARK-83", "Customer ref lark-83", "LARK-83"),
        (scalar("Customer name"), "North Quill", "Payee NORTH\n  QUILL LTD", "North Quill"),
        (scalar("Customer name"), "  ", "Receipt", None),
        (scalar("Customer reference"), "ROOK-91", "Reference ROOK-912", None),
        (scalar("Count", type="integer"), 13, "Count 113", None),
        (scalar("Count", type="integer"), 34, "Count 12,34", None),
        (scalar("Count", type="integer"), 321, "Count 1 321", None),
        (scalar("Count", type="integer"), 27, "Count 27,4X", None),
        (scalar("Refund", type="number", normalizer="money"), 52.37, "Refund 3 52,37", None),
        (scalar("Ratio", type="number"), 2.0, "Ratio 2", 2.0),
        (scalar("Active", type="boolean"), False, "Active false", False),
        (scalar("Filing date", normalizer="iso_date"), "2034-10-22", "Filed 21 października 2034", None),
        (
            scalar("Filing date", normalizer="iso_date"),
            "2034-10-22",
            "Filed 21.10.2034 or 22 października 2034",
            "2034-10-22",
        ),
        (scalar("Refund", type="number", normalizer="money"), 6543.71, "Refund -6 543,71 PLN", None),
        (scalar("Refund", type="number", normalizer="money"), 6543.71, "Refund −6 543,71 PLN", None),
        (scalar("Refund", type="number", normalizer="money"), -6543.71, "Refund −6 543,71 PLN", -6543.71),
        (scalar("Refund", type="number", normalizer="money"), -6543.71, "Refund -6 543,71 PLN", -6543.71),
        (
            scalar("Account", normalizer="account_number"),
            "73" + "1864" * 6,
            "New account PL73" + " 1864" * 6,
            "73" + "1864" * 6,
        ),
        (scalar("Account", normalizer="account_number"), "73" + "1864" * 6, "Old account PL74" + " 1864" * 6, None),
        (scalar("Tax ID", normalizer="nip"), "7842913068", "ID PL784-291-30-68", "7842913068"),
        (scalar("Tax ID", normalizer="nip"), "7842913068", "ID 784-291-30-68-3", None),
        (scalar("Register", normalizer="krs"), "0000087643", "Register 00000876430", None),
        (scalar("Register", normalizer="regon"), "876450123", "Register 87645012300007", None),
        (scalar("Person ID", normalizer="pesel"), "87654321019", "Person ID 87654321018", None),
    ],
)
def test_model_values_need_support_inside_their_own_quote(field, value, quote, expected):
    from kio2json.engines import extract

    cfg = form({"value": field}, ["llm"])
    model = OfflineModel(custom_output_args={"value": {"value": value, "quote": quote}})
    text = f"Receipt\nCustomer ref LARK-83\n{quote}"
    assert extract(cfg, text, model=model) == {"value": expected}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("-6 543,71", -6543.71), ("+6.543,71", 6543.71), ("-6543,71", -6543.71)],
)
def test_labelled_money_preserves_sign_across_grouping(raw, expected):
    from kio2json.engines import extract

    cfg = form(
        {"refund": scalar("Refund", type="number", normalizer="money", pattern=r"Refund: (.+)")}, ["labelled_fields"]
    )
    assert extract(cfg, f"Refund: {raw}") == {"refund": expected}


@pytest.mark.parametrize("raw", ["784-291-30-68-3", "7842913068XYZ", "7842913068 and another ID"])
def test_labelled_nip_rejects_a_capture_with_trailing_characters(raw):
    from kio2json.engines import extract

    cfg = form({"nip": scalar("Tax ID", normalizer="nip", pattern=r"ID: (.+)")}, ["labelled_fields"])
    assert extract(cfg, f"ID: {raw}") == {"nip": None}


@pytest.mark.parametrize(
    ("field", "value", "quote", "text"),
    [
        (scalar("Refund", type="number", normalizer="money"), 15.31, "15,31", "Signed refund -15,31"),
        (scalar("Tax ID", normalizer="nip"), "7865439120", "7865439120", "Tax ID 7865439120-7"),
        (scalar("Reference"), "JET-81", "JET-81", "Reference JET-812"),
    ],
)
def test_clipping_a_quote_cannot_change_the_source_value(field, value, quote, text):
    from kio2json.engines import extract

    cfg = form({"field": field}, ["llm"])
    model = OfflineModel(custom_output_args={"field": {"value": value, "quote": quote}})
    assert extract(cfg, text, model=model) == {"field": None}


@pytest.mark.parametrize(
    ("field", "value", "quote", "text"),
    [
        (scalar("Refund", type="number", normalizer="money"), 15.31, "15,31", "Charge -15,31. Refund 15,31."),
        (
            scalar("Amount", type="number", normalizer="money"),
            48,
            "48,00",
            "Kwota operacji Data operacji\n48,00 19.07.2031",
        ),
        (scalar("Register", normalizer="krs"), "0000087643", "0000087643", "KRS nr 0000087643"),
    ],
)
def test_verbatim_quote_can_cover_a_standalone_value(field, value, quote, text):
    from kio2json.engines import extract

    cfg = form({"field": field}, ["llm"])
    model = OfflineModel(custom_output_args={"field": {"value": value, "quote": quote}})
    assert extract(cfg, text, model=model) == {"field": value}
