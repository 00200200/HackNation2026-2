import pytest

from kio2json.power_of_attorney import extract


def test_numbered_officers_grant_for_separate_companies():
    text = """PEŁNOMOCNICTWO
My niżej podpisani:
1) Mira Wietrzna – prezes zarządu Warsztat Miedziany spółka z ograniczoną
odpowiedzialnością, KRS 0000998123
2) Wit Szklany – prokurent Latarnia spółka akcyjna, KRS 0000998345
ustanawiamy:
1) Radcę prawnego Idę Zimową pełnomocnikiem procesowym.
Adres do doręczeń: Pole Zielone"""
    result = extract(text)
    assert [(p["data"]["nazwa"], p["data"]["krs"], p["podpisujacy"]) for p in result["mocodawca"]] == [
        (
            "Warsztat Miedziany spółka z ograniczoną odpowiedzialnością",
            "0000998123",
            [{"imie_nazwisko": "Mira Wietrzna"}],
        ),
        ("Latarnia spółka akcyjna", "0000998345", [{"imie_nazwisko": "Wit Szklany"}]),
    ]
    assert result["pelnomocnicy"] == [{"imie_nazwisko": "Idę Zimową", "pesel": None}]


def test_appointee_without_title_and_printed_nominative():
    text = """Mocodawca: Latarnia sp. z o.o.
Udziela pełnomocnictwa Pani Idzie Zimowej (PESEL 92040112345).
Pełnomocnik: Ida Zimowa, PESEL 92040112345"""
    assert extract(text)["pelnomocnicy"] == [{"imie_nazwisko": "Ida Zimowa", "pesel": "92040112345"}]


@pytest.mark.parametrize("stamp_edge", ["|", "."])
def test_numbered_grant_joins_supported_letterhead_ids_and_reads_untitled_appointee(stamp_edge):
    from kio2json.classify import classify

    text = """NIP: 525-00-07-738
KRS: 0000998123
PEŁNOMOCNICTWO NR 23/2024
Działając w imieniu spółki pod firmą Latarnia Spółka Akcyjna, wpisanej do
Krajowego Rejestru Sądowego pod numerem 0000998123, udzielamy
Idzie Zimowej
numer PESEL 92040112345
pełnomocnictwa do działania.
Za Latarnia S.A.
| PROKURENT
X&@ %
Mira Wietrzna
Latarnia S.A., ul. Nowa 1
Adres do kontaktu: Miasto Pole"""
    text = text.replace("| PROKURENT", stamp_edge + " PROKURENT")
    assert classify([text]) == "power_of_attorney"
    result = extract(text)
    (principal,) = result["mocodawca"]
    assert principal["data"]["krs"] == "0000998123"
    assert principal["data"]["nip"] == "5250007738"
    assert principal["podpisujacy"] == [{"imie_nazwisko": "Mira Wietrzna"}]
    assert result["pelnomocnicy"] == [{"imie_nazwisko": "Idzie Zimowej", "pesel": "92040112345"}]


def test_distinguishes_unreadable_signature_from_a_named_electronic_signature():
    text = """Mocodawca: Latarnia sp. z o.o. udziela pełnomocnictwa.
Podpis mocodawcy: [nieczytelny]
Podpisano elektronicznie przez: Mira Wietrzna
Data podpisu: 14.03.2025
Biuro Obsługi"""
    assert extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": None}, {"imie_nazwisko": "Mira Wietrzna"}]


def test_registry_court_is_not_a_change_of_party():
    text = """Mocodawca: Latarnia Spółka Akcyjna, wpisana do Krajowego Rejestru Sądowego
prowadzonego przez Sąd Rejonowy, Wydział Gospodarczy
Krajowego Rejestru Sądowego pod numerem KRŚ: 0000998123, udziela pełnomocnictwa."""
    assert extract(text)["mocodawca"][0]["data"]["krs"] == "0000998123"


def test_digital_stamps_bind_to_the_named_grantor_and_stop_at_a_foreign_block():
    text = """Warsztat Miedziany sp. z o.o. i Latarnia S.A. udzielają pełnomocnictwa.
Za Latarnia S.A.
Podpisano elektronicznie przez: Mira Wietrzna
Za Warsztat Miedziany sp. z o.o.
Podpisano elektronicznie przez:
Wit Szklany
Osoba do kontaktu:
Podpisano elektronicznie przez: Ola Ognista"""
    result = extract(text)
    assert [p["podpisujacy"] for p in result["mocodawca"]] == [
        [{"imie_nazwisko": "Wit Szklany"}],
        [{"imie_nazwisko": "Mira Wietrzna"}],
    ]


def test_officers_of_one_principal_share_the_signature_list():
    text = """My niżej podpisani:
1) Mira Wietrzna – prezes zarządu Latarnia S.A., KRS 0000998123
2) Wit Szklany – prokurent Latarnia S.A.
udzielamy pełnomocnictwa."""
    (principal,) = extract(text)["mocodawca"]
    assert principal["data"]["krs"] == "0000998123"
    assert principal["podpisujacy"] == [{"imie_nazwisko": "Mira Wietrzna"}, {"imie_nazwisko": "Wit Szklany"}]


def test_closing_title_cannot_claim_the_next_principals_signature():
    text = """Warsztat Miedziany sp. z o.o. i Latarnia S.A. udzielają pełnomocnictwa.
W imieniu Latarnia S.A.:
.....................
Mira Wietrzna
Prokurent
W imieniu Warsztat Miedziany sp. z o.o.:
.....................
Wit Szklany
Prezes Zarządu"""
    result = extract(text)
    assert [p["podpisujacy"] for p in result["mocodawca"]] == [
        [{"imie_nazwisko": "Wit Szklany"}],
        [{"imie_nazwisko": "Mira Wietrzna"}],
    ]
