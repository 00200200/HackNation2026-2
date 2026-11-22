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


@pytest.mark.parametrize(
    "firm", ["Zielona Introligatornia\nBolesław Lipowy", "Zielona Introligatornia Bolesław Lipowy"]
)
def test_proprietors_defined_role_and_wrapped_business_name(firm):
    page = f"""Pełnomocnictwo
Ja, niżej podpisany Bolesław Lipowy, prowadzący działalność gospodarczą pod firmą
{firm}, NIP 5413125874, zwany dalej „Mocodawcą”, ustanawiam pełnomocnikiem adw. Teresę Witkowską."""
    (row,) = extract(page)["mocodawca"]
    assert row["data"] == {
        "typ": "osoba_fizyczna",
        "imie_nazwisko": "Bolesław Lipowy",
        "nazwa": "Zielona Introligatornia Bolesław Lipowy",
        "nip": "5413125874",
        "krs": None,
    }
    assert row["podpisujacy"] == [{"imie_nazwisko": "Bolesław Lipowy"}]


@pytest.mark.parametrize(
    ("firm_and_contact", "name"),
    [
        ("„Pudełka i Pióra”\nTelefon do biura: 650 000 123", "Pudełka i Pióra"),
        ("Pudełka i Pióra\nE-mail: biuro@example.invalid", "Pudełka i Pióra"),
        ("«Pudełka,\nPióra i Papier» z punktem usługowym w mieście", "Pudełka, Pióra i Papier"),
        ("Atelier\n„Bocian”\nDane kontaktowe: biuro@example.invalid", "Atelier „Bocian”"),
        ('Studio "Atlas, Horyzont"\nSkrzynka kontaktowa: B12', 'Studio "Atlas, Horyzont"'),
        ("„Atelier „Bocian” i Syn” z punktem usługowym w mieście", "Atelier „Bocian” i Syn"),
    ],
)
def test_business_name_finishes_at_its_closing_quote_or_next_label(firm_and_contact, name):
    page = f"""Ja, Irena Miętowa, prowadząca działalność gospodarczą pod nazwą {firm_and_contact}
NIP 7654321089, udzielam umocowania."""
    (row,) = extract(page)["mocodawca"]
    assert row["data"]["nazwa"] == name
    assert row["data"]["nip"] == "7654321089"


@pytest.mark.parametrize(
    ("business", "declaration_scanned", "expected"),
    [
        ("Łucja Wąsik Ceramika", True, "Łucja Wąsik Ceramika"),
        ("Łucja Wasik Ceramika", True, None),
        ("Ceramika Łucja Wasik", True, None),
        ("Ceramika Ozdobna", True, "Ceramika Ozdobna"),
        ("Łucja Wasik Ceramika", False, "Łucja Wasik Ceramika"),
    ],
)
def test_only_scanned_business_name_abstains_on_conflicting_personal_spelling(business, declaration_scanned, expected):
    declaration = f"""PEŁNOMOCNICTWO
Ja, niżej podpisana Łucja Wąsik, prowadząca działalność gospodarczą pod nazwą {business},
NIP 6489072176, udzielam pełnomocnictwa adw. Żanecie Szkliwnej."""
    pages = ["Pismo przewodnie", declaration]
    (row,) = extract_power_of_attorney(pages, {2} if declaration_scanned else {1})["mocodawca"]
    assert row["data"]["nazwa"] == expected
    assert row["data"]["imie_nazwisko"] == "Łucja Wąsik"
    assert row["data"]["nip"] == "6489072176"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("Łucja Wasik Ceramika", "Łucja Wasik Ceramika"),
        ("Łucja Wasik CeramikaArt", None),
        ("ArtŁucja Wasik Ceramika", None),
    ],
)
def test_independent_native_printing_supports_a_business_name_from_a_scan(printed, expected):
    declaration = """Mocodawca: Łucja Wąsik, wpisana do CEIDG.
Firma: Łucja Wasik Ceramika
NIP 6489072176. Udzielam umocowania."""
    (row,) = extract_power_of_attorney([declaration, f"Firma: {printed}"], {1})["mocodawca"]
    assert row["data"]["nazwa"] == expected


