"""A neighbouring OCR page cannot change which rules apply to a native field."""

import pytest

from kio2json.ocr_extract import extract_appeal, extract_bank_transfer, extract_power_of_attorney

GRANT = "Mocodawca: Fiołkowe Studio sp. z o.o. udziela pełnomocnictwa adw. Idzie Scenicznej."
NAME = "Anna Jasna"
ROLE = "Dyrektor"
ACCOUNT = "87432198765432198765432123"
OTHER = "71932700000000000000000027"


@pytest.mark.parametrize(
    ("pages", "ocr_pages", "signers"),
    [
        ([GRANT, f"Podpis\n{NAME}"], {1}, []),
        ([GRANT, f"Podpis\n{NAME}"], {2}, [NAME]),
        ([f"{GRANT}\nPodpis", NAME], {1}, []),
        ([f"{GRANT}\nPodpis", NAME], {2}, []),
        ([f"{GRANT}\n{NAME}", ROLE], {1}, []),
        ([f"{GRANT}\n{NAME}", ROLE], {2}, []),
        ([GRANT, f"Podpis\n{NAME}", f"{ROLE}\nCelina Zimna\n{ROLE}"], {2}, [NAME]),
        ([GRANT, "Podpis", NAME], {2, 3}, [NAME]),
        ([f"{GRANT}\n......................", NAME], {1}, [NAME]),
        ([f"{GRANT}\n......................", NAME], {2}, [NAME]),
        ([f"{GRANT}\nOsoba do kontaktu:\n......................", NAME], {2}, []),
        ([f"{GRANT}\nPełnomocnictwo przyjmuję:", f"Podpis\n{NAME}"], {2}, []),
    ],
)
def test_only_ocr_signature_blocks_use_the_undotted_fallback(pages, ocr_pages, signers):
    records = extract_power_of_attorney(pages, ocr_pages)
    assert records["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": name} for name in signers]


@pytest.mark.parametrize(
    ("ocr_page", "parties"), [(1, ["Gmina Łąkowa", "sekretariatQfikcja.example"]), (2, ["Gmina Łąkowa"])]
)
def test_damaged_mail_is_suppressed_only_when_its_own_line_was_scanned(ocr_page, parties):
    pages = ["Zamawiający: Gmina Łąkowa\nul. Leśna 1\nNIP: 9990001122", "sekretariatQfikcja.example\nODWOŁANIE"]
    assert [party["nazwa"] for party in extract_appeal(pages, {ocr_page})["Zamawiajacy"]] == parties


@pytest.mark.parametrize(("ocr_pages", "sender"), [({2}, OTHER), ({1}, None)])
def test_empty_sender_uses_the_base_or_ocr_rule_of_the_receipt(ocr_pages, sender):
    pages = [
        f"Potwierdzenie przelewu\nNotatka: przelew na konto {OTHER}\nRachunek odbiorcy: {ACCOUNT}\nRachunek nadawcy:",
        "Potwierdzenie wygenerowano elektronicznie.",
    ]
    record = extract_bank_transfer(pages, ocr_pages)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (sender, ACCOUNT)


@pytest.mark.parametrize("ocr_pages", [{1}, {2}])
def test_receipt_with_unlabelled_numbers_can_use_another_page_with_account_fields(ocr_pages):
    pages = [
        f"Potwierdzenie przelewu\n{ACCOUNT}\n{OTHER}\nKwota: 7,44 PLN",
        f"Numer rachunku nadawcy: {OTHER}\nNumer rachunku odbiorcy: {ACCOUNT}",
    ]
    record = extract_bank_transfer(pages, ocr_pages)["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (OTHER, ACCOUNT)


@pytest.mark.parametrize(
    "first", ["Rachunek nadawcy: ****", "Rachunek nadawcy:", f"Nadawca: {OTHER}\nNadawca: {ACCOUNT}"]
)
def test_declared_sender_on_the_ocr_receipt_cannot_be_borrowed_from_a_native_attachment(first):
    pages = [f"{first}\nRachunek odbiorcy: {ACCOUNT}", f"Nadawca: {OTHER}\nPotwierdzenie archiwalne"]
    record = extract_bank_transfer(pages, {1})["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (None, ACCOUNT)


def test_an_extra_page_cannot_give_the_opposite_role_the_printed_account():
    pages = [f"Rachunek odbiorcy: {ACCOUNT}", f"Nadawca: {ACCOUNT}"]
    record = extract_bank_transfer(pages, {1})["przelew_bankowy"]
    assert (record["z_rachunku"], record["na_rachunek"]) == (None, ACCOUNT)
