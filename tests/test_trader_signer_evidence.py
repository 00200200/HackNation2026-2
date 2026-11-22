"""Independent examples of execution by or on behalf of an identified proprietor."""

import pytest

from kio2json.ocr_extract import extract_power_of_attorney
from kio2json.power_of_attorney import extract

MANDATE = """PEŁNOMOCNICTWO
Mocodawca: Olga Michalska, przedsiębiorca wpisana do CEIDG.
Udzielam pełnomocnictwa adw. Robertowi Walczakowi do składania wyjaśnień."""
OWNER = "Olga Michalska"
PROXY = "Marta Górska"


@pytest.mark.parametrize("scan", [False, True], ids=["native", "ocr"])
@pytest.mark.parametrize(
    ("closing", "expected"),
    [
        ("Czytelny podpis przedsiębiorcy\nOlga Michalska", OWNER),
        ("Olga Michalska\n(podpis właścicielki)", OWNER),
        ("Podpisała: Olga Michalska", OWNER),
        ("Olga Michalska", OWNER),
        ("Olga Michalska – właścicielka", OWNER),
        ("Podpisano elektronicznie przez: Olga Michalska", OWNER),
        ("Podpis przedstawiciela mocodawcy: Marta Górska", PROXY),
        ("Z upoważnienia mocodawcy\nMarta Górska", PROXY),
        ("Pełnomocnik: Robert Walczak\nPodpis mocodawcy — Olga Michalska", OWNER),
        ("Podpis przedsiębiorcy: Olga Michalska\nZa zgodność z oryginałem\nPodpis: Robert Walczak", OWNER),
        ("", None),
        ("Podpis właścicielki: [nieczytelny]", None),
        ("Miejsce na podpis przedsiębiorcy\n________________", None),
        ("Adres do korespondencji:\nOlga Michalska", None),
        ("Pełnomocnictwo przyjmuję.\nPodpis przedsiębiorcy: Olga Michalska", None),
        ("Za zgodność z oryginałem\nPodpis przedsiębiorcy: Olga Michalska", None),
        ("Podpis przedstawiciela mocodawcy: Robert Walczak", None),
        ("Podpis właścicielki: Marta Górska", None),
        ("Podpis: Marta Górska", None),
        ("Podpis odbiorcy: Olga Michalska", None),
        ("Podpis świadka\n..........\nMarta Górska", None),
    ],
)
def test_issuer_signer_requires_execution_evidence(closing, expected, scan):
    page = MANDATE + "\n" + closing
    result = extract_power_of_attorney([page], [1]) if scan else extract(page)
    (issuer,) = result["mocodawca"]
    assert issuer["data"]["imie_nazwisko"] == OWNER
    assert issuer["podpisujacy"] == ([{"imie_nazwisko": expected}] if expected else [])


def test_issuer_signature_can_follow_a_separately_signed_receipt():
    page = MANDATE + "\nPrzyjmuję pełnomocnictwo.\nRobert Walczak\nPodpis mocodawcy:\nOlga Michalska"
    assert extract(page)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": OWNER}]


@pytest.mark.parametrize("scan", [False, True], ids=["native", "ocr"])
def test_undersigned_proxy_executes_for_trader_named_in_genitive(scan):
    page = """PEŁNOMOCNICTWO
Ja, niżej podpisana Marta Górska, działając w imieniu Olgi Michalskiej,
prowadzącej działalność gospodarczą pod nazwą „Zioła”, udzielam pełnomocnictwa do złożenia wniosku."""
    result = extract_power_of_attorney([page], [1]) if scan else extract(page)
    (row,) = result["mocodawca"]
    assert row["data"]["imie_nazwisko"] == OWNER
    assert row["podpisujacy"] == [{"imie_nazwisko": PROXY}]


@pytest.mark.parametrize("scanned", [[1], [2]])
def test_mixed_page_provenance_preserves_issuer_and_excludes_copy_certifier(scanned):
    pages = [
        MANDATE + "\nCzytelny podpis przedsiębiorcy",
        "Olga Michalska\nPoświadczenie zgodności kopii\nPodpisano elektronicznie przez: Marta Górska",
    ]
    (row,) = extract_power_of_attorney(pages, scanned)["mocodawca"]
    assert row["podpisujacy"] == [{"imie_nazwisko": OWNER}]


def test_passive_issuance_also_has_an_explicit_execution_field():
    page = """PEŁNOMOCNICTWO
Pełnomocnictwo udzielone przez Olgę Michalską, prowadzącą działalność gospodarczą pod nazwą „Zioła”,
uprawnia do odbioru dokumentacji.
W imieniu mocodawcy podpisała: Marta Górska"""
    (row,) = extract(page)["mocodawca"]
    assert row["data"]["imie_nazwisko"] == OWNER
    assert row["podpisujacy"] == [{"imie_nazwisko": PROXY}]


def test_wrapping_the_grant_does_not_change_the_printed_signature():
    page = MANDATE.replace("do składania", "\ndo składania") + "\nOlga Michalska"
    assert extract(page)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": OWNER}]


def test_copy_certification_with_carriage_return_lines_keeps_ocr_provenance():
    pages = [MANDATE, "Za zgodność z oryginałem\rPodpisano elektronicznie przez: Marta Górska"]
    (row,) = extract_power_of_attorney(pages, [2])["mocodawca"]
    assert row["podpisujacy"] == []


@pytest.mark.parametrize("scan", [False, True], ids=["native", "ocr"])
@pytest.mark.parametrize(
    ("closing", "expected"),
    [
        ("Osoba do kontaktu:\nMarta Wolska\nPodpis mocodawcy:\n_________________", None),
        ("Pieczęć mocodawcy: ................\nDane kontrahenta:\nNazwa firmy: Warsztat Miedziany", None),
        ("Koordynator postępowania:\nMarta Wolska\n(podpis mocodawcy)", None),
        ("Adresat korespondencji\nMarta Wolska\nPodpis przedsiębiorcy:\nOlga Michalska", OWNER),
        ("Osoba do kontaktu\nMarta Wolska\nPodpis przedstawiciela mocodawcy:\nMarta Górska", PROXY),
        ("Marta Górska\n(podpis przedstawiciela mocodawcy)", PROXY),
    ],
)
def test_other_fields_keep_their_names_next_to_a_signature(closing, expected, scan):
    page = MANDATE + "\n" + closing
    result = extract_power_of_attorney([page], [1]) if scan else extract(page)
    (issuer,) = result["mocodawca"]
    assert issuer["podpisujacy"] == ([{"imie_nazwisko": expected}] if expected else [])


@pytest.mark.parametrize("scan", [False, True], ids=["native", "ocr"])
@pytest.mark.parametrize(
    ("recipient", "expected"),
    [
        ("Pełnomocnik: Robert Walczak", OWNER),
        ("Dane pełnomocnika:\nRobert Walczak", OWNER),
        ("Pełnomocnik: Robert Walczak\nPrzyjmuję pełnomocnictwo.", None),
        ("Pełnomocnictwo przyjmuję.\nPełnomocnik: Robert Walczak", None),
        ("Za zgodność z oryginałem\nDane pełnomocnika:\nRobert Walczak", None),
    ],
)
def test_owner_can_sign_after_recipient_details(recipient, expected, scan):
    page = MANDATE + "\n" + recipient + "\nPodpis właścicielki: Olga Michalska"
    result = extract_power_of_attorney([page], [1]) if scan else extract(page)
    (issuer,) = result["mocodawca"]
    assert issuer["podpisujacy"] == ([{"imie_nazwisko": expected}] if expected else [])
