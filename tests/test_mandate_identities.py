import pytest

from kio2json.ocr_extract import extract_power_of_attorney
from kio2json.power_of_attorney import extract


def test_company_follows_grant_verb_in_an_issuer_section():
    text = """Pełnomocnictwo
I. Mocodawca
Pełnomocnictwa udziela Morski Atrament S.A., KRS 0000963124.
II. Pełnomocnicy
adw. Celina Szklista
Zakres:
do prowadzenia sprawy, w której występuje adw. Barbara Miła."""
    result = extract(text)
    assert [(p["data"]["nazwa"], p["data"]["krs"]) for p in result["mocodawca"]] == [
        ("Morski Atrament S.A.", "0000963124")
    ]
    assert result["pelnomocnicy"] == [{"imie_nazwisko": "Celina Szklista", "pesel": None}]


@pytest.mark.parametrize("ocr_pages", [[], [1]])
def test_named_closing_signatures_stop_at_new_role(ocr_pages):
    page = """Mocodawca: Pracownia Szkliwa S.A.
Spółka ustanawia pełnomocnika.
Za Pracownia Szkliwa S.A.:
Aurelia Tęczowa
Prokurent
Felicja Łagodna
Członek Zarządu
Świadek:
Otylia Nadmorska"""
    (row,) = extract_power_of_attorney([page], ocr_pages)["mocodawca"]
    assert row["podpisujacy"] == [{"imie_nazwisko": "Aurelia Tęczowa"}, {"imie_nazwisko": "Felicja Łagodna"}]


@pytest.mark.parametrize("ocr_pages", [[], [1]])
def test_named_person_separate_from_firm_and_foreign_ids(ocr_pages):
    page = """PEŁNOMOCNICTWO
Ja, Celina Rybicka, prowadząca jednoosobową działalność gospodarczą pod nazwą
„Emaliowane Szkło”, REGON 246802468, NIP 538-17-24-310,
udzielam pełnomocnictwa adw. Marcie Zwinnej.
Zamawiający: Wielki Tygiel S.A., KRS 0000562149, NIP 1234567890.
Podpis mocodawcy:
Celina Rybicka"""
    result = extract_power_of_attorney([page], ocr_pages)
    assert result["mocodawca"] == [
        {
            "data": {
                "typ": "osoba_fizyczna",
                "imie_nazwisko": "Celina Rybicka",
                "nazwa": "Emaliowane Szkło",
                "nip": "5381724310",
                "krs": None,
            },
            "podpisujacy": [{"imie_nazwisko": "Celina Rybicka"}],
        }
    ]


def test_sole_proprietor_name_in_trade_name_requires_sole_trader_evidence():
    page = """Mocodawca: Naprawa Wag Jolanta Wolska
wpis do CEIDG, REGON: 246802468
Pełnomocnik: adw. Marta Górna
NIP 1234567890"""
    (row,) = extract(page)["mocodawca"]
    assert row["data"] == {
        "typ": "osoba_fizyczna",
        "imie_nazwisko": "Jolanta Wolska",
        "nazwa": "Naprawa Wag Jolanta Wolska",
        "nip": None,
        "krs": None,
    }
    assert not extract(page.replace("wpis do CEIDG, ", ""))["mocodawca"]


def test_principal_without_printed_firm_has_no_business_name():
    result = extract("""Mocodawca: Felicja Piórowa, przedsiębiorca wpisana do CEIDG,
NIP 9876543210. Ustanawiam pełnomocnika.""")
    (row,) = result["mocodawca"]
    assert row["data"]["imie_nazwisko"] == "Felicja Piórowa"
    assert row["data"]["nazwa"] is None
    assert row["podpisujacy"] == []


def test_foreign_trade_declaration_cannot_become_the_issuer():
    result = extract("""Mocodawca: Soczewka S.A.
Zamawiający: Celina Rybicka, prowadząca działalność gospodarczą pod firmą Żagiel, NIP 1234567890.
Spółka udziela pełnomocnictwa adw. Barbarze Miłej.""")
    (row,) = result["mocodawca"]
    assert (row["data"]["nazwa"], row["data"]["nip"]) == ("Soczewka S.A.", None)


def test_genitive_grantor_in_a_representation_clause():
    result = extract("""Działając w imieniu Antoniny Morawskiej, prowadzącej działalność gospodarczą
pod firmą Warsztat Kafli, REGON 246802468, udzielam pełnomocnictwa.""")
    (row,) = result["mocodawca"]
    assert row["data"]["imie_nazwisko"] == "Antonina Morawska"
    assert row["data"]["nazwa"] == "Warsztat Kafli"
    assert row["podpisujacy"] == []


