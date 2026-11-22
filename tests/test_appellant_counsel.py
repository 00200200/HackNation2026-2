import pytest

from kio2json.appeal import extract


def counsel(text):
    appeal = "ODWOŁANIE\nOdwołujący: Porcelana S.A.\nZamawiający: Powiat Opolski\n"
    party = extract(appeal + text)["Odwolujacy"][0]
    rep = party["pelnomocnik"]
    return party["przez-pelnomocnika"], rep["imie_nazwisko"], rep["nazwa"], rep["mail"]


@pytest.mark.parametrize(
    "block",
    [
        "Podpis pełnomocnika Odwołującego:\nadw. Nina Polna\nKancelaria Polna\nsekretariat@example.org",
        (
            "W imieniu Odwołującego wnoszę odwołanie jako jego pełnomocnik.\n"
            "radca prawny Nina Polna\nKancelaria Polna\ne-mail: sekretariat@example.org"
        ),
        "Za Odwołującego:\nadwokat Nina Polna\nKancelaria Polna\nsekretariat@example.org",
        "Odwołującego reprezentuje radca prawny Nina Polna\nKancelaria Polna\nsekretariat@example.org",
    ],
)
def test_appellant_owns_contact_record(block):
    assert counsel(block) == (1, "Nina Polna", "Kancelaria Polna", "sekretariat@example.org")


def test_firm_letterhead_is_linked_by_the_same_lawyer():
    text = (
        "Kancelaria Polna\nadw. Nina Polna\nbiuro@example.org\nODWOŁANIE\nOdwołujący: Porcelana S.A.\n"
        "Zamawiający: Powiat Opolski\nZa Odwołującego podpisuje:\nadw. Nina Polna"
    )
    party = extract(text)["Odwolujacy"][0]
    assert party["pelnomocnik"] == {
        "imie_nazwisko": "Nina Polna",
        "nazwa": "Kancelaria Polna",
        "mail": "biuro@example.org",
    }


def test_absent_counsel_contact_and_separate_party_mail():
    assert counsel("Za Odwołującego:\nadw. Nina Polna\nAdres do doręczeń Odwołującego: party@example.org") == (
        1,
        "Nina Polna",
        None,
        None,
    )
    assert counsel("Odwołujący wnosi niniejsze odwołanie przez pełnomocnika.") == (1, None, None, None)


@pytest.mark.parametrize(
    "block",
    [
        "Za Odwołującego:\nPrezes zarządu Nina Polna\nbiuro@example.org",
        "Za Zamawiającego:\nadw. Nina Polna\nKancelaria Polna\nbiuro@example.org",
        "Załączniki:\nPodpis pełnomocnika Odwołującego:\nadw. Nina Polna\nKancelaria Polna",
        "W odpowiedzi przytoczono:\n„Za Odwołującego:\nadw. Nina Polna”",
        "Odwołujący działa osobiście.\nPełnomocnik przystępującego:\nadw. Nina Polna",
    ],
)
def test_no_counsel_from_another_role(block):
    assert counsel(block) == (0, None, None, None)


def test_independent_firm_line_in_an_appointment():
    text = (
        "ODWOŁANIE\nOdwołujący: Porcelana S.A.\nreprezentowana przez pełnomocnika:\n"
        "Marka Zielińskiego\nZieliński i Partnerzy\ne-mail: biuro@example.org\nZamawiający: Gmina Opole"
    )
    assert extract(text)["Odwolujacy"][0]["pelnomocnik"]["nazwa"] == "Zieliński i Partnerzy"


def test_capacity_first_filing_then_signature_on_next_rows():
    assert counsel(
        "Działając jako pełnomocnik spółki Porcelana S.A., wnoszę odwołanie.\n"
        "Z poważaniem\nradca prawny Oskar Lis\nKancelaria Lis\nbiuro@example.org"
    ) == (1, "Oskar Lis", "Kancelaria Lis", "biuro@example.org")


def test_signature_role_after_the_signatory():
    assert counsel(
        "Z poważaniem\nadwokat Sara Kłos\npełnomocnik procesowy Odwołującego\nKancelaria Kłos\nbiuro@example.org"
    ) == (1, "Sara Kłos", "Kancelaria Kłos", "biuro@example.org")


def test_filing_does_not_end_the_search_for_its_signed_record():
    assert counsel(
        "Odwołujący wnosi odwołanie przez pełnomocnika.\nZarzuty i wnioski\n"
        "Za Odwołującego:\nadw. Nina Polna\nKancelaria Polna\nsekretariat@example.org"
    ) == (1, "Nina Polna", "Kancelaria Polna", "sekretariat@example.org")


def test_named_board_member_does_not_create_a_mandate():
    assert counsel("Odwołującego reprezentuje prezes zarządu Adam Las.") == (0, None, None, None)
    assert counsel("Odwołującego reprezentuje\nczłonek zarządu Adam Las") == (0, None, None, None)


