from kio2json import receipt_title
from kio2json.pdf_text import WordBox


def word(text, x, y, width=24, height=7):
    return WordBox(1, text, x, y, x + width, y + height)


def test_wrapped_value_discards_small_detached_ink_but_keeps_printed_punctuation():
    boxes = [
        word("Tytuł:", 25, 50),
        word("|", 120, 55, 1, 1),
        word("Usługa", 25, 66),
        word("-", 53, 70, 3, 1),
        word("etap", 60, 66),
        word("B.", 90, 66),
        word("testowy", 25, 78),
        word("i", 325, 78, 1, 1),
        word("Kwota", 25, 100),
        word("23,75", 90, 100),
    ]
    assert receipt_title.reread_title(None, boxes, "| Usługa - etap B. testowy i") == "Usługa - etap B. testowy"


def test_explicit_title_supersedes_debit_description_header():
    boxes = [
        word("Opis", 15, 50),
        word("Kwota", 200, 50),
        word("Przelew", 15, 65),
        word("15,35", 200, 65),
        word(".", 7, 90, 2, 1),
        word("Tytuł.", 15, 90),
        word("Serwis", 45, 90),
        word("Numer", 15, 110),
        word("transakcji", 42, 110),
        word("AZ49", 70, 110),
    ]
    assert receipt_title.reread_title(None, boxes, None) == "Serwis"


def test_repeated_titles_cannot_bind_a_single_transaction():
    boxes = [
        word("Tytuł", 15, 50),
        word("Pierwszy", 50, 50),
        word("Tytuł", 15, 70),
        word("Drugi", 50, 70),
    ]
    assert receipt_title.reread_title(None, boxes, None) is None


def test_long_transcript_is_not_replaced_by_an_incomplete_crop():
    boxes = [word("Tytuł", 15, 50), word("Abonament", 50, 50)]
    assert receipt_title.reread_title(None, boxes, "Abonament półroczny ustalony od września") is None


def test_inline_known_field_ends_the_scanned_title():
    boxes = [
        word("Tytuł:", 20, 35),
        word("Przegląd", 47, 35),
        word("Kwota:", 78, 35),
        word("46,75", 108, 35),
        word("PLN", 140, 35),
    ]
    assert receipt_title.reread_title(None, boxes, None) == "Przegląd"


def test_canonical_scanned_title_strips_its_printed_quote_pair():
    boxes = [word("Tytuł:", 20, 35), word("„Dostawa", 47, 35), word("paczki”", 79, 35)]
    assert receipt_title.reread_title(None, boxes, None) == "Dostawa paczki"


def test_optional_crop_failure_preserves_existing_title(tmp_path):
    boxes = [
        word("Potwierdzenie", 20, 25),
        word("płatności", 130, 29),
        word("Tytuł:", 20, 80),
        word("przegląd", 52, 81),
        word("maszyn", 140, 84),
    ]
    assert receipt_title.reread_title(tmp_path / "unavailable.pdf", boxes, "Przegląd maszyn") is None


def test_multiword_payment_label_can_occupy_one_box():
    boxes = [
        word("Szczegóły płatności", 15, 40, width=80),
        word("Odbiór", 100, 40),
        word("towaru", 132, 40),
    ]
    assert receipt_title.reread_title(None, boxes, None) == "Odbiór towaru"
