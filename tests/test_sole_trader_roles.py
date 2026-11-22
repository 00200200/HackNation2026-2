"""Fictional grants exercising the distinction between a trader and other named people."""

import pytest

from kio2json.power_of_attorney import extract


def _grants(text):
    return extract("PEŁNOMOCNICTWO\n" + text)["mocodawca"]


@pytest.mark.parametrize(
    ("text", "owner"),
    [
        pytest.param(
            "Mocodawca: Pracownia Tafli Hanna Wierzbicka\n"
            "Forma działalności: jednoosobowa działalność gospodarcza\n"
            "Udzielam pełnomocnictwa do odbioru dokumentów.",
            "Hanna Wierzbicka",
            id="business-name-with-owner-at-end",
        ),
        pytest.param(
            "Mocodawca: Filip Grabowski Naprawa Zegarów\n"
            "Przedsiębiorca wpisany do CEIDG. Udziela pełnomocnictwa do złożenia oferty.",
            "Filip Grabowski",
            id="business-name-with-owner-at-start",
        ),
        pytest.param(
            "Ja, niżej podpisana Celina Borowska, prowadzę działalność gospodarczą "
            "pod firmą „Bibułkowy Dom” i udzielam pełnomocnictwa do podpisania wniosku.",
            "Celina Borowska",
            id="first-person-finite-verb",
        ),
        pytest.param(
            "Jako właściciel zakładu „Mechanika Zaworowa” ja, Dariusz Lipiński, "
            "udzielam pełnomocnictwa do reprezentowania mnie w postępowaniu.",
            "Dariusz Lipiński",
            id="first-person-owner-title",
        ),
        pytest.param(
            "Kinga Modlińska prowadząca działalność gospodarczą pod firmą „Farbka” "
            "udziela pełnomocnictwa do przeglądania akt.",
            "Kinga Modlińska",
            id="third-person-participle",
        ),
        pytest.param(
            "Właścicielka pracowni „Stalowy Dzwonek”, Barbara Orłowska, udziela pełnomocnictwa do złożenia wyjaśnień.",
            "Barbara Orłowska",
            id="third-person-owner-apposition",
        ),
        pytest.param(
            "Pełnomocnictwa udziela Tomasz Brzozowski, prowadzący działalność "
            "gospodarczą pod nazwą „Zecernia”, do reprezentowania go przed komisją.",
            "Tomasz Brzozowski",
            id="post-verbal-subject",
        ),
        pytest.param(
            "Mocodawca: zakład introligatorski „Wolna Karta”\n"
            "Udzielam pełnomocnictwa do wniesienia odwołania.\n"
            "Podpis właścicielki: Renata Jaworska",
            "Renata Jaworska",
            id="owner-signature-under-business-grant",
        ),
        pytest.param(
            "Mocodawca: Emilia Laskowska\nAdres: ul. Fikcyjnej Latarni 7\n"
            "NIP: 0000000000\nProwadzę działalność gospodarczą pod nazwą „Przesmyk”.\n"
            "Udzielam pełnomocnictwa do odbioru pism.",
            "Emilia Laskowska",
            id="owner-followed-by-address-and-id",
        ),
        pytest.param(
            "Działając w imieniu Joanny Malinowskiej, prowadzącej działalność "
            "gospodarczą pod firmą „Cichy Młyn”, udzielam pełnomocnictwa do złożenia oferty.",
            "Joanna Malinowska",
            id="genitive-woman-in-representation-clause",
        ),
        pytest.param(
            "Mocodawca (dane z CEIDG)\nFirma: Sklep Lutniczy\n"
            "Imię i nazwisko przedsiębiorcy: Adam Piasecki\n"
            "Udzielam pełnomocnictwa do uzyskania odpisu.",
            "Adam Piasecki",
            id="ceidg-card",
        ),
        pytest.param(
            "Mocodawcą jest Alicja Gajewska, właścicielka firmy „Trzy Nuty”.\n"
            "Udziela pełnomocnictwa Michałowi Borkowskiemu do zawarcia umowy.",
            "Alicja Gajewska",
            id="owner-before-dative-attorney",
        ),
        pytest.param(
            "Pełnomocnictwo udzielone przez Pawła Dębowskiego, prowadzącego działalność "
            "gospodarczą pod nazwą „Kwarcowy Kąt”, obejmuje złożenie oferty.",
            "Paweł Dębowski",
            id="masculine-accusative-after-przez",
        ),
        pytest.param(
            "Mocodawca: firma „Lakowy Liść”\n"
            "Udzielam pełnomocnictwa do podpisania protokołu.\n"
            "Podpis przedsiębiorcy: Halina Górska",
            "Halina Górska",
            id="signature-of-granting-entrepreneur",
        ),
    ],
)
def test_personal_grantor_of_business(text, owner):
    principals = _grants(text)
    assert [(p["data"]["typ"], p["data"]["imie_nazwisko"]) for p in principals] == [("osoba_fizyczna", owner)]


