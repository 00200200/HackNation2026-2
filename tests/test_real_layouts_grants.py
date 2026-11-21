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


@pytest.mark.parametrize("label_first", [False, True])
def test_one_printed_identifier_resolves_one_matching_inflected_appointment(label_first):
    appointment = "Udzielamy pełnomocnictwa Pani Aldonie Mgielnej do reprezentowania spółki."
    label = "Pełnomocnik: Aldona Mgielna, PESEL 92020367898"
    lines = [label, appointment] if label_first else [appointment, label]
    assert extract("Mocodawca: Niebieska Wstęga S.A.\n" + "\n".join(lines))["pelnomocnicy"] == [
        {"imie_nazwisko": "Aldona Mgielna", "pesel": "92020367898"}
    ]


def test_distinct_attorneys_with_similar_names_keep_their_printed_identity():
    text = """Niebieska Wstęga S.A. ustanawia Panią Aldonę Mgielną do reprezentacji.
Pełnomocnik: Alina Mgielna, PESEL 92020367898"""
    assert [p["imie_nazwisko"] for p in extract(text)["pelnomocnicy"]] == ["Aldonę Mgielną", "Alina Mgielna"]


def test_grantors_represented_in_either_order_and_independent_grantor_reconciled():
    text = """PEŁNOMOCNICTWO
Mocodawca: Polarna Przystań S.A.
Strony podpisujące:
• Olga Ognista – prokurent Iskrowa Pracownia S.A., KRS 0000812634
• Srebrna Tratwa S.A., KRS 0000812656, reprezentowana przez: prezes zarządu Mira Piankowa
udzielają pełnomocnictwa adw. Ewie Górskiej."""
    assert [(p["data"]["nazwa"], p["data"]["krs"], p["podpisujacy"]) for p in extract(text)["mocodawca"]] == [
        ("Polarna Przystań S.A.", None, []),
        ("Iskrowa Pracownia S.A.", "0000812634", [{"imie_nazwisko": "Olga Ognista"}]),
        ("Srebrna Tratwa S.A.", "0000812656", [{"imie_nazwisko": "Mira Piankowa"}]),
    ]


def test_registry_reading_stops_at_next_role_and_noisy_label_needs_ocr():
    from kio2json.power_of_attorney import normalize_registry_labels

    prefix = "Mocodawca: Srebrna Tratwa S.A., KXS: 0000812656,"
    rest = "\nZamawiający: przedsiębiorstwo, KRS 0000812634,\nudziela pełnomocnictwa."
    assert extract(prefix + rest)["mocodawca"][0]["data"]["krs"] is None
    assert extract(normalize_registry_labels(prefix) + rest)["mocodawca"][0]["data"]["krs"] == "0000812656"


def test_notarial_form_requires_an_operative_appointment():
    from kio2json.power_of_attorney import has_notarial_grant

    head = "AKT NOTARIALNY\nPrzed notariuszem stawiła się członkini zarządu spółki Srebrna Tratwa S.A.\n"
    grant = "Działając w imieniu spółki udziela pełnomocnictwa adw. Ewie Górskiej."
    assert has_notarial_grant(head + grant)
    assert not has_notarial_grant(head + "Okazano dokument zatytułowany pełnomocnictwo adw. Ewy Górskiej.")
    assert not has_notarial_grant(head + f"Przytoczono zapis dawnego dokumentu: „{grant}”")
    assert not has_notarial_grant(head + grant.replace("udziela", "nie udziela"))
    assert not has_notarial_grant(grant)


def test_capitalized_officer_title_is_not_part_of_the_company_name():
    text = """PEŁNOMOCNICTWO
1) Pola Arkadowa – Prezes Zarządu Odległy Dąb S.A., KRS 0000891234
2) Kamil Piórowy – Prokurent Kamienny Tor S.A.
udzielają pełnomocnictwa."""
    assert [(p["data"]["nazwa"], p["podpisujacy"]) for p in extract(text)["mocodawca"]] == [
        ("Odległy Dąb S.A.", [{"imie_nazwisko": "Pola Arkadowa"}]),
        ("Kamienny Tor S.A.", [{"imie_nazwisko": "Kamil Piórowy"}]),
    ]


def test_reported_grant_in_notarial_record_is_not_an_operative_appointment():
    from kio2json.power_of_attorney import has_notarial_grant

    text = """AKT NOTARIALNY
Stawająca okazała wcześniejszy dokument, w którym mocodawca udziela pełnomocnictwa adw. Ewie Górskiej."""
    assert not has_notarial_grant(text)


def test_matching_printed_names_cannot_override_conflicting_identifiers():
    text = """Niebieska Wstęga S.A. ustanawia pełnomocników.
Pełnomocnik: Aldona Mgielna, PESEL 92020367898
Pełnomocnik: Aldona Mgielna, PESEL 92020367999"""
    assert [person["pesel"] for person in extract(text)["pelnomocnicy"]] == ["92020367898", "92020367999"]


