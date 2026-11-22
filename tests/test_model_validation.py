"""Format checks on grounded output, using invented values independent of any case."""

import pytest

from kio2json.class_config import load_classes
from kio2json.model_validation import validate_fields


@pytest.fixture(scope="module")
def definitions():
    return {definition.id: definition for definition in load_classes()}


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("data_operacji", "2024-02-29", "2024-02-29"),
        ("data_operacji", "2023-02-29", None),
        ("data_operacji", "29.02.2024", None),
        ("kwota", 102.74, 102.74),
        ("kwota", 0, 0),
        ("kwota", 102.743, None),
        ("kwota", float("inf"), None),
        ("kwota", True, None),
        ("na_rachunek", "74123451234512345123451234", "74123451234512345123451234"),
        ("na_rachunek", "PL74123451234512345123451234", "PL74123451234512345123451234"),
        ("z_rachunku", "DE89370400440532013000", "DE89370400440532013000"),
        ("na_rachunek", "GB82WEST12345698765432", "GB82WEST12345698765432"),
        ("na_rachunek", "gB82West12345698765432", "gB82West12345698765432"),
        ("z_rachunku", "GB83WEST12345698765432", None),
        ("z_rachunku", "DE813704004405320130000", None),  # valid checksum, wrong length
        ("z_rachunku", "74123451234512345123451235", None),
        ("na_rachunek", "00123451234512345123451305", None),  # 00 is congruent to the actual check digits 97
        ("z_rachunku", "7412345123451234512345", None),
        ("numer_transakcji", None, None),
    ],
)
def test_transfer_fields(definitions, field, value, expected):
    values = {"przelew_bankowy": {field: value}}
    assert validate_fields(definitions["bank_transfer"], values)["przelew_bankowy"][field] == expected


def test_registry_numbers_stay_with_their_original_party(definitions):
    rows = [
        {"nazwa": "Example A", "krs": "0000000099", "nip": "4321012345", "regon": "554433224"},
        {"nazwa": "Example B", "krs": "12345", "nip": "4321012340", "regon": "55443322467892"},
        {"nazwa": "Example C", "regon": "55443322567898"},  # bad parent, valid local-unit check digit
        {"nazwa": "Example D", "regon": "55443322467893"},  # valid parent, bad local-unit check digit
    ]
    result = validate_fields(definitions["appeal"], {"Zamawiajacy": rows})
    assert result["Zamawiajacy"] == [
        rows[0],
        {**rows[1], "krs": None, "nip": None},
        {**rows[2], "regon": None},
        {**rows[3], "regon": None},
    ]
    assert rows[1]["nip"] == "4321012340"


def test_pesel_in_a_nested_list(definitions):
    values = {
        "mocodawca": [],
        "pelnomocnicy": [{"pesel": "00222987659"}, {"pesel": "00222987658"}, {"pesel": "00332987653"}, {"pesel": None}],
    }
    assert validate_fields(definitions["power_of_attorney"], values) == {
        "mocodawca": [],
        "pelnomocnicy": [{"pesel": "00222987659"}, {"pesel": None}, {"pesel": None}, {"pesel": None}],
    }


@pytest.mark.parametrize(
    ("bzp", "ted", "bzp_expected", "ted_expected"),
    [
        ("2028/BZP00225588", "123459-2028", "2028/BZP00225588", "123459-2028"),
        ("2028/BZP00225588/01", None, "2028/BZP00225588/01", None),
        ("2028/BZP00225588/0", "123459-20281", None, None),
        ("123459-2028", "2028/S 011-123459", None, None),
    ],
)
def test_validate_canonical_notice_formats(definitions, bzp, ted, bzp_expected, ted_expected):
    values = {"ZamowieniePubliczne": {"numer_bzp": bzp, "numer_ted": ted}}
    assert validate_fields(definitions["appeal"], values)["ZamowieniePubliczne"] == {
        "numer_bzp": bzp_expected,
        "numer_ted": ted_expected,
    }
