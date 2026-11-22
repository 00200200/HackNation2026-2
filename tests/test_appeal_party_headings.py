"""Owner-labelled captions on invented appeal cards."""

import pytest

from kio2json.appeal import extract
from kio2json.classify import classify


@pytest.mark.parametrize(
    "label",
    [
        "Dane odwołującego",
        "Nazwa i adres odwołującego",
        "Wykonawca wnoszący odwołanie",
        "Dane podmiotu składającego odwołanie",
    ],
)
def test_inflected_role_binds_only_its_own_card(label):
    text = (
        f"{label}:\nPracownia\nSzklanych Map\nul. Skrajna 2\nNIP: 1234567890\n"
        "Nazwa i adres zamawiającego: Urząd Ksiąg\nNIP: 2345678901\n"
        "Pełnomocnik zamawiającego\nadw. Anna Szklana\n"
        "Wybrany wykonawca\nStudio Planet\nNIP: 3456789012\n"
        "Przystępujący\nStudio Szronu\nNIP: 4567890123\nODWOŁANIE"
    )
    result = extract(text)
    assert [(a["nazwa"], a["nip"], a["przez-pelnomocnika"]) for a in result["Odwolujacy"]] == [
        ("Pracownia Szklanych Map", "1234567890", 0)
    ]
    assert [(a["nazwa"], a["nip"]) for a in result["Zamawiajacy"]] == [("Urząd Ksiąg", "2345678901")]


@pytest.mark.parametrize(
    "caption", ["Pełnomocnik zamawiającego", "Rachunek zamawiającego", "Dane przystępującego", "Wybrany wykonawca"]
)
def test_unrelated_role_with_company_evidence(caption):
    result = extract(f"ODWOŁANIE\n{caption}:\nFabryka Map sp. z o.o.\nNIP: 1234567890")
    assert result["Odwolujacy"] == result["Zamawiajacy"] == []


@pytest.mark.parametrize(
    "context",
    ["II. Uzasadnienie", "Zamawiający w odpowiedzi wskazał:", "Cytat z pisma przeciwnika:", "Z pisma wynika: „", "„"],
)
def test_quoted_party_heading_in_pleading(context):
    text = f"ODWOŁANIE\n{context}\nDane odwołującego:\nFabryka Rulonów sp. z o.o.\nNIP: 1234567890"
    assert extract(text)["Odwolujacy"] == []


def test_role_syntax_requires_local_evidence_and_judgment_keeps_own_route():
    assert extract("Dane zamawiającego:\nNIP: 1234567890\nZarzuty")["Zamawiajacy"] == []
    assert extract("Dane odwołującego:\nBrak informacji o stronie.\nODWOŁANIE")["Odwolujacy"] == []
    assert extract("Dane odwołującego:\nRadca prawny Anna Szklana\nNIP: 1234567890")["Odwolujacy"] == []
    assert classify(["WYROK\nODWOŁANIE\nDane odwołującego:\nPapierowy Most sp. z o.o."]) is None


def test_opposing_counsel_is_a_boundary_before_a_bare_attorney_name():
    text = (
        "Dane odwołującego:\nPort Szkła sp. z o.o.\n"
        "Pełnomocnik zamawiającego\nadw. Anna Szklana\nKancelaria Szkła\n"
        "Wybrany wykonawca\nDom Kart sp. z o.o.\nNIP: 1234567890"
    )
    (appellant,) = extract(text)["Odwolujacy"]
    assert (appellant["nazwa"], appellant["przez-pelnomocnika"], appellant["nip"]) == ("Port Szkła sp. z o.o.", 0, None)


