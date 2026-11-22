import pytest

from kio2json import bank_transfer
from kio2json.classify import classify
from kio2json.ocr_accounts import account_evidence, normalize_receipt
from kio2json.ocr_extract import extract_bank_transfer
from kio2json.pdf_text import WordBox
from kio2json.receipt_layout import receipt_cell_fields


@pytest.mark.parametrize("ocr", [False, True])
def test_receipt_routes_and_keeps_both_printed_country_codes(ocr):
    text = (
        "Potwierdzenie przelewu\n"
        "Z rachunku: DE89 3704 0044\n0532 0130 00\n"
        "Na rachunek: GB82 WEST 1234 5698 7654 32\n"
        "Kwota: 20,00 PLN\nData operacji: 03.02.2025"
    )
    evidence = account_evidence(text) if ocr else None
    assert classify([text], ocr_accounts=evidence) == "bank_transfer"
    fields = extract_bank_transfer([text], {1} if ocr else {}, accounts=evidence)["przelew_bankowy"]
    assert fields["z_rachunku"] == "DE89370400440532013000"
    assert fields["na_rachunek"] == "GB82WEST12345698765432"


@pytest.mark.parametrize("ocr", [False, True])
def test_detached_cells_preserve_country_codes(ocr):
    table = [
        ("Nadawca", "Odbiorca"),
        ("PL56 4587 0099 1234 5678 0123 4567", "FR14 2004 1010 0505 0001 3M02 606"),
    ]
    boxes = [
        WordBox(1, value, x, 20 * i, x + 5 * len(value), 20 * i + 10)
        for i, row in enumerate(table)
        for x, value in zip((20, 280), row)
    ]
    fields = receipt_cell_fields(boxes, ocr=ocr)
    assert fields["Rachunek nadawcy"] == "PL56458700991234567801234567"
    assert fields["Rachunek odbiorcy"] == "FR1420041010050500013M02606"


def test_checksum_uses_country_of_visible_account_next_to_mask():
    text = (
        "Potwierdzenie przelewu\nZ rachunku: ****\nNa rachunek: NL91 ABNA 0417 1643 00\n"
        "Kwota: 20,00 PLN\nData operacji: 03.02.2025"
    )
    assert classify([text], ocr_accounts=account_evidence(text)) == "bank_transfer"
    assert classify([text], ocr_accounts=account_evidence(text.replace("NL91", "NL81"))) is None


def test_bank_letter_roles_keep_country_code_and_alphanumeric_bban():
    text = (
        "Bank potwierdza, że w dniu 01.03.2025 z rachunku nr GB82 WEST 1234 5698 7654 32 "
        "wykonano przelew w kwocie 10,00 na rachunek nr DE89 3704 0044 0532 0130 00."
    )
    for fields in (bank_transfer.extract(text), extract_bank_transfer([text], {1})):
        assert fields["przelew_bankowy"]["z_rachunku"] == "GB82WEST12345698765432"
        assert fields["przelew_bankowy"]["na_rachunek"] == "DE89370400440532013000"


def test_ocr_can_resolve_one_unknown_foreign_digit_using_its_country_checksum():
    assert normalize_receipt("Na rachunek: GB82 WEST 1234 5698 7654 3?") == "Na rachunek: GB82WEST12345698765432"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("DE89 3 704 00 44   0532 0130 00", "DE89370400440532013000"),
        ("56 45870\n09912345\t67801234567", "56458700991234567801234567"),
        ("FR14 2004 1010 0505 0001 3M02 Bank", None),
        ("DE 56458700991234567801234567", None),
        ("pl 56 4587 0099 1234 5678 0123 4567", "pl56458700991234567801234567"),
        ("gB82 West 1234 5698 7654 32", "gB82West12345698765432"),
    ],
)
def test_receipt_account_handles_pdf_word_and_line_breaks(printed, expected):
    text = "Rachunek nadawcy: " + printed
    assert bank_transfer.extract(text)["przelew_bankowy"]["z_rachunku"] == expected


def test_ocr_substitutes_digit_shaped_glyphs_only_in_the_right_bban():
    from kio2json.ocr_normalize import normalize_ocr

    assert normalize_ocr("DE89 37O4 0044 0532 0130 00") == "DE89370400440532013000"
    assert normalize_ocr("GB82 WEST 1234 5698 7654 32") == "GB82 WEST 1234 5698 7654 32"


@pytest.mark.parametrize(
    "printed",
    ["DE     56458700991234567801234567", "DE89 3704 0044 0532 0130 00 1234"],
)
def test_receipt_does_not_salvage_a_fragment_of_a_malformed_account(printed):
    text = "Na rachunek: " + printed
    assert bank_transfer.extract(text)["przelew_bankowy"]["na_rachunek"] is None
    assert extract_bank_transfer([text], {1})["przelew_bankowy"]["na_rachunek"] is None


@pytest.mark.parametrize("ocr", [False, True])
def test_split_country_and_alphanumeric_groups_are_bound_to_printed_roles(ocr):
    text = (
        "Potwierdzenie przelewu\nZ rachunku: p\u2009L74 1234 5123 4512 3451 2345 1234\n"
        "Na rachunek: F\nr14 2004 1010 0505 0001 3 m 02 606\n"
        "Kwota: 20,00 PLN\nData operacji: 03.02.2025"
    )
    evidence = account_evidence(text) if ocr else None
    assert classify([text], ocr_accounts=evidence) == "bank_transfer"
    fields = extract_bank_transfer([text], {1} if ocr else {}, accounts=evidence)["przelew_bankowy"]
    assert fields["z_rachunku"] == "pL74123451234512345123451234"
    assert fields["na_rachunek"] == "Fr1420041010050500013m02606"


@pytest.mark.parametrize("prefix", ["D E ", "D\nE    ", "Z Z "])
def test_invalid_split_code_cannot_supply_a_domestic_suffix(prefix):
    account = "74123451234512345123451234"
    page = "Na rachunek: " + prefix + account
    assert bank_transfer.extract(page)["przelew_bankowy"]["na_rachunek"] is None
    evidence = account_evidence(page)
    assert evidence.recipient is None
    assert evidence.distinct_numbers == 0


def test_ocr_repairs_keep_both_printed_country_letters():
    from kio2json.ocr_normalize import normalize_ocr

    assert normalize_ocr("d E89 37O4 0044 0532 0130 00") == "dE89370400440532013000"
    assert normalize_receipt("g B82 WEST 1234 5698 7654 3?") == "gB82WEST12345698765432"
