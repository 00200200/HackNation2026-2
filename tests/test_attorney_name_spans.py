"""Invented attorney grants exercising the span contract at the class field boundary."""

import json

import pytest

from kio2json.class_config import load_classes
from kio2json.llm import grounded


@pytest.fixture
def grant(monkeypatch):
    monkeypatch.setenv("KIO_LLM_API_KEY", "")
    return next(definition for definition in load_classes() if definition.id == "power_of_attorney")


def names(grant, proposal, source, shown=None, alternates=()):
    recipients = grant.fields["pelnomocnicy"]
    data = [{"imie_nazwisko": proposal, "pesel": None}]
    return grounded(recipients, data, source, source if shown is None else shown, alternates=alternates)[0][
        "imie_nazwisko"
    ]


@pytest.mark.parametrize(
    "appointment",
    [
        "Upoważnienie otrzymuje Ewa Zimowa.",
        "Osoba umocowana: Ewa Zimowa",
        "Udziela pełnomocnictwa osobie wymienionej poniżej.\nOsoba umocowana: Ewa Zimowa",
    ],
)
def test_recipient_surname_recovers_printed_full_name(grant, appointment):
    source = "PEŁNOMOCNICTWO\nMocodawca: Pracownia Wydruku sp. z o.o.\n" + appointment + "\nData: 01.03.2026"
    assert names(grant, "Zimowa", source) == "Ewa Zimowa"


@pytest.mark.parametrize(
    "source",
    [
        "Mocodawca: Ewa Zimowa\nOsoba umocowana: Zimowa",
        "Osoba umocowana: Ewa\nZimowa",
        "Osoba umocowana: Ewa\tZimowa",
        "Osoba umocowana: Zimowa\nMocodawca: Jan Zimowy",
        "Osoba umocowana: Ewa Zimowa\nPełnomocnik: Anna Zimowa",
        "Pełnomocnicy: Ewa Zimowa oraz Anna Zimowa",
        "Osoba umocowana: Ewa Zimowa-Nowak",
        "Pełnomocnik: Ewa Zimowa sp. z o.o.",
    ],
)
def test_singleton_abstains_without_unique_attributable_printed_name(grant, source):
    assert names(grant, "Zimowa", source) is None


def test_preserves_all_printed_components_and_visible_evidence(grant):
    source = "Osoba umocowana: Iga Maria Wiosenna-Jasna"
    assert names(grant, "Wiosenna-Jasna", source) == "Iga Maria Wiosenna-Jasna"
    assert names(grant, "Maria Wiosenna-Jasna", source) == "Iga Maria Wiosenna-Jasna"
    assert names(grant, "Iga", source, "Osoba umocowana: Iga") is None
    alt = "Osoba umocowana: Hanna Wiosenna-Jasna"
    assert names(grant, "Wiosenna-Jasna", source, alternates=((alt, alt),)) is None


def test_schema_describes_recipient_and_cited_profile_keeps_its_contract(grant):
    field = grant.fields["pelnomocnicy"].items.fields["imie_nazwisko"]
    assert "Given name and surname" in json.dumps(grant.span_model.model_json_schema())
    cited = {"quote": "Ewa Zimowa", "value": "Zimowa"}
    assert names(grant, cited, "Osoba umocowana: Ewa Zimowa") == "Zimowa"
    assert field.instruction in json.dumps(grant.cited_model.model_json_schema())


@pytest.mark.parametrize("proposal", ["Wiosenna", "Iga Wiosenna"])
def test_inline_identifier_label_is_outside_the_printed_name(grant, proposal):
    assert names(grant, proposal, "Pełnomocnik: Iga Wiosenna PESEL 00000000000") == "Iga Wiosenna"


def test_whole_printed_name_in_free_prose_preserves_all_parts(grant):
    source = "Wymieniona w dokumencie adwokat Élodie García-López otrzymuje umocowanie."
    assert names(grant, "Élodie García-López", source) == "Élodie García-López"


def test_name_with_lowercase_particle_recovered_from_same_printed_line(grant):
    assert names(grant, "Berg", "Osoba umocowana: Anna van den Berg") == "Anna van den Berg"


@pytest.mark.parametrize(
    "rows", [[], [{"imie_nazwisko": None, "pesel": None}], [{"imie_nazwisko": "Lidia Ciepła", "pesel": None}]]
)
def test_missing_recipient_uses_only_explicit_appointment(grant, rows):
    source = (
        "PEŁNOMOCNICTWO\nMocodawca: Lidia Ciepła\nUdziela pełnomocnictwa osobie wymienionej poniżej.\n"
        "Osoba umocowana: Ewa Zimowa\nData: 01.03.2026"
    )
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": "Ewa Zimowa", "pesel": None}
    ]
    assert grounded(grant.fields["pelnomocnicy"], [], source, source) == []


