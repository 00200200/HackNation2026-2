"""Complete source tokens must support every normalized value, even for short citations."""

import re

import pytest
from pydantic_ai.models.test import TestModel as OfflineModel

from kio2json.class_config import DocumentClass, OutputField
from kio2json.engines import extract
from kio2json.output_schema import cited_value, scalar_value


def typed_field(normalizer):
    return OutputField(type="number" if normalizer == "money" else "string", normalizer=normalizer, instruction="Value")


@pytest.mark.parametrize("group", [" ", "\xa0", "\u2009", "\u202f", "'", "’", "_", ".", ","])
def test_amount_accepts_only_the_complete_number(group):
    field = typed_field("money")
    decimal = "." if group == "," else ","
    token = f"9{group}876{group}543{decimal}21"
    source = f"Saldo: {token} CHF."
    assert cited_value(field, 9876543.21, token, source) == 9876543.21
    positions = [i for i, char in enumerate(token) if char.isdigit()]
    for start in positions:
        for end in positions:
            if end < start or (start == 0 and end == len(token) - 1):
                continue
            fragment = token[start : end + 1]
            number = float(fragment.replace(group, "").replace(decimal, "."))
            assert cited_value(field, number, source, source) is None
            assert cited_value(field, number, fragment, source) is None


@pytest.mark.parametrize(
    ("name", "token", "expected"),
    [
        ("nip", "PL 471-368-95-72", "4713689572"),
        ("krs", "nr 0000374268", "0000374268"),
        ("regon", "76124358967413", "76124358967413"),
        ("pesel", "84163925714", "84163925714"),
        ("account_number", "PL38" + " 6129" * 6, "38" + "6129" * 6),
        ("iso_date", "27.04.2036", "2036-04-27"),
    ],
)
def test_identifiers_and_dates_require_the_complete_token(name, token, expected):
    field = typed_field(name)
    source = f"Value: {token}."
    assert cited_value(field, expected, token, source) == expected
    positions = [i for i, char in enumerate(token) if char.isdigit()]
    for first in positions:
        for last in positions:
            if last < first or (first == positions[0] and last == positions[-1]):
                continue
            fragment = token[first : last + 1]
            assert cited_value(field, expected, fragment, source) is None
            assert cited_value(field, fragment, token, source) is None

    bare = re.sub(r"^(?:PL|nr)\s*", "", token)
    for separator in ("-", " ", "\u2009"):
        for longer in (f"72{separator}{bare}", f"{bare}{separator}46", f"72{separator}{bare}{separator}46"):
            assert cited_value(field, expected, bare, longer) is None
            assert cited_value(field, expected, longer, longer) is None


@pytest.mark.parametrize("token", ["87,23zł", "87,23PLN", "EUR87,23", "87,23 zł", "EUR 87,23", "€87,23", "87.23£"])
def test_currency_affix_preserves_amount(token):
    assert cited_value(typed_field("money"), 87.23, token, f"Gross: {token}.") == 87.23


@pytest.mark.parametrize("engines", [["llm"], ["labelled_fields", "llm"]])
def test_offline_model_cannot_ground_partial_field_values(engines):
    cases = {
        "balance": ("money", 876.54, "Saldo: 9 876,54 PLN"),
        "fee": ("money", 234.56, "Fee: 1’234,56 CHF"),
        "account": ("account_number", "38" + "6129" * 6, "Account: PL38" + " 6129" * 6 + " 7429"),
        "mail": (None, "north@example.org", "Mailbox: audit.north@example.org"),
        "ref": (None, "GULL-81", "Reference: GULL-81-B"),
        "gross": ("money", 87.23, "Gross: 87,23zł"),
    }
    config = DocumentClass(
        id="statement",
        routing={"required": ["Saldo"]},
        engines=engines,
        fields={name: typed_field(normalizer) for name, (normalizer, _, _) in cases.items()},
    )
    model = OfflineModel(custom_output_args={k: {"value": v, "quote": q} for k, (_, v, q) in cases.items()})
    result = extract(config, "\n".join(q for _, _, q in cases.values()), model=model)
    assert result == {**dict.fromkeys(cases), "gross": 87.23}


@pytest.mark.parametrize(
    ("token", "partial"),
    [("9 _876,54", 876.54), (".54", 54), ("74,62_ABC", 74.62), ("99,999,999,999,999.99", 99999999999999.98)],
)
def test_malformed_or_rounded_source_cannot_confirm_amount(token, partial):
    assert cited_value(typed_field("money"), partial, token, token) is None


def test_adjacent_date_and_amount_columns_keep_both_values():
    text = "Kwota / Data\n48,00 19.07.2031"
    assert cited_value(typed_field("iso_date"), "2031-07-19", "19.07.2031", text) == "2031-07-19"
    assert cited_value(typed_field("money"), 48, "48,00", text) == 48


@pytest.mark.parametrize(
    ("name", "token"), [("nip", "471--368-95-72"), ("money", "1,234,56"), ("money", "99,999,999,999,999.99")]
)
def test_labelled_and_model_normalization_abstain_on_invalid_or_unrepresentable_values(name, token):
    field = typed_field(name)
    assert scalar_value(field, token) is None
    assert cited_value(field, token, token, token) is None