@pytest.mark.parametrize(("ocr_pages", "expected"), [({1}, "0000827135"), ({2}, None)])
def test_registry_typo_is_corrected_only_on_its_own_ocr_page(ocr_pages, expected):
    from kio2json.ocr_extract import extract_power_of_attorney

    pages = ["Mocodawca: Błękitny Grot S.A., KXS: 0000827135, udziela pełnomocnictwa.", "Informacja o dokumencie"]
    assert extract_power_of_attorney(pages, ocr_pages)["mocodawca"][0]["data"]["krs"] == expected


def test_officer_in_another_sentence_is_not_the_granting_officer():
    text = """PEŁNOMOCNICTWO
Mocodawca: Ostry Przecinek S.A., KRS 0000456981. Sprawozdanie sporządziła Eliza Migdałowa – dyrektor.
Spółka udziela pełnomocnictwa adw. Idzie Cichej."""
    assert extract(text)["mocodawca"][0]["podpisujacy"] == []


@pytest.mark.parametrize(
    ("closing", "signers"),
    [("", []), ("Aktu nie podpisano.", []), ("Odczytano, przyjęto i podpisano.", ["Lidia Miodowa"])],
)
def test_appearing_officer_requires_execution_to_be_a_notarial_signer(closing, signers):
    text = f"""AKT NOTARIALNY
Przed notariuszem stanęła Lidia Miodowa, prokurent spółki Leśny Romb S.A.
Działając w imieniu spółki udziela pełnomocnictwa adw. Idzie Cichej.
{closing}"""
    assert [s["imie_nazwisko"] for s in extract(text)["mocodawca"][0]["podpisujacy"]] == signers


@pytest.mark.parametrize("ocr_pages", [None, {1}, {2}])
@pytest.mark.parametrize(
    "history",
    [
        "Baltowy Wir S.A. okazuje poprzednie pełnomocnictwo o treści „Niebieska Róża S.A. udziela pełnomocnictwa Wandzie Lnistej do podpisu”.",
        "Okazano dokument, w którym Niebieska Róża S.A. udziela pełnomocnictwa Wandzie Lnistej do podpisu.",
    ],
)
def test_notarial_grant_uses_only_the_current_instrument(history, ocr_pages):
    from kio2json.ocr_extract import extract_power_of_attorney
    from kio2json.power_of_attorney import has_notarial_grant

    pages = [
        "Akt notarialny\n" + history,
        "Srebrny Kil S.A. niniejszym udziela pełnomocnictwa Oliwie Łagodnej do reprezentacji.",
    ]
    text = "\n".join(pages)
    assert has_notarial_grant(text)
    result = extract(text) if ocr_pages is None else extract_power_of_attorney(pages, ocr_pages)
    assert [p["data"]["nazwa"] for p in result["mocodawca"]] == ["Srebrny Kil S.A."]
    assert [p["imie_nazwisko"] for p in result["pelnomocnicy"]] == ["Oliwie Łagodnej"]


@pytest.mark.parametrize(
    "foreign",
    [
        "Zamawiający: Tkany Łuk S.A., NIP: 7526000005",
        "Zamawiający: Tkany Łuk S.A.\nNIP: 7526000005",
        "Zamawiający:\nNIP: 7526000005",
        "Zamawiający: Tkany Łuk S.A.\nKRS: 0000156647\nNIP: 7526000005",
    ],
)
def test_neighbouring_foreign_party_cannot_supply_the_principals_missing_nip(foreign):
    text = f"""PEŁNOMOCNICTWO
Mocodawca: Srebrny Kil S.A.
{foreign}
Srebrny Kil S.A. udziela adw. Oliwie Łagodnej pełnomocnictwa do reprezentowania spółki."""
    (principal,) = extract(text)["mocodawca"]
    assert (principal["data"]["nazwa"], principal["data"]["nip"]) == ("Srebrny Kil S.A.", None)


def test_letterhead_ids_can_appear_in_any_order_within_one_registry_block():
    text = """NIP: 7526000005
REGON: 123456789
KRS: 0000812656
PEŁNOMOCNICTWO
Mocodawca: Srebrny Kil S.A., KRS 0000812656, udziela pełnomocnictwa."""
    assert extract(text)["mocodawca"][0]["data"]["nip"] == "7526000005"


def test_notarial_sentence_boundaries_allow_inline_history_and_a_wrapped_professional_title():
    from kio2json.power_of_attorney import has_notarial_grant

    text = """AKT NOTARIALNY
Okazano dokument, w którym Niebieska Róża S.A. udziela pełnomocnictwa Wandzie Lnistej do podpisu. Srebrny Kil S.A. udziela pełnomocnictwa adw.
Oliwie Łagodnej do reprezentacji."""
    assert has_notarial_grant(text)
    result = extract(text)
    assert [p["data"]["nazwa"] for p in result["mocodawca"]] == ["Srebrny Kil S.A."]
    assert [p["imie_nazwisko"] for p in result["pelnomocnicy"]] == ["Oliwie Łagodnej"]