@pytest.mark.parametrize(
    "source,rows",
    [
        ("Osoba umocowana: Ewa Zimowa\nPESEL świadka: 00000000000", [{"imie_nazwisko": None, "pesel": "00000000000"}]),
        ("Osoba umocowana: Ewa Zimowa\nPełnomocnik: Jan Zimowy", []),
        ("Pełnomocnicy: Ewa Zimowa oraz Jan Zimowy", []),
        ("Osoba umocowana: Ewa Zimowa", [{"imie_nazwisko": None, "pesel": None}] * 2),
        ("Osoba umocowana: Ewa Zimowa sp. z o.o.", []),
    ],
)
def test_unresolved_records_are_preserved_without_guessing(grant, source, rows):
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == rows


def test_named_and_numbered_recipient_can_fill_matching_record(grant):
    source = "Osoba umocowana: Ewa Zimowa, PESEL: 00000000000"
    rows = [{"imie_nazwisko": None, "pesel": "00000000000"}]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": "Ewa Zimowa", "pesel": "00000000000"}
    ]


@pytest.mark.parametrize(
    "source",
    [
        "Udzielam pełnomocnictwa Janowi Leśnemu.",
        "Upoważniam Jana Leśnego.",
        "Przykład wypełnienia dokumentu:\nOsoba umocowana: Ewa Zimowa",
        "To nie jest udzielone pełnomocnictwo.\nOsoba umocowana: Ewa Zimowa",
        "Jeśli nastąpi zatwierdzenie:\nOsoba umocowana: Ewa Zimowa",
        "Wzór pełnomocnictwa\nPełnomocnik: Ewa Zimowa",
        "Pierwotne pełnomocnictwo zostało odwołane.\nOsoba umocowana: Ewa Zimowa",
        "Osoba umocowana: Ewa Zimowa oraz Anna Letnia.",
    ],
)
def test_new_record_requires_operative_nominative_appointment(grant, source):
    assert grounded(grant.fields["pelnomocnicy"], [], source, source, spans=True) == []


def test_singleton_name_cannot_be_attached_to_a_different_persons_identifier(grant):
    source = "Mocodawca: Iga Letnia, PESEL: 00000000000\nOsoba umocowana: Ewa Zimowa"
    rows = [{"imie_nazwisko": "Zimowa", "pesel": "00000000000"}]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": None, "pesel": "00000000000"}
    ]


@pytest.mark.parametrize("other", ["Podpisano przez: Lidia Ciepła", "Załącznik podpisała Lidia Ciepła."])
def test_sole_explicit_recipient_outweighs_printed_signer(grant, other):
    source = "Osoba umocowana: Ewa Zimowa\n" + other
    rows = [{"imie_nazwisko": "Lidia Ciepła", "pesel": None}]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": "Ewa Zimowa", "pesel": None}
    ]


def test_one_appointment_cannot_expand_to_two_identical_rows(grant):
    source = "Osoba umocowana: Ewa Zimowa"
    rows = [{"imie_nazwisko": "Ewa", "pesel": None}, {"imie_nazwisko": "Zimowa", "pesel": None}]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": "Ewa Zimowa", "pesel": None}
    ]


@pytest.mark.parametrize("name", ["Zimowa", "Ewa Zimowa"])
def test_direct_recipient_never_acquires_another_attorneys_pesel(grant, name):
    source = "Osoba umocowana: Ewa Zimowa, PESEL: 00000000000\nPełnomocnik: Anna Jasna, PESEL: 11111111111"
    rows = [{"imie_nazwisko": name, "pesel": "11111111111"}]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        {"imie_nazwisko": None, "pesel": "11111111111"}
    ]


@pytest.mark.parametrize(
    "appointment",
    [
        "Wymieniona w dokumencie adwokat Anna Jasna otrzymuje umocowanie.",
        "Drugim pełnomocnikiem jest Anna Jasna.",
        "Anna Jasna otrzymuje pełnomocnictwo.",
    ],
)
def test_mixed_label_and_affirmative_prose_preserve_both_recipients(grant, appointment):
    source = "Pełnomocnik: Ewa Zimowa\n" + appointment + "\nZałącznik podpisała Lidia Ciepła."
    rows = [{"imie_nazwisko": name, "pesel": None} for name in ("Ewa Zimowa", "Anna Jasna", "Lidia Ciepła")]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        *rows[:2],
        {"imie_nazwisko": None, "pesel": None},
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "Wymieniona w dokumencie adwokat Anna Jasna nie otrzymuje umocowania.",
        "Anna Jasna podpisała protokół. Umocowanie otrzymuje inna osoba.",
        "Drugim pełnomocnikiem nie jest Anna Jasna.",
    ],
)
def test_other_mentions_do_not_establish_a_second_appointment(grant, statement):
    source = "Pełnomocnik: Ewa Zimowa\n" + statement
    rows = [{"imie_nazwisko": name, "pesel": None} for name in ("Ewa Zimowa", "Anna Jasna")]
    assert grounded(grant.fields["pelnomocnicy"], rows, source, source, spans=True) == [
        rows[0],
        {"imie_nazwisko": None, "pesel": None},
    ]
