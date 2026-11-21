from kio2json.ocr_normalize import normalize_ocr
from kio2json.power_of_attorney import extract


def test_account_repair_requires_the_checksum():
    digits = "56458700991234567801234567"
    assert normalize_ocr("Rachunek: 56 4587 OO99 1234 5678 0123 4567") == "Rachunek: " + digits
    assert normalize_ocr("PL" + digits.replace("7", "/", 1)) == digits
    for unrelated in ["16 4587 OO99 1234 5678 0123 4567", "2/4/2020", "9" * 26]:
        assert normalize_ocr(unrelated) == unrelated


def test_only_repair_the_company_suffix_in_legal_forms():
    assert normalize_ocr("Przykład sp. z 0.0.  Wartość 0.0.") == "Przykład sp. z o.o.  Wartość 0.0."


def test_only_restore_explicit_address_separators():
    assert normalize_ocr("E-mail: test [at] fikcja.example") == "E-mail: test@fikcja.example"
    assert normalize_ocr("E-mail: test @ fikcja.example") == "E-mail: test@fikcja.example"
    assert normalize_ocr("testQfirma.example, test firma.example") == "testQfirma.example, test firma.example"


def test_signers_without_dots_need_evidence_of_a_signature():
    body = "Mocodawca: Fikcyjne Studio sp. z o.o. udziela pełnomocnictwa adw. Idzie Wymyślnej.\n"
    signature = "\nIga Próbna\nPrezes Zarządu"
    assert extract(body + signature)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Iga Próbna"}]
    assert extract(body + "Adresat: Alicja Fikcyjna")["mocodawca"][0]["podpisujacy"] == []


def test_missing_signature_lines_preserve_explicit_principal_and_skip_unnamed_principals():
    body = "Fikcyjne Studio sp. z o.o. oraz Próbna Firma sp. k. udzielają pełnomocnictwa.\n"
    signature = "W imieniu Próbna Firma sp. k.:\nIga Wymyślna\nDyrektor"
    principals = extract(body + signature)["mocodawca"]
    assert [p["podpisujacy"] for p in principals] == [[], [{"imie_nazwisko": "Iga Wymyślna"}]]
    assert all(not p["podpisujacy"] for p in extract(body + "Iga Wymyślna\nDyrektor")["mocodawca"])


def test_restore_accents_in_headings_and_labels_without_changing_names():
    assert normalize_ocr("ODWOLANIE\nOdwolujacy: Studio Pelno\nPELNOMOCNICTWO PROCESOWE") == (
        "ODWOŁANIE\nOdwołujący: Studio Pelno\nPEŁNOMOCNICTWO PROCESOWE"
    )


def test_email_second_read_must_agree_on_every_other_character():
    from kio2json.ocr_normalize import confirmed_email

    assert confirmed_email("radaQfikcja.example", "rada@fikcja.example") == "rada@fikcja.example"
    assert confirmed_email("rada©fikcja.example", "rada@inna.example") == "rada©fikcja.example"
    assert confirmed_email("radaQfikcja.example", "radę@fikcja.example") == "radaQfikcja.example"
    assert confirmed_email("radaQfikcja.example", "radaQfikcja.example") == "radaQfikcja.example"


def test_scanned_pdf_returns_words_in_pdf_points(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    from kio2json.pdf_text import read_pages

    image = Image.new("RGB", (900, 240), "white")
    ImageDraw.Draw(image).text((60, 50), "ALFA PRZELEW", font=ImageFont.load_default(size=62), fill="black")
    path = tmp_path / "scan.pdf"
    image.save(path, resolution=150)
    words = []
    assert read_pages(path, word_boxes=words) == ["ALFA PRZELEW"]
    assert [(w.page, w.text) for w in words] == [(1, "ALFA"), (1, "PRZELEW")]
    assert 26 < words[0].x0 < 35 and 25 < words[0].y0 < 40
    assert words[0].x1 < words[1].x0 < words[1].x1 < 900 * 72 / 150
    assert words[0].y0 < words[0].y1 < 240 * 72 / 150


def test_native_word_boxes_keep_pdfplumber_coordinates(monkeypatch):
    from unittest.mock import MagicMock

    from kio2json import pdf_text

    page = MagicMock(page_number=2)
    page.extract_text.return_value = "Załącznik"
    page.extract_words.return_value = [{"text": "Załącznik", "x0": 40, "top": 60, "x1": 91, "bottom": 70}]
    document = MagicMock()
    document.__enter__.return_value.pages = [page]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda _: document)
    words = []
    assert pdf_text.read_pages("native.pdf", word_boxes=words) == ["Załącznik"]
    assert words == [(2, "Załącznik", 40, 60, 91, 70)]
    page.to_image.assert_not_called()


def test_damaged_contact_line_cannot_create_another_contracting_authority():
    from kio2json.appeal import extract

    text = "Zamawiający: Gmina Próbna\nul. Pusta 4\nNIP: 9990001122\nsekretariatQfikcja.example\nODWOŁANIE"
    parties = extract(text)["Zamawiajacy"]
    assert [p["nazwa"] for p in parties] == ["Gmina Próbna"]
    assert extract("Zamawiający: przyklad.example")["Zamawiajacy"][0]["nazwa"] == "przyklad.example"


def test_confirmed_payment_with_one_unreadable_account_preserves_the_other_role():
    from kio2json import bank_transfer
    from kio2json.classify import classify

    account = "56458700991234567801234567"
    text = (
        "Potwierdzenie przelewu\nRachunek nadawcy: ****\nRachunek odbiorcy: "
        + account
        + "\nKwota przelewu: 64,50 PLN\nData operacji: 04.06.2025"
    )
    assert classify([text]) == "bank_transfer"
    result = bank_transfer.extract(text)["przelew_bankowy"]
    assert (result["z_rachunku"], result["na_rachunek"]) == (None, account)
    assert classify(["Prosimy o potwierdzenie przelewu" + text.removeprefix("Potwierdzenie przelewu")]) is None
    assert classify(["FAKTURA VAT\n" + text]) is None
