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
