"""Invented role cards. Positions are in PDF points, independent of extraction order."""

from pathlib import Path

import pytest

from kio2json import pipeline
from kio2json.appeal_layout import party_inventory
from kio2json.pdf_text import WordBox


def cards(rows, scale=1, page=1):
    boxes = []
    for y, cells in rows:
        for x, cell in cells:
            for token in cell.split():
                end = x + len(token) * 5
                boxes.append(WordBox(page, token, x * scale, y * scale, end * scale, (y + 10) * scale))
                x = end + 3
    return boxes


@pytest.mark.parametrize("scale", [1, 2])
def test_shuffled_columns_wrapping_and_repeated_stationery(scale):
    rows = [
        (20, [(30, "Pełnomocnik: Iga Kruk")]),
        (100, [(30, "Mocodawca:"), (310, "Mocodawca:")]),
        (114, [(30, "Papierowy"), (310, "Atramentowa Sp. z o.o.")]),
        (128, [(30, "Wiatr Sp. z o.o."), (310, "KRS 0000000345")]),
        (142, [(30, "Podpisujący: Ewa Piórko"), (310, "Podpisujący: Iwo Kredka")]),
    ]
    boxes = cards(rows, scale) + cards(rows[:1], scale, page=2)
    blocks = party_inventory(boxes[::-1], {i: (600 * scale, 800 * scale) for i in (1, 2)})
    assert [(b.role, b.lines) for b in blocks] == [
        ("principal", ["Papierowy", "Wiatr Sp. z o.o."]),
        ("principal", ["Atramentowa Sp. z o.o.", "KRS 0000000345"]),
        ("signer", ["Ewa Piórko"]),
        ("signer", ["Iwo Kredka"]),
    ]
    assert [b.parent for b in blocks[2:]] == [b.order for b in blocks[:2]]


def test_normal_entry_appends_a_second_labelled_appointee(monkeypatch):
    page = "PEŁNOMOCNICTWO\nMocodawca: Papierowy Wiatr Sp. z o.o.\nudziela pełnomocnictwa:\nPełnomocnicy:\n1. Iga Piórko\n2. Iwo Kredka"
    boxes = cards([(50 + n * 14, [(35, line)]) for n, line in enumerate(page.splitlines())])

    def read(path, *, word_boxes, page_sizes, **kwargs):
        word_boxes.extend(reversed(boxes))
        page_sizes[1] = 600, 800
        return [page]

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(pipeline, "_grant_signers", lambda *args: None)
    label, record = pipeline.process_pdf(Path("invented.pdf"))
    assert label == "power_of_attorney"
    assert [p["imie_nazwisko"] for p in record["pelnomocnicy"]] == ["Iga Piórko", "Iwo Kredka"]


def test_same_role_columns_keep_signers_with_their_named_principals():
    from kio2json import power_of_attorney
    from kio2json.appeal_layout import read_role_columns

    rows = [
        (50, [(25, "Mocodawca:"), (310, "Mocodawca:")]),
        (65, [(25, "Papierowy Wiatr Sp. z o.o."), (310, "Błękitny Atrament Sp. z o.o.")]),
        (80, [(25, "KRS 0000000123"), (310, "KRS 0000000345")]),
        (95, [(25, "Podpisujący: Iga Piórko"), (310, "Podpisujący: Iwo Kredka")]),
    ]
    page = "\n".join(["PEŁNOMOCNICTWO", *[" ".join(t for _, t in c) for _, c in rows], "Udzielamy pełnomocnictwa."])
    blocks = party_inventory(cards(rows)[::-1], {1: (600, 800)})
    [ordered] = read_role_columns([page], blocks)
    record = power_of_attorney.extract(ordered)
    power_of_attorney.apply_grant_blocks(record, blocks, ordered)
    assert [(p["data"]["nazwa"], p["data"]["krs"], p["podpisujacy"]) for p in record["mocodawca"]] == [
        ("Papierowy Wiatr Sp. z o.o.", "0000000123", [{"imie_nazwisko": "Iga Piórko"}]),
        ("Błękitny Atrament Sp. z o.o.", "0000000345", [{"imie_nazwisko": "Iwo Kredka"}]),
    ]


