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


def test_numbered_grant_joins_supported_letterhead_ids_and_reads_untitled_appointee():
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