@pytest.mark.parametrize("authority", ["Dane zamawiajacego", "Jednostka zamawiajaca", "Zamawiajacy (nazwa i adres)"])
@pytest.mark.parametrize("punctuation", [":", ""])
def test_adjacent_native_card_columns_keep_names_and_identifiers(tmp_path, punctuation, authority):
    from reportlab.pdfgen.canvas import Canvas

    from kio2json.pipeline import process_pdf

    path = tmp_path / "cards.pdf"
    pdf = Canvas(str(path), pagesize=(600, 800))
    pdf.drawString(35, 770, "Odwolanie do Prezesa KIO")
    for i, (left, right) in enumerate(
        [
            (f"Dane odwolujacego{punctuation}", f"{authority}{punctuation}"),
            ("Most z Papieru", "Port ze Szklanek"),
            ("NIP: 1234567890", "NIP: 2345678901"),
        ]
    ):
        pdf.drawString(35, 740 - 16 * i, left)
        pdf.drawString(320, 740 - 16 * i, right)
    pdf.drawString(35, 620, "Zarzuty")
    pdf.drawString(35, 600, "Wnosimy odwolanie.")
    pdf.save()
    kind, record = process_pdf(path)
    assert kind == "appeal"
    assert [(p["nazwa"], p["nip"]) for p in record["Odwolujacy"]] == [("Most z Papieru", "1234567890")]
    assert [(p["nazwa"], p["nip"]) for p in record["Zamawiajacy"]] == [("Port ze Szklanek", "2345678901")]


def test_overlapping_native_fonts_keep_original_value_tokens(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    from kio2json.pipeline import process_pdf

    path = tmp_path / "overlap.pdf"
    pdf = Canvas(str(path))
    pdf.drawString(40, 760, "Odwolanie do Prezesa KIO")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, 720, "Dane odwolujacego:")
    pdf.setFont("Courier", 12)
    pdf.drawString(112, 720, "Atlas sp. z o.o.")
    pdf.drawString(40, 702, "NIP: 1234567890")
    pdf.drawString(40, 670, "Zamawiajacy: Port Koszy")
    pdf.drawString(35, 620, "Zarzuty")
    pdf.drawString(35, 600, "Wnosimy odwolanie.")
    pdf.save()
    kind, record = process_pdf(path)
    assert kind == "appeal"
    assert [(p["nazwa"], p["nip"]) for p in record["Odwolujacy"]] == [("Atlas sp. z o.o.", "1234567890")]


def test_contact_and_ids_on_opposing_counsel_card_stay_with_that_card():
    result = extract(
        "Dane odwołującego:\nDom Map sp. z o.o.\nPełnomocnik zamawiającego: izba@example.test\n"
        "adw. Ula Nowa\nNIP: 1234567890\nODWOŁANIE"
    )
    (party,) = result["Odwolujacy"]
    assert (party["nip"], party["przez-pelnomocnika"]) == (None, 0)


def test_a_bare_unsupported_caption_closes_the_previous_card():
    result = extract(
        "Dane odwołującego:\nDom Map sp. z o.o.\nDane zamawiającego\nPełnomocnik zamawiającego\nNIP: 1234567890"
    )
    assert result["Zamawiajacy"] == []
    assert result["Odwolujacy"][0]["nazwa"] == "Dom Map sp. z o.o."


def test_prose_and_quoted_appointments_supply_no_party_evidence():
    assert extract("ODWOŁANIE\nDane odwołującego:\nGmina odmówiła wydania informacji.\nZarzuty")["Odwolujacy"] == []
    result = extract(
        "Dane odwołującego:\nDom Map sp. z o.o.\nODWOŁANIE\nII. Uzasadnienie\n"
        "Zamawiający napisał:\nPełnomocnik odwołującego: adw. Ula Nowa\nKancelaria Mostu"
    )
    assert result["Odwolujacy"][0]["przez-pelnomocnika"] == 0
    assert (
        extract(
            "ODWOŁANIE\nZamawiający napisał: „W odpowiedzi podajemy dane.\n"
            "Dane odwołującego:\nDom Map sp. z o.o.\nNIP: 1234567890\n”"
        )["Odwolujacy"]
        == []
    )


