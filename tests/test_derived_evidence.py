"""Invented excerpts for organizer fields whose output differs from the printed words."""

import pytest

from kio2json.class_config import OutputField
from kio2json.derived_evidence import derived_value


def check(key, proposed, quote, text):
    kind = "integer" if key in {"czynnosc_powod_id", "przez-pelnomocnika"} else "string"
    return derived_value(key, OutputField(type=kind, instruction="Test"), proposed, quote, text)


@pytest.mark.parametrize(
    ("key", "source", "result"),
    [
        ("numer_bzp", "2028/BZP 00449933/04", "2028/BZP00449933/04"),
        ("numer_ted", "2028/S 077-345679", "345679-2028"),
        ("numer_ted", "345679-2028", "345679-2028"),
    ],
)
def test_notice_uses_the_entire_printed_reference(key, source, result):
    assert check(key, result, source, f"Ogłoszenie: {source}.") == result
    assert check(key, result, source[1:], source) is None
    assert check(key, result, source, "X/" + source) is None
    assert check(key, result, source, source + "-X") is None
    assert check(key, result, source, "Brak") is None


def test_model_cannot_omit_a_bzp_correction_or_change_a_ted_year():
    assert check("numer_bzp", "2028/BZP00449933", "2028/BZP 00449933", "2028/BZP 00449933/04") is None
    assert check("numer_ted", "345679-2027", "2028/S 077-345679", "2028/S 077-345679") is None


def test_negated_rejection_does_not_evidence_a_decision_to_reject():
    text = "Zarzut nr 1: Zamawiający nie odrzucił oferty."
    assert check("czynnosc_powod_id", 1, text, text) is None


def test_reason_must_be_supported_by_the_first_charge():
    first = "Zarzut nr 1: zaniechanie odrzucenia oferty."
    second = "Zarzut nr 2: odrzucenie oferty."
    text = first + "\n" + second
    assert check("czynnosc_powod_id", 7, "zaniechanie odrzucenia oferty", text) == 7
    assert check("czynnosc_opis", "Zaniechanie odrzucenia oferty", first, text) == "Zaniechanie odrzucenia oferty"
    assert check("czynnosc_powod_id", 1, "1", text) is None
    assert check("czynnosc_powod_id", 1, "odrzucenia", text) is None
    assert check("czynnosc_powod_id", 7, "zaniechanie odrzuc", text) is None
    assert check("czynnosc_powod_id", 1, second, text) is None
    assert check("czynnosc_powod_id", 1, second, second) is None
    assert check("czynnosc_powod_id", 1, "odrzucenie oferty", "Uzasadnienie: odrzucenie oferty") is None


def test_first_charge_quote_uses_original_character_offsets():
    text = "Zarzut nr 1: w sprawie\n      zaniechanie odrzucenia oferty."
    assert check("czynnosc_powod_id", 7, "zaniechanie odrzucenia oferty", text) == 7
    assert check("czynnosc_powod_id", 7, "w sprawie", text) is None


@pytest.mark.parametrize(
    ("key", "value", "line", "accepted"),
    [
        ("przez-pelnomocnika", 1, "Odwołujący reprezentowany przez pełnomocnika", True),
        ("przez-pelnomocnika", 0, "Odwołujący działa osobiście", True),
        ("przez-pelnomocnika", 1, "Zamawiający reprezentowany przez pełnomocnika", False),
        ("przez-pelnomocnika", 1, "Odwołujący nie jest reprezentowany przez pełnomocnika", False),
        ("przez-pelnomocnika", 0, "Odwołujący: brak danych", False),
        ("typ", "osoba_prawna", "Mocodawca: Fabryka Prób sp. z o.o.", True),
        ("typ", "osoba_fizyczna", "Mocodawca: osoba fizyczna", True),
        ("typ", "osoba_prawna", "Pełnomocnik: Fabryka Prób sp. z o.o.", False),
        ("typ", "osoba_prawna", "Mocodawca: reprezentowany przez Fabryka Prób sp. z o.o.", False),
        ("typ", "osoba_prawna", "Mocodawca: Fabryka Prób sp. z o.o. sp.k.", False),
        ("typ", "osoba_fizyczna", "Mocodawca: Fabryka Prób sp. z o.o.", False),
    ],
)
def test_role_fields_require_explicit_evidence(key, value, line, accepted):
    assert check(key, value, line, line) == (value if accepted else None)
    assert check(key, value, line, "Brak") is None