def test_explicit_client_service_contact_is_not_the_lawyers_email():
    party = extract(
        "ODWOŁANIE\nOdwołujący: Porcelana S.A.\nreprezentowana przez: adw. Nina Polna\n"
        "Adres do doręczeń Odwołującego: spolka@example.org"
    )["Odwolujacy"][0]
    assert party["pelnomocnik"]["mail"] is None


def test_one_line_signature_and_contacts():
    assert counsel("W imieniu Odwołującego:\nadw. Nina Polna, Kancelaria Polna, e-mail: np@example.org") == (
        1,
        "Nina Polna",
        "Kancelaria Polna",
        "np@example.org",
    )


def test_another_partys_lawyer_in_an_account_of_the_hearing():
    assert counsel("Odwołujący wskazuje, że inny oferent działa przez pełnomocnika.\nadw. Nina Polna") == (
        0,
        None,
        None,
        None,
    )


def test_explicit_professional_capacity_with_wrapped_role_and_name():
    assert counsel(
        "Podpis pełnomocnika strony odwołującej:\nradca prawny\nMaria Las\nKancelaria Las\ne-mail: ml@example.org"
    ) == (1, "Maria Las", "Kancelaria Las", "ml@example.org")


@pytest.mark.parametrize(
    "block",
    [
        "Zamawiający wskazał:\nPełnomocnik odwołującego:\nadw. Nina Polna",
        "Załączniki:\nPełnomocnik odwołującego:\nadw. Nina Polna",
        "Pełnomocnik zamawiającego:\nPełnomocnik\nNina Polna",
    ],
)
def test_quoted_or_enclosed_signatures_do_not_supply_the_client(block):
    assert counsel(block) == (0, None, None, None)


def test_distant_signed_closing_requires_the_appellants_own_declaration():
    signed = "Wnoszę o uwzględnienie zarzutów.\nZ poważaniem\nradca prawny Nina Polna\nKancelaria Polna\nnp@example.org"
    assert counsel("Jako pełnomocnik Odwołującego składam odwołanie.\nZarzuty\n" + signed) == (
        1,
        "Nina Polna",
        "Kancelaria Polna",
        "np@example.org",
    )
    assert counsel("Pismo pełnomocnika zamawiającego\n" + signed) == (0, None, None, None)


def test_same_surname_is_insufficient_to_take_contacts_from_another_office():
    doc = (
        "Kancelaria Polna\nadw. Olga Polna\nwrong@example.org\nODWOŁANIE\n"
        "Odwołujący: Porcelana S.A.\nZamawiający: Powiat Opolski\nZa Odwołującego:\nadw. Nina Polna"
    )
    assert extract(doc)["Odwolujacy"][0]["pelnomocnik"] == {"imie_nazwisko": "Nina Polna", "nazwa": None, "mail": None}


@pytest.mark.parametrize(
    ("role", "represented"),
    [
        ("Przedstawiciel Odwołującego umocowany pełnomocnictwem procesowym", 1),
        ("Przedstawiciel ustawowy Odwołującego", 0),
        ("Zamawiający napisał:\nZ poważaniem\nPrzedstawiciel Odwołującego umocowany pełnomocnictwem", 0),
        ("Przedstawiciel Zamawiającego umocowany pełnomocnictwem procesowym", 0),
    ],
)
def test_native_signature_page_outside_the_reading_window(tmp_path, role, represented):
    from reportlab.pdfgen.canvas import Canvas

    from evals.variant_pages import polish_font
    from kio2json.pipeline import process_pdf

    path = tmp_path / "filing.pdf"
    pdf = Canvas(str(path))
    for rows in [
        [
            "ODWOŁANIE",
            "Do Prezesa Krajowej Izby Odwoławczej",
            "Odwołujący: Porcelana S.A.",
            "Zamawiający: Powiat Opolski",
        ],
        ["Uzasadnienie", "Odwołujący kwestionuje ocenę oferty."],
        ["Wnioski", "Wnosimy o nakazanie powtórzenia czynności."],
        ["Z poważaniem", role, "Załączniki:", "1. Dokumenty umocowania."],
    ]:
        pdf.setFont(polish_font("Helvetica"), 12)
        for idx, row in enumerate("\n".join(rows).splitlines()):
            pdf.drawString(50, 760 - 20 * idx, row)
        pdf.showPage()
    pdf.save()
    kind, record = process_pdf(path)
    assert kind == "appeal"
    party = record["Odwolujacy"][0]
    assert party["przez-pelnomocnika"] == represented
    assert party["pelnomocnik"] == dict.fromkeys(("imie_nazwisko", "nazwa", "mail"))


def test_explicit_labels_inside_the_signed_contact_block():
    assert counsel(
        "Podpis pełnomocnika Odwołującego:\nImię i nazwisko: Nina Polna\n"
        "Nazwa kancelarii: Radix i Partnerzy\nE-mail pełnomocnika: np@example.org"
    ) == (1, "Nina Polna", "Radix i Partnerzy", "np@example.org")