def test_populated_roster_needs_a_fresh_role_and_an_unambiguous_identity():
    from kio2json import power_of_attorney

    rows = [
        (24, [(25, "PEŁNOMOCNICTWO")]),
        (40, [(25, "Pełnomocnicy:")]),
        (54, [(25, "1. Iga Piórko")]),
        (68, [(25, "2. Iwo Kredka")]),
        (82, [(25, "Adresat:")]),
        (96, [(25, "3. Ula Kartka")]),
        (110, [(25, "Podpisujący: Ada Kalka")]),
    ]
    blocks = party_inventory(cards(rows), {1: (600, 800)})
    record = {"mocodawca": [], "pelnomocnicy": [{"imie_nazwisko": "Iga Piórko", "pesel": None}]}
    power_of_attorney.apply_grant_blocks(record, blocks, "PEŁNOMOCNICTWO")
    assert [p["imie_nazwisko"] for p in record["pelnomocnicy"]] == ["Iga Piórko", "Iwo Kredka"]
    rows.append((153, [(25, "Udzielam pełnomocnictwa:")]))
    for n, pesel in enumerate(["00000000001", "00000000002"]):
        rows.append((170 + n * 30, [(25, "Pełnomocnik: Ewa Piórko")]))
        rows.append((184 + n * 30, [(25, "PESEL " + pesel)]))
    power_of_attorney.apply_grant_blocks(record, party_inventory(cards(rows), {1: (600, 800)}), "PEŁNOMOCNICTWO")
    assert len(record["pelnomocnicy"]) == 2


def test_only_the_appellants_appointment_supplies_a_firm():
    from kio2json import appeal
    from kio2json.appeal_layout import apply_appeal_blocks

    lines = [
        "Odwołujący: Papierowy Wiatr",
        "reprezentowany przez pełnomocnika:",
        "Iga Piórko",
        "Kreda Partners",
        "e-mail: list@example.test",
        "Zamawiający: Dom Kalki",
        "reprezentowany przez pełnomocnika:",
        "Iwo Kredka",
        "Inna Kancelaria",
        "ODWOŁANIE",
    ]
    blocks = party_inventory(cards([(n * 14 + 40, [(20, line)]) for n, line in enumerate(lines)]), {1: (600, 800)})
    record = appeal.extract("\n".join(lines))
    apply_appeal_blocks(record, blocks)
    assert record["Odwolujacy"][0]["pelnomocnik"] == {
        "imie_nazwisko": "Iga Piórko",
        "nazwa": "Kreda Partners",
        "mail": "list@example.test",
    }


@pytest.mark.parametrize(
    "tail",
    [
        ["Strona przeciwna: Dom Papieru", "Pełnomocnicy:", "1. Iwo Kredka", "2. Ewa Kartka"],
        ["Zamawiający: Dom Papieru", "Pełnomocnicy:", "1. Iwo Kredka", "2. Ewa Kartka"],
        ["Pełnomocnicy:", "1. Iwo Kredka", "PESEL: 00000000001", "PESEL: 00000000002"],
        ["Pełnomocnicy:", "1. Iwo Kredka", "PESEL: 00000000001", "2. Ewa Kartka", "PESEL: 00000000001"],
    ],
)
def test_ambiguous_or_opposing_appointee_cards_leave_list_intact(tail):
    from kio2json import power_of_attorney

    rows = cards([(50 + n * 14, [(20, line)]) for n, line in enumerate(["PEŁNOMOCNICTWO", *tail])])
    person = {"imie_nazwisko": "Iga Piórko", "pesel": None}
    record = {"mocodawca": [], "pelnomocnicy": [person.copy()]}
    power_of_attorney.apply_grant_blocks(record, party_inventory(rows, {1: (600, 800)}), "PEŁNOMOCNICTWO")
    assert record["pelnomocnicy"] == [person]


def test_named_signature_moves_to_its_printed_owner():
    from kio2json import power_of_attorney

    lines = [
        "Mocodawca: Papierowy Wiatr Sp. z o.o.",
        "KRS 0000000123",
        "W imieniu Błękitny Atrament Sp. z o.o.",
        "Podpisujący: Iwo Kredka",
        "udziela pełnomocnictwa adw. Iga Kartka",
    ]
    text = "\n".join(lines)
    blocks = party_inventory(cards([(40 + n * 14, [(20, line)]) for n, line in enumerate(lines)]), {1: (600, 800)})
    record = power_of_attorney.extract(text)
    power_of_attorney.apply_grant_blocks(record, blocks, text)
    assert [p["podpisujacy"] for p in record["mocodawca"]] == [[], [{"imie_nazwisko": "Iwo Kredka"}]]