@pytest.mark.parametrize("header", ["Dane mocodawcy:", "Mocodawca:", "Osoba udzielająca pełnomocnictwa:"])
def test_named_proprietor_with_registry_card_and_no_trade_narrative(header):
    record = extract(f"""PEŁNOMOCNICTWO
{header}
Magdalena Jaworska
NIP: 7654321089
Nazwa firmy: Sigillum
Udzielam pełnomocnictwa adwokatowi.
Świadek: Klara Prosta, NIP 0000000000.""")
    (row,) = record["mocodawca"]
    assert row["data"] == {
        "typ": "osoba_fizyczna",
        "imie_nazwisko": "Magdalena Jaworska",
        "nazwa": "Sigillum",
        "nip": "7654321089",
        "krs": None,
    }


def test_registered_firm_field_can_print_the_only_personal_name():
    text = (
        "PEŁNOMOCNICTWO\nMocodawca (osoba fizyczna wpisana do CEIDG)\n"
        "Firma przedsiębiorcy: Pracownia Szkła Maria Jaworska\n"
        "NIP: 0000000071\nUdzielam umocowania do wglądu w akta."
    )
    data = extract(text)["mocodawca"][0]["data"]
    assert (data["imie_nazwisko"], data["nazwa"], data["nip"]) == (
        "Maria Jaworska",
        "Pracownia Szkła Maria Jaworska",
        "0000000071",
    )


def test_registered_firm_with_two_personal_names_is_ambiguous():
    text = (
        "PEŁNOMOCNICTWO\nMocodawca (dane z CEIDG)\n"
        "Firma przedsiębiorcy: Ewa Wolska i Jan Kowalski\nUdzielam umocowania do odbioru pisma."
    )
    assert not extract(text)["mocodawca"]


def test_genitive_owner_repeated_in_business_name_still_needs_nominative():
    text = (
        "PEŁNOMOCNICTWO\nDziałając w imieniu Jana Kowalskiego, prowadzącego działalność gospodarczą "
        "pod firmą „Warsztat Jana Kowalskiego”, udzielam pełnomocnictwa do odbioru pisma."
    )
    data = extract(text)["mocodawca"][0]["data"]
    assert data["imie_nazwisko"] == "Jan Kowalski"
    assert data["nazwa"] == "Warsztat Jana Kowalskiego"


def test_first_person_sentence_inside_recipient_block_keeps_its_role():
    text = (
        "PEŁNOMOCNICTWO\nMocodawca: zakład „Lampa”\nPełnomocnik: Ja, Jan Kowalski, "
        "prowadzący działalność gospodarczą pod firmą „Beta”.\nUdzielam pełnomocnictwa do odbioru pisma."
    )
    assert not extract(text)["mocodawca"]


@pytest.mark.parametrize("prefix", ["Przedsiębiorca:", "Mocodawca: przedsiębiorca"])
def test_entrepreneur_title_does_not_turn_a_brand_into_a_person(prefix):
    text = f"PEŁNOMOCNICTWO\n{prefix} Czerwony Rower (NIP 0000000111) udziela pełnomocnictwa do odbioru pism."
    assert not extract(text)["mocodawca"]


def test_bare_grantor_does_not_take_attorneys_business():
    text = (
        "PEŁNOMOCNICTWO\nJan Kowalski prowadzący działalność gospodarczą,\n"
        "Pełnomocnik: Anna Nowak, właścicielka firmy „Podmiot Obcy”.\n"
        "Udzielam pełnomocnictwa do odebrania pisma."
    )
    data = extract(text)["mocodawca"][0]["data"]
    assert (data["imie_nazwisko"], data["nazwa"]) == ("Jan Kowalski", None)


@pytest.mark.parametrize(
    "body",
    [
        "Udzielam pełnomocnictwa do odebrania pisma.\nPełnomocniczka:\nPodpis przedsiębiorcy: Anna Nowak",
        (
            "Dane osoby upoważnionej:\nImię i nazwisko: Anna Nowak\nNIP 0000000111\n"
            "Udzielam pełnomocnictwa do odebrania pisma."
        ),
    ],
)
def test_appointed_woman_cannot_supply_the_proprietor_identity(body):
    assert not extract("PEŁNOMOCNICTWO\nMocodawca: firma „Lampa”\n" + body)["mocodawca"]