def test_representation_in_quoted_body_is_excluded_from_native_card_inventory(monkeypatch, tmp_path):
    from kio2json import pipeline
    from kio2json.pdf_text import WordBox

    lines = [
        "Dane odwołującego:",
        "Dom Map sp. z o.o.",
        "ODWOŁANIE",
        "II. Uzasadnienie",
        "Zamawiający napisał:",
        "Pełnomocnik odwołującego:",
        "adw. Anna Szklana",
    ]

    def read(path, **options):
        options["page_sizes"][1] = (600, 800)
        options["word_boxes"].extend(
            WordBox(1, line, 30, i * 16 + 35, 260, i * 16 + 45) for i, line in enumerate(lines)
        )
        return ["\n".join(lines)]

    monkeypatch.setattr(pipeline, "read_pages", read)
    kind, data = pipeline.process_pdf(tmp_path / "card.pdf")
    assert kind == "appeal"
    assert data["Odwolujacy"][0]["przez-pelnomocnika"] == 0


@pytest.mark.parametrize(
    "quoted",
    [
        "Pełnomocnik odwołującego\nAnna Szklana",
        "W imieniu odwołującego jako pełnomocnik wnoszę odwołanie.",
    ],
)
def test_opponent_statement_cannot_supply_filing_or_signature(quoted):
    text = "Dane odwołującego:\nDom Map sp. z o.o.\nODWOŁANIE\nII. Uzasadnienie\nZamawiający napisał:\n" + quoted
    assert extract(text)["Odwolujacy"][0]["przez-pelnomocnika"] == 0


def test_signature_after_closed_quotation_still_belongs_to_the_filing():
    text = (
        "Dane odwołującego:\nDom Map sp. z o.o.\nODWOŁANIE\nII. Uzasadnienie\n"
        "Zamawiający napisał: „Treść odpowiedzi.\nPełnomocnik odwołującego\nAnna Szklana\n”\n"
        "Pełnomocnik odwołującego\nUla Nowa"
    )
    assert extract(text)["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"] == "Ula Nowa"


@pytest.mark.parametrize("separator", [" ", "\n"])
def test_name_and_street_on_the_same_value_row(separator):
    text = f"ODWOŁANIE\nNazwa i adres zamawiającego:{separator}Dom Map sp. z o.o., ul. Skrajna 4\nNIP: 1234567890"
    assert [(p["nazwa"], p["nip"]) for p in extract(text)["Zamawiajacy"]] == [("Dom Map sp. z o.o.", "1234567890")]


@pytest.mark.parametrize(
    "caption",
    [
        "Nazwa i adres organizatora postępowania",
        "Dane jednostki zamawiającej",
        "Instytucja prowadząca postępowanie o udzielenie zamówienia",
        "Podmiot udzielający zamówienia",
        "Zamawiający (nazwa i adres)",
        "Jednostka zamawiająca",
        "Dane instytucji organizującej postępowanie",
    ],
)
def test_authority_description_keeps_printed_name_and_registry(caption):
    result = extract(f"{caption}\nMuzeum Latawców\nREGON: 123456789\nODWOŁANIE")
    assert [(p["nazwa"], p["regon"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Muzeum Latawców", "123456789", None)
    ]


def test_joint_caption_does_not_assume_first_member_leads():
    result = extract(
        "Dane zamawiających wspólnie:\n1. Gmina Lampionów\nNIP: 1234567890\n"
        "2. Miasto Wstęg (zamawiający prowadzący postępowanie)\nNIP: 2345678901\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["nip"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Gmina Lampionów", "1234567890", 0),
        ("Miasto Wstęg", "2345678901", 1),
    ]


@pytest.mark.parametrize("action", ["prowadzący", "przeprowadzający"])
def test_separate_lead_card_and_member_card_keep_ownership(action):
    result = extract(
        "Jednostka zamawiająca:\nMuzeum Latawców\nREGON: 123456789\n"
        f"Podmiot {action} postępowanie:\nGmina Lampionów\nNIP: 1234567890\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["regon"], p["nip"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Muzeum Latawców", "123456789", None, 0),
        ("Gmina Lampionów", None, "1234567890", 1),
    ]


