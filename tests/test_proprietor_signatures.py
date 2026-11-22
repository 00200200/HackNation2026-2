import pytest

from kio2json.power_of_attorney import extract


def test_printed_owner_signature_keeps_the_issuer_business_and_tax_number():
    text = """Mocodawca:
Nazwa firmy: Pracownia Koralików
NIP 0000000123
Udzielam pełnomocnictwa do odebrania dokumentów.
Podpis właścicielki:
Lidia Tomaszewska
Świadek: Marek Kwiatkowski, NIP 0000000456"""
    assert extract(text)["mocodawca"] == [
        {
            "data": {
                "imie_nazwisko": "Lidia Tomaszewska",
                "krs": None,
                "nazwa": "Pracownia Koralików",
                "nip": "0000000123",
                "typ": "osoba_fizyczna",
            },
            "podpisujacy": [{"imie_nazwisko": "Lidia Tomaszewska"}],
        }
    ]


@pytest.mark.parametrize(
    "closing",
    [
        "Podpis właściciela: [nieczytelny]",
        "Podpis właściciela: Złoty Pierścień",
        "Podpis właściciela: Piotr Zaleski\nPodpis właściciela: Karol Makowski",
        "Przyjmuję pełnomocnictwo.\nPodpis właściciela: Piotr Zaleski",
        "Świadek czynności:\nPodpis właściciela: Piotr Zaleski",
    ],
)
def test_ambiguous_or_third_party_signatures_do_not_identify_the_grantor(closing):
    text = "Mocodawca: firma „Pięć Skrzyń”\nUdzielam pełnomocnictwa do odebrania akt.\n" + closing
    assert extract(text)["mocodawca"] == []


def test_company_owned_site_does_not_make_its_signer_a_personal_issuer():
    text = """Mocodawca: zakład spółki „Kuźnia”
Udziela pełnomocnictwa do odbioru ofert.
Podpis właściciela: Piotr Zaleski"""
    assert extract(text)["mocodawca"] == []
