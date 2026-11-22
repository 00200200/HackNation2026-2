import pytest

from kio2json.classify import classify


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        ("Odwolanie do Prezesa KIO\nWykonawca wnoszacy odwolanie: Biuro Lnu\nZarzuty", "appeal"),
        ("Do Prezesa Krajowej Izby Odwoławczej\nWnosimy odwołanie.\nŻądania", "appeal"),
        ("Upowaznienie\nMocodawca: Studio Baru\nUpowazniam do reprezentowania mnie przed Izba.", "power_of_attorney"),
        (
            "Dowod wykonania transakcji\nIdentyfikator operacji: R4\nKwota: 4,20 PLN\n"
            "Rachunek nadawcy: " + "12-" * 12 + "12\nRachunek odbiorcy: " + "34-" * 12 + "34",
            "bank_transfer",
        ),
        ("Odpowiedz na odwolanie\nODWOŁANIE\nOdwołujący: Sady\nWnoszę odwołanie.", None),
        ("Zgłoszenie przystąpienia do postępowania odwoławczego\nODWOŁANIE\nOdwołujący: Sady", None),
        ("Spis załączników\nOdwołanie do Prezesa KIO\nZarzuty", None),
    ],
)
def test_independent_filing_mandate_and_payment_cues(page, expected):
    assert classify([page]) == expected


def test_appeal_form_roles_and_first_action():
    from kio2json.appeal import extract

    page = (
        "Olsztyn, 09/03/2030\nWykonawca wnoszący odwołanie\nPracownia Futerałów\n"
        "NIP 1231231231\nZamawiający\nMuzeum Lin\nPrzedmiot zamówienia: Renowacja ram\n"
        "Kwestionowana czynność: Odrzucenie oferty\nData zaskarżonej czynności: 01/03/2030"
    )
    data = extract(page)
    assert data["Odwolujacy"][0]["nazwa"] == "Pracownia Futerałów"
    assert data["Zamawiajacy"][0]["nazwa"] == "Muzeum Lin"
    assert data["ZamowieniePubliczne"]["tytul"] == "Renowacja ram"
    filing = data["OdwolanieKIO"]
    assert (filing["data"], filing["czynnosc_powod_id"], filing["czynnosc_dzien"]) == ("2030-03-09", 1, "2030-03-01")


def test_signed_grant_with_separate_appointment_field():
    from kio2json.power_of_attorney import extract

    data = extract(
        "Pełnomocnictwo\nMocodawca\nSpinka sp. z o.o.\nNIP 1231231231\n"
        "Podpis mocodawcy: Ada Most\nUpoważniam do reprezentowania mnie w postępowaniu:\nEwa Grot"
    )
    assert data["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Ada Most"}]
    assert data["pelnomocnicy"] == [{"imie_nazwisko": "Ewa Grot", "pesel": None}]


def test_alternate_payment_value_labels():
    from kio2json.bank_transfer import extract

    data = extract(
        "Kwota płatności: 1 234,50 zł\nData wykonania przelewu: 08/04/2030\n"
        "Tytuł płatności: Serwis wag\nZ rachunku\n" + "12-" * 12 + "12\nNa rachunek\n" + "34-" * 12 + "34"
    )
    assert data["przelew_bankowy"] == {
        "kwota": 1234.50,
        "data_operacji": "2030-04-08",
        "tytul": "Serwis wag",
        "z_rachunku": "12" * 13,
        "na_rachunek": "34" * 13,
        "numer_transakcji": None,
    }


def test_parallel_form_sections_keep_their_own_values(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    from kio2json.pipeline import process_pdf

    path = tmp_path / "form.pdf"
    writer = Canvas(str(path), pagesize=(600, 800))
    left = ["Odwolanie do Prezesa KIO", "Wykonawca wnoszacy odwolanie", "Fabryka Wag", "NIP 1231231231"]
    right = ["Zamawiajacy", "Muzeum Wag", "NIP 3213213213", "Zarzuty"]
    for i, (a, b) in enumerate(zip(left, right, strict=True)):
        writer.drawString(40, 740 - 18 * i, a)
        writer.drawString(320, 740 - 18 * i, b)
    writer.save()
    label, data = process_pdf(path)
    assert label == "appeal"
    assert data["Odwolujacy"][0]["nip"] == "1231231231"
    assert data["Zamawiajacy"][0]["nazwa"] == "Muzeum Wag"


@pytest.mark.parametrize(("amount", "expected"), [("1\u202f250 zł", 1250.0), ("1,250.25 PLN", 1250.25), ("123", None)])
def test_payment_amount_grouping_and_currency(amount, expected):
    from kio2json.bank_transfer import transaction_values

    assert transaction_values("Wartość transakcji: " + amount)[0] == expected


@pytest.mark.parametrize("heading", ["Pełnomocnictwo zostało odwołane", "Pełnomocnictwo wygasło"])
def test_revoked_mandate_is_unrelated(heading):
    assert classify([heading + "\nMocodawca: Studio Mostów\nPełnomocnik: Ada Most"]) is None


@pytest.mark.parametrize("title", ["Tytuł wykonawczy ABC", "Odwołanie do KIO"])
@pytest.mark.parametrize("header", ["", "Potwierdzenie przelewu"])
def test_payment_description_does_not_open_a_parallel_section(title, header):
    from kio2json.appeal_layout import form_columns
    from kio2json.pdf_text import WordBox

    rows = [
        ("Kwota:", "5,20 PLN"),
        ("Data operacji:", "01.02.2032"),
        ("Tytuł:", title),
        ("Numer transakcji:", "12345"),
    ]
    page = "\n".join(f"{label} {value}" for label, value in rows)
    boxes = [
        WordBox(1, text, x, y * 18, x + 6 * len(text), y * 18 + 11)
        for y, pair in enumerate(rows)
        for x, text in zip((30, 310), pair, strict=True)
    ]
    if header:
        boxes.insert(0, WordBox(1, header, 30, -18, 160, -7))
        page = header + "\n" + page
    assert form_columns(page, boxes, 600) == page


def test_later_action_field_cannot_replace_first_charge():
    from kio2json.appeal import extract

    filing = extract(
        "Zarzucam zaniechanie odrzucenia oferty w dniu 2 maja 2033.\n2. Kolejny zarzut\n"
        "Zaskarżona czynność: Unieważnienie postępowania\nData czynności: 05.05.2033"
    )["OdwolanieKIO"]
    assert (filing["czynnosc_dzien"], filing["czynnosc_powod_id"]) == ("2033-05-02", 7)


def test_account_phrase_in_payment_title():
    from kio2json.bank_transfer import extract

    assert (
        extract("Tytuł: Na konto zamawiającego za usługę")["przelew_bankowy"]["tytul"]
        == "Na konto zamawiającego za usługę"
    )


def test_completed_status_corroborates_a_bank_record_without_confirmation_title():
    page = (
        "Dane płatności\nStatus operacji: rozliczona\nKwota: 41,93 PLN\n"
        "Rachunek nadawcy: "
        + "31" * 13
        + "\nRachunek odbiorcy: "
        + "42" * 13
        + "\nNumer transakcji: TX982\nData księgowania: 08.03.2030"
    )
    assert classify([page]) == "bank_transfer"
    assert classify([page.replace("rozliczona", "oczekująca")]) is None
    assert classify(["Faktura pro forma\n" + page]) is None
