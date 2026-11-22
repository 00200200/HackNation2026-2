"""Invented appeals with role modifiers and explicitly identified joint authorities."""

import pytest

from kio2json.appeal import extract


@pytest.mark.parametrize(
    "caption",
    [
        "Dane identyfikacyjne strony odwołującej się",
        "Nazwa skarżącego wykonawcy",
        "Wykonawca odwołujący się",
        "Skarżący (wykonawca)",
        "Strona wnosząca odwołanie (wykonawca)",
    ],
)
def test_descriptive_appellant_owns_registry_and_counsel(caption):
    data = extract(
        f"{caption}: Pracownia Kwarcu sp. z o.o.\nNIP: 1234567890\n"
        "Pełnomocnik odwołującego: adw. Anna Szklana\n"
        "Powiat jako zamawiający: Powiat Jaspisowy\nREGON: 234567890\n"
        "Pełnomocnik zamawiających\nadw. Ewa Kredka\nNIP: 3456789012\nZarzuty"
    )
    (app,) = data["Odwolujacy"]
    assert (app["nazwa"], app["nip"], app["pelnomocnik"]["imie_nazwisko"]) == (
        "Pracownia Kwarcu sp. z o.o.",
        "1234567890",
        "Anna Szklana",
    )
    (buyer,) = data["Zamawiajacy"]
    assert (buyer["nazwa"], buyer["regon"], buyer["nip"]) == ("Powiat Jaspisowy", "234567890", None)


@pytest.mark.parametrize("link", ["Pełnomocnik zamawiających", "Lider postępowania", "Postępowanie prowadzi"])
@pytest.mark.parametrize("member", ["Gmina Opalowa", "Powiat Jaspisowy"])
def test_lead_field_names_existing_member(link, member):
    data = extract(
        "Wspólni zamawiający (reprezentant zamawiających):\n"
        "1. Gmina Opalowa\nNIP: 1234567890\n2. Powiat Jaspisowy\nREGON: 234567890\n"
        f"{link}: {member}\nZarzuty"
    )
    assert [(p["nazwa"], p["nip"], p["regon"], p["prowadzacy_postepowanie"]) for p in data["Zamawiajacy"]] == [
        ("Gmina Opalowa", "1234567890", None, int(member == "Gmina Opalowa" and link != "Pełnomocnik zamawiających")),
        (
            "Powiat Jaspisowy",
            None,
            "234567890",
            int(member == "Powiat Jaspisowy" and link != "Pełnomocnik zamawiających"),
        ),
    ]


@pytest.mark.parametrize(
    "caption",
    [
        "Dane pełnomocnika skarżącego wykonawcy",
        "Strona przystępująca (wykonawca)",
        "Stanowisko skarżącego wykonawcy",
        "Rachunek gminy jako zamawiającego",
        "Dane odwołującej się wykonawcy",
        "Dane nieskarżącego wykonawcy",
        "Wykonawca nieodwołujący się",
    ],
)
def test_dependent_and_disagreeing_roles_have_no_owner(caption):
    data = extract(f"{caption}: Fabryka Ołówków sp. z o.o.\nNIP: 1234567890\nZarzuty")
    assert data["Odwolujacy"] == data["Zamawiajacy"] == []


@pytest.mark.parametrize(
    "marker", ["(prowadząca postępowanie)", "(pełnomocnik zamawiających do prowadzenia postępowania)"]
)
def test_member_mark_after_registry_belongs_to_that_member(marker):
    data = extract("Dane zamawiających:\n1. Powiat Jaspisowy\n2. Gmina Opalowa\nNIP: 1234567890\n" + marker)
    assert [(p["nazwa"], p["prowadzacy_postepowanie"]) for p in data["Zamawiajacy"]] == [
        ("Powiat Jaspisowy", 0),
        ("Gmina Opalowa", 1),
    ]


def test_external_attorney_and_unmarked_members():
    text = (
        "Zamawiający wspólnie (przedstawiciel zamawiających):\n1. Gmina Opalowa\n2. Powiat Jaspisowy\n"
        "Pełnomocnik zamawiających:\nKancelaria Kwarcu sp. z o.o.\nNIP: 1234567890"
    )
    assert [(p["nazwa"], p["nip"], p["prowadzacy_postepowanie"]) for p in extract(text)["Zamawiajacy"]] == [
        ("Gmina Opalowa", None, 0),
        ("Powiat Jaspisowy", None, 0),
    ]


@pytest.mark.parametrize("separator", [" ", "\n"])
def test_named_lead_between_members_keeps_the_rest_of_the_list(separator):
    text = (
        "Dane zamawiających:\n1. Gmina Opalowa\n2. Powiat Jaspisowy\n"
        f"Postępowanie prowadzi:{separator}Powiat Jaspisowy\n3. Miasto Kwarcowe\nNIP: 1234567890"
    )
    assert [(p["nazwa"], p["nip"], p["prowadzacy_postepowanie"]) for p in extract(text)["Zamawiajacy"]] == [
        ("Gmina Opalowa", None, 0),
        ("Powiat Jaspisowy", None, 1),
        ("Miasto Kwarcowe", "1234567890", 0),
    ]


@pytest.mark.parametrize(
    "caption",
    [
        "Pełnomocnik wspólnych zamawiających",
        "Dane pełnomocnika zamawiających",
        "Strona przystępująca (wykonawca)",
    ],
)
def test_bare_opponent_card_stops_name_and_registry_collection(caption):
    text = f"Powiat jako zamawiający: Powiat Jaspisowy\n{caption}\nKancelaria Opalu sp. z o.o.\nNIP: 1234567890"
    (buyer,) = extract(text)["Zamawiajacy"]
    assert (buyer["nazwa"], buyer["nip"]) == ("Powiat Jaspisowy", None)