def test_named_entrepreneur_with_parenthesized_tax_id():
    principals = _grants(
        "Przedsiębiorca Witold Czarnecki (NIP 0000000135) udziela pełnomocnictwa "
        "do odbioru korespondencji w swoim imieniu."
    )
    assert [(p["data"]["imie_nazwisko"], p["data"]["nip"], p["data"]["typ"]) for p in principals] == [
        ("Witold Czarnecki", "0000000135", "osoba_fizyczna")
    ]


@pytest.mark.parametrize(
    ("card", "owner", "business"),
    [
        pytest.param(
            "Mocodawca: osoba fizyczna\nImię i nazwisko: Teresa Janicka\nNazwa firmy: Warsztat Przecinków",
            "Teresa Janicka",
            "Warsztat Przecinków",
            id="personal-and-commercial-name-fields",
        ),
        pytest.param(
            "Mocodawca (dane z CEIDG)\nImię: Norbert\nNazwisko: Majewski\nNazwa firmy: Farbiarnia Kreska",
            "Norbert Majewski",
            "Farbiarnia Kreska",
            id="separate-given-name-and-surname",
        ),
    ],
)
def test_trader_card_keeps_personal_and_business_names(card, owner, business):
    principals = _grants(card + "\nUdzielam pełnomocnictwa do wglądu w akta.")
    assert [(p["data"]["imie_nazwisko"], p["data"]["nazwa"], p["data"]["typ"]) for p in principals] == [
        (owner, business, "osoba_fizyczna")
    ]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(
            "Mocodawca: zakład naprawczy „Wolne Koło”\n"
            "Forma działalności: jednoosobowa działalność gospodarcza\n"
            "Udzielam pełnomocnictwa do złożenia oferty.\nPodpis właściciela: [nieczytelny]",
            id="owner-name-absent",
        ),
        pytest.param(
            "Mocodawca: piekarnia „Ciepły Rogal”\n"
            "Udzielam pełnomocnictwa do reprezentacji.\n"
            "Pełnomocnik: Rafał Rudnicki, prowadzący działalność gospodarczą pod firmą „Paragraf”.",
            id="attorney-owns-another-business",
        ),
        pytest.param(
            "Mocodawca: warsztat „Zielony Tokarz”\nUdzielam pełnomocnictwa do odbioru pisma.\n"
            "Świadek: Maria Wolska, właścicielka firmy „Spiralny Drut”.",
            id="witness-has-owner-title",
        ),
        pytest.param(
            "Mocodawca: Lutnia sp. z o.o.\nUdziela pełnomocnictwa do zawarcia umowy.\n"
            "Podpis przedstawiciela mocodawcy: Anna Leszczyńska, prezes zarządu.",
            id="corporate-officer-signature",
        ),
        pytest.param(
            "Mocodawca: zakład „Suchy Most”\nUdzielam pełnomocnictwa do składania pism.\n"
            "Adres do korespondencji pełnomocnika: ul. Blanki Piórkowskiej 11",
            id="address-dedication",
        ),
        pytest.param(
            "Mocodawca: studio „Wąska Wstążka”\nUdzielam pełnomocnictwa do udziału w przetargu.\n"
            "Pełnomocnictwo przyjmuję.\nPodpis pełnomocnika: Karolina Czerwińska",
            id="acceptance-signature",
        ),
        pytest.param(
            "Mocodawca: Czółenko sp. z o.o.\nUdzielamy pełnomocnictwa do prowadzenia sprawy.\n"
            "Świadek: Andrzej Rogowski\nNumer wpisu świadka do CEIDG: brak",
            id="third-party-ceidg-on-corporate-grant",
        ),
        pytest.param(
            "Mocodawca: firma „Lakowy Liść”\nUdzielam pełnomocnictwa do podpisania protokołu.\n"
            "Pełnomocnik (przyjęcie pełnomocnictwa):\nPodpis przedsiębiorcy: Halina Górska",
            id="signature-of-appointed-entrepreneur",
        ),
        pytest.param(
            "Mocodawca: Srebrny Próg\nŹródło danych firmy: CEIDG\nImię i nazwisko przedsiębiorcy: [brak]\n"
            "Udzielam pełnomocnictwa do przeglądania akt.",
            id="two-word-brand-without-printed-owner",
        ),
    ],
)
def test_other_roles_do_not_supply_a_personal_grantor(text):
    assert [p["data"]["imie_nazwisko"] for p in _grants(text) if p["data"]["imie_nazwisko"]] == []
