import pytest

from kio2json.appeal_layout import read_appeal_columns
from kio2json.pdf_text import WordBox


def _words(lines, page=1):
    return [WordBox(page, text, x, y, x + len(text) * 5, y + 10) for x, y, text in lines]


@pytest.mark.parametrize("scanned", [False, True])
def test_staggered_party_and_body_columns_have_independent_reading_order(scanned):
    lines = [
        (40, 10, "Odwołanie"),
        (44, 48, "Zamawiający"),
        (305, 55, "Zarzuty"),
        (44, 64, "Pracownia Jasna S.A."),
        (305, 71, "Brak uzasadnienia wyboru."),
        (44, 80, "NIP 7000000012, REGON"),
        (305, 87, "Dowody"),
        (44, 96, "123456789"),
        (305, 103, "Protokół oceny."),
    ]
    page = "\n".join(line for _, _, line in lines)
    restored, gutters = read_appeal_columns([page], _words(lines), {1: (600, 800)}, [1] if scanned else [])
    assert restored[0].splitlines() == [
        "Odwołanie",
        "Zamawiający",
        "Pracownia Jasna S.A.",
        "NIP 7000000012, REGON 123456789",
        "Zarzuty",
        "Brak uzasadnienia wyboru.",
        "Dowody",
        "Protokół oceny.",
    ]
    assert gutters


def test_row_labels_and_their_values_stay_together():
    rows = [
        (40, 10, "Zamawiający"),
        (305, 10, "Błękitna Spółka S.A."),
        (40, 30, "Numer postępowania:"),
        (305, 30, "AZ/5"),
        (40, 50, "Data"),
        (305, 50, "12.03.2032"),
        (40, 70, "Przedmiot zamówienia:"),
        (305, 70, "Dowody pomiaru"),
    ]
    page = "\n".join(" ".join([rows[i][2], rows[i + 1][2]]) for i in range(0, len(rows), 2))
    restored, gutters = read_appeal_columns([page], _words(rows), {1: (600, 800)}, [])
    assert restored == [page]
    assert not gutters


def test_reading_order_on_second_page_preserves_unrelated_transcript_and_card_ownership():
    from kio2json.appeal_layout import party_inventory

    rows = [
        (295, 10, "Odwołanie do KIO"),
        (42, 42, "Odwołujący:"),
        (310, 42, "Zarzuty"),
        (42, 57, "Warsztat Piaski S.A."),
        (310, 57, "Nie podano kryteriów."),
        (42, 72, "reprezentowany przez"),
        (310, 72, "Dowody"),
        (42, 87, "Anna Jasna"),
        (310, 87, "Opis przedmiotu."),
        (42, 135, "Podpis"),
    ]
    boxes = _words(rows, page=2)
    # OCR can correct a footer independently of its word boxes.
    body = "\n".join(" ".join([rows[i][2], rows[i + 1][2]]) for i in (1, 3, 5, 7))
    pages = ["Okładka", rows[0][2] + "\n" + body + "\nPodpis czytelny"]
    sizes = {2: (600, 800)}
    restored, gutters = read_appeal_columns(pages, boxes, sizes, [2])
    assert restored[0] == pages[0]
    assert restored[1].startswith("Odwołanie do KIO\nOdwołujący:\nWarsztat Piaski S.A.")
    assert restored[1].endswith("Opis przedmiotu.\nPodpis czytelny")
    blocks = party_inventory(boxes, sizes, appeal_cards=True, page_gutters=gutters)
    party = next(b for b in blocks if b.role == "appellant")
    counsel = next(b for b in blocks if b.role == "representation")
    assert party.lines == ["Warsztat Piaski S.A."]
    assert counsel.parent == party.order
    assert counsel.lines == ["Anna Jasna"]
    missing = [pages[0], pages[1].replace("kryteriów.", "uzasadnienia.")]
    fallback, gutters = read_appeal_columns(missing, boxes, sizes, [2])
    assert fallback == missing
    assert not gutters


def test_shared_body_heading_follows_both_party_cards():
    rows = [
        (40, 30, "Odwołujący:"),
        (305, 37, "Zamawiający:"),
        (40, 46, "Pracownia Jasna S.A."),
        (305, 53, "Zakład Prób S.A."),
        (40, 62, "NIP 7000000012"),
        (305, 69, "NIP 7000000023"),
        (40, 86, "Zarzuty"),
        (40, 102, "Nie wskazano podstaw rozstrzygnięcia ani kryteriów oceny wszystkich ofert."),
    ]
    page = "\n".join(line for _, _, line in rows)
    restored, gutters = read_appeal_columns([page], _words(rows), {1: (600, 800)}, [])
    assert gutters
    assert restored[0].splitlines()[-3:] == [rows[5][2], rows[6][2], rows[7][2]]


def test_quoted_representation_in_charges_is_excluded_from_party_inventory():
    from kio2json.appeal_layout import party_inventory

    rows = [
        (40, 30, "Odwołujący:"),
        (305, 30, "Zarzuty"),
        (40, 46, "Pracownia Jasna S.A."),
        (305, 46, "W protokole wymieniono:"),
        (40, 62, "NIP 7000000012"),
        (305, 62, "Pełnomocnik odwołującego:"),
        (40, 78, "REGON 123456789"),
        (305, 78, "adw. Sara Kowalska"),
    ]
    boxes = _words(rows)
    page = "\n".join(" ".join([rows[i][2], rows[i + 1][2]]) for i in range(0, len(rows), 2))
    sizes = {1: (600, 800)}
    _, gutters = read_appeal_columns([page], boxes, sizes, [])
    assert gutters
    blocks = party_inventory(boxes, sizes, appeal_cards=True, page_gutters=gutters)
    assert [block.role for block in blocks] == ["appellant"]


def test_native_first_page_keeps_shared_heading_after_aligned_cards(monkeypatch):
    from pathlib import Path

    from kio2json import pipeline

    rows = [
        (40, 10, "Odwołanie"),
        (40, 30, "Odwołujący:"),
        (305, 30, "Zamawiający:"),
        (40, 46, "Pracownia Jasna S.A."),
        (305, 46, "Zakład Prób S.A."),
        (40, 62, "NIP 7000000012"),
        (305, 62, "NIP 7000000023"),
        (40, 86, "Zarzuty"),
        (40, 102, "Nie wskazano podstaw rozstrzygnięcia ani kryteriów oceny wszystkich ofert."),
    ]
    page = "\n".join([rows[0][2], *[" ".join([rows[i][2], rows[i + 1][2]]) for i in (1, 3, 5)], rows[7][2], rows[8][2]])

    def read(_path, **kwargs):
        kwargs["page_sizes"][1] = (600, 800)
        kwargs["word_boxes"].extend(_words(rows))
        return [page]

    seen = []

    def extract(definition, text, **kwargs):
        seen.append(text)
        return {}

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(pipeline, "extract", extract)
    assert pipeline.process_pdf(Path("appeal.pdf"))[0] == "appeal"
    assert seen[0].index("NIP 7000000023") < seen[0].index("Zarzuty")