def test_signed_proprietor_with_no_role_caption():
    result = extract("""Ja, niżej podpisana Aurelia Biała, prowadzę działalność gospodarczą pod firmą
Splot Aurelia Biała, NIP 1234567890. Ustanawiam pełnomocnika.""")
    (row,) = result["mocodawca"]
    assert row["data"]["nazwa"] == "Splot Aurelia Biała"
    assert row["podpisujacy"] == [{"imie_nazwisko": "Aurelia Biała"}]


def test_officer_acting_for_a_registered_company_is_not_a_personal_grantor():
    result = extract("""Ja, niżej podpisana Celina Rybicka, jako prezes spółki Soczewka S.A.,
prowadzącej działalność gospodarczą w zakresie optyki, KRS 0000897210, udzielam pełnomocnictwa.""")
    (row,) = result["mocodawca"]
    assert row["data"]["typ"] == "osoba_prawna"
    assert row["data"]["nazwa"] == "Soczewka S.A."


def test_signature_of_unlabelled_declarant_and_separately_labelled_firm():
    result = extract("""PEŁNOMOCNICTWO
Barbara Cichocka, wpisana do CEIDG.
Firma: Modelarnia Zachód
NIP 6481234512
udziela pełnomocnictwa adw. Marcie Szkliwnej.""")
    (row,) = result["mocodawca"]
    assert row["data"] == {
        "typ": "osoba_fizyczna",
        "nazwa": "Modelarnia Zachód",
        "imie_nazwisko": "Barbara Cichocka",
        "nip": "6481234512",
        "krs": None,
    }
    assert not row["podpisujacy"]


@pytest.mark.parametrize("heading", ["", "Świadek: "])
def test_only_a_bare_grant_subject_can_supply_the_trading_identity(heading):
    page = f"""{heading}Jolanta Pawłowska, prowadząca działalność gospodarczą pod nazwą Żuraw,
REGON 246802468, NIP 1234567890, udziela umocowania.
Podpis właściciela: Jolanta Pawłowska"""
    result = extract(page)
    if heading:
        assert result["mocodawca"] == []
    else:
        (row,) = result["mocodawca"]
        assert row["data"]["nazwa"] == "Żuraw"
        assert row["podpisujacy"] == [{"imie_nazwisko": "Jolanta Pawłowska"}]


def test_a_further_lawyer_in_a_separate_section_does_not_receive_authority():
    text = """Mocodawca: Soczewka S.A.
II. Pełnomocnicy
r. pr. Wanda Słoneczna
III. Uczestnicy
Wykonawcę konkurencyjnego reprezentuje adw. Teresa Łagodna."""
    assert extract(text)["pelnomocnicy"] == [{"imie_nazwisko": "Wanda Słoneczna", "pesel": None}]


def test_personal_card_fields_can_follow_the_business_and_identifiers():
    page = """Mocodawca:
Firma: Pracownia Korków
NIP 5991234991, REGON 245678901
Imię i nazwisko przedsiębiorcy: Aldona Mazurkiewicz
Pełnomocnik: osoba fizyczna
Imię i nazwisko: Teresa Łagodna"""
    (row,) = extract(page)["mocodawca"]
    assert row["data"] == {
        "typ": "osoba_fizyczna",
        "imie_nazwisko": "Aldona Mazurkiewicz",
        "nazwa": "Pracownia Korków",
        "krs": None,
        "nip": "5991234991",
    }
    assert row["podpisujacy"] == []


def test_undersigned_declarant_without_pronoun_signs_for_own_business():
    page = """Niżej podpisany Witold Orzechowski, prowadzący działalność gospodarczą
pod nazwą Kartografia Wydm, NIP 5362815432, udzielam pełnomocnictwa adw. Teresie Kwiatowej."""
    (row,) = extract(page)["mocodawca"]
    assert row["data"]["imie_nazwisko"] == "Witold Orzechowski"
    assert row["data"]["nazwa"] == "Kartografia Wydm"
    assert row["data"]["nip"] == "5362815432"
    assert row["podpisujacy"] == [{"imie_nazwisko": "Witold Orzechowski"}]


def test_inline_witness_owns_their_registry_numbers():
    page = """Mocodawca: Antonina Stalowa, prowadząca działalność gospodarczą pod firmą Serwis Blach,
świadkowie: Teresa Pąkowa, NIP 5250007738; udziela umocowania."""
    (row,) = extract(page.replace("\n", " "))["mocodawca"]
    assert row["data"]["nip"] is None


@pytest.mark.parametrize("recipient", ["na rzecz adw. Ewy Brzozowej", "dla radcy prawnego Wita Świeckiego"])
@pytest.mark.parametrize("own", ["", ", NIP 5260250274"])
def test_inverted_issuer_keeps_only_its_own_registry_numbers(recipient, own):
    page = f"Umocowania udziela Wąska Ścieżka S.A.{own} {recipient}, NIP 5250007738."
    (row,) = extract(page)["mocodawca"]
    assert row["data"]["nazwa"] == "Wąska Ścieżka S.A."
    assert row["data"]["nip"] == ("5260250274" if own else None)
