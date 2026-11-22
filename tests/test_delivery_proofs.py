"""Matched transmission records and author messages in the same forms."""

import pytest

from kio2json.classify import classify

FORM = "Pismo ogólne do podmiotu publicznego\nAdresat: Prezes KIO\nIdentyfikator pisma: Q/2033/71"
APPEAL = "ODWOŁANIE\nOdwołujący: Studio Półki\nWnosimy odwołanie od wyboru oferty."
GRANT = "PEŁNOMOCNICTWO\nUdzielam pełnomocnictwa do reprezentowania mnie przed Izbą."
PAYMENT = (
    "Potwierdzenie przelewu\nKwota: 182,63 PLN\nData księgowania: 07.05.2033\n"
    "Rachunek nadawcy: " + "13" * 13 + "\nRachunek odbiorcy: " + "64" * 13
)


@pytest.mark.parametrize(
    "heading,fields",
    [
        ("Urzędowe poświadczenie przedłożenia", "Identyfikator dokumentu: A9\nZałączniki"),
        ("Dowód wysłania", "Adres do doręczeń elektronicznych: AE:PL-8\nNazwa załącznika"),
        ("Dowód otrzymania", "Identyfikator przesyłki: Z5\nWykaz plików"),
        ("Raport z weryfikacji podpisu elektronicznego", "Wynik weryfikacji: poprawny\nNazwa dokumentu"),
        (FORM, "Załączniki"),
    ],
)
def test_attachment_title_in_transport_record(heading, fields):
    assert classify([f"Operator usługi\n{heading}\n{fields}\nPEŁNOMOCNICTWO\npodpis.xades"]) is None


@pytest.mark.parametrize(
    "declaration,label", [(APPEAL, "appeal"), (GRANT, "power_of_attorney"), (PAYMENT, "bank_transfer")]
)
def test_form_body_owns_route_even_if_attachment_has_other_title(declaration, label):
    page = FORM + "\nZałączniki:\nPEŁNOMOCNICTWO\nTreść pisma:\n" + declaration
    assert classify([page]) == label


def test_quoted_filing_and_subject_do_not_make_a_document_operative():
    page = FORM + "\nTemat: Wnosimy odwołanie od wyboru oferty\nOdwołujący: Studio Półki\nODWOŁANIE"
    assert classify([page]) is None
    assert classify([FORM + "\nPodgląd załącznika:\n" + GRANT]) is None
    assert classify([FORM + "\nZałączniki:\n" + PAYMENT]) is None


def test_genuine_filing_can_mention_delivery_proof_or_have_transmission_fields_first():
    assert classify([GRANT + "\nZałączniki:\nDowód otrzymania\nIdentyfikator przesyłki: 82"]) == "power_of_attorney"
    assert classify([FORM + "\n" + APPEAL]) == "appeal"


@pytest.mark.parametrize(
    "text",
    ["Nie udzielam pełnomocnictwa.", "Nie składamy odwołania.", "Nazwa dokumentu: „Wnoszę odwołanie”"],
)
def test_form_requires_affirmative_declaration(text):
    assert classify([FORM + "\nPEŁNOMOCNICTWO\n" + text]) is None


@pytest.mark.parametrize(
    "body,label",
    [
        ("Oświadczam, że wnoszę odwołanie od wyboru oferty.", "appeal"),
        ("Oświadczam, że udzielam pełnomocnictwa do reprezentowania mnie.", "power_of_attorney"),
        ("Informuję, że wykonawca wnosi odwołanie. Przekazuję jego pismo.", None),
        ("Temat:\nWnoszę odwołanie\nTreść pisma: Przesyłam plik w załączeniu.", None),
        ("Treść pisma: Przekazuję pismo, w którym wykonawca wnosi odwołanie od wyboru.", None),
        ("PEŁNOMOCNICTWO\nUmocowuję adwokata do reprezentowania mnie przed Izbą.", "power_of_attorney"),
        ("ODWOŁANIE\nOdwołujący: Studio Wagi\nWnoszę niniejszym odwołanie od wyboru.", "appeal"),
    ],
)
def test_message_assertions_and_subject_continuations(body, label):
    assert classify([FORM + "\n" + body]) == label