@pytest.mark.parametrize("caption", ["Pełnomocnik zamawiającego", "Rachunek zamawiającego", "Odpowiedź zamawiającego"])
def test_unlabelled_negative_closes_authority_card(caption):
    result = extract(f"Organizator postępowania:\nGmina Lampionów\n{caption}\nStudio Tuby sp. z o.o.\nNIP: 1234567890")
    assert [(p["nazwa"], p["nip"]) for p in result["Zamawiajacy"]] == [("Gmina Lampionów", None)]


@pytest.mark.parametrize("caption", ["Zamawiający (nazwa i adres)", "Dane instytucji prowadzącej postępowanie"])
def test_decorated_authority_requires_evidence_and_ignores_charges(caption):
    assert extract(f"{caption}:\nNie ustalono.\nZarzuty")["Zamawiajacy"] == []
    assert extract(f"ODWOŁANIE\nZarzuty\n{caption}:\nGmina Lampionów\nREGON: 123456789")["Zamawiajacy"] == []


def test_joint_public_bodies_can_supply_their_own_name_evidence():
    result = extract(
        "Jednostki wspólnie prowadzące postępowanie:\n1. Województwo Lazurowe\n2. Powiat Szklany\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Województwo Lazurowe", 0),
        ("Powiat Szklany", 0),
    ]


@pytest.mark.parametrize("separator", [": ", " "])
def test_numbered_authorities_with_inline_registry(separator):
    result = extract(
        f"Dane zamawiających:\n1. Gmina Lampionów NIP{separator}1234567890\n"
        f"2. Powiat Szklany NIP{separator}2345678901\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["nip"]) for p in result["Zamawiajacy"]] == [
        ("Gmina Lampionów", "1234567890"),
        ("Powiat Szklany", "2345678901"),
    ]


def test_numbered_counsel_is_not_a_joint_authority():
    result = extract("Dane zamawiających:\n1. Gmina Lampionów\n2. Pełnomocnik zamawiającego\nNIP: 2345678901")
    assert [(p["nazwa"], p["nip"]) for p in result["Zamawiajacy"]] == [("Gmina Lampionów", None)]


def test_authority_response_is_a_body_section():
    assert (
        extract("ODWOŁANIE\nOdpowiedź zamawiającego:\nDane instytucji zamawiającej:\nGmina Lampionów")["Zamawiajacy"]
        == []
    )


def test_numbered_joint_authority_keeps_id_after_inline_street():
    result = extract(
        "Dane zamawiających:\n1. Gmina Lampionów, ul. Zielona 4, NIP: 1234567890\n2. Powiat Szklany\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["nip"]) for p in result["Zamawiajacy"]] == [
        ("Gmina Lampionów", "1234567890"),
        ("Powiat Szklany", None),
    ]


@pytest.mark.parametrize("boundary", ["Odpowiedź zamawiającego:", "Zarzuty", "Cytat z pisma:"])
def test_plain_role_in_authority_response_has_no_owner(boundary):
    assert extract(f"ODWOŁANIE\n{boundary}\nZamawiający: Gmina Lampionów\nNIP: 1234567890")["Zamawiajacy"] == []


def test_inline_lead_value_opens_its_own_card_next_to_numbered_members():
    result = extract(
        "Dane zamawiających:\n1. Gmina Lampionów\nNIP: 1234567890\n"
        "Podmiot prowadzący postępowanie: Muzeum Latawców\n"
        "2. Powiat Szklany\nREGON: 123456789"
    )
    assert [(p["nazwa"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Gmina Lampionów", 0),
        ("Muzeum Latawców", 1),
        ("Powiat Szklany", 0),
    ]
