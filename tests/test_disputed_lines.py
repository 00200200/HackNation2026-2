import re
from unittest.mock import Mock

import pytest
from stdnum.pl import pesel, regon

from kio2json import disputed_lines as lines
from kio2json.pdf_text import WordBox


def row(text, y=10):
    return [WordBox(1, m[0], m.start() * 4, y, m.end() * 4, y + 8) for m in re.finditer(r"\S+", text)]


@pytest.mark.parametrize(
    ("kind", "number"),
    [
        ("NIP", "7312469070"),
        ("REGON", "24681357" + regon.calc_check_digit("24681357")),
        ("PESEL", "8403126498" + pesel.calc_check_digit("8403126498")),
        ("account", "06198765431234567800003456"),
    ],
)
def test_supported_digit_needs_only_one_local_read(kind, number):
    raw = number[:-1] + "?"
    label = "Na rachunek" if kind == "account" else kind
    text = f"{label}: {raw}"
    document = "receipt" if kind == "account" else "grant"
    (cell,) = lines._cells(text, [row(text)], document, set())
    second = Mock(side_effect=AssertionError)
    assert lines._decision(cell, number, second, set()) == number
    second.assert_not_called()


def test_disputed_krs_preserves_leading_zero_and_requires_agreement():
    cell = lines.Cell("KRS", 0, 10, "000O456789", [])
    read = "0000456789"
    assert lines._decision(cell, read, lambda: read, set()) == read
    assert lines._decision(cell, read, lambda: "0000456759", set()) is None
    assert lines._decision(cell, read, Mock(side_effect=OSError), set()) is None


def test_signed_caption_needs_a_complete_independent_read():
    text = "Podpis mocodawcy:\nEwa Ma1ina"
    rows = [row("Podpis mocodawcy:"), row("Ewa Ma1ina", 26)]
    (cell,) = lines._cells(text, rows, "grant", set())
    assert lines._decision(cell, "Ewa Malina", lambda: "Ewa Malina", set()) == "Ewa Malina"
    assert lines._decision(cell, "Ewa Malina", lambda: "Ewa", set()) is None
    assert not list(lines._cells(text, rows, "appeal", set()))


def test_two_line_printed_caption_is_one_confirmed_block():
    text = "Podpis mocodawcy:\nEwa\nMalina"
    rows = [row(s, i * 12) for i, s in enumerate(text.splitlines())]
    (cell,) = lines._cells(text, rows, "grant", set())
    assert cell.block
    assert lines._decision(cell, "Ewa\nMalina", Mock(side_effect=AssertionError), set()) == "Ewa Malina"


@pytest.mark.parametrize(
    "text",
    [
        "REGON: *********",
        "REGON: 24681357 *",
        "REGON: 24681357 - XXXX",
        "Numer: 246813570",
        "KRS: 0000456789",
        "PESEL: 1234",
    ],
)
def test_absent_masked_and_undisputed_cells_skip_render(text):
    assert not list(lines._cells(text, [row(text)], "appeal", set()))


def test_repeated_identical_rows_are_ambiguous():
    text = "REGON: 24681357?"
    assert not list(lines._cells(text + "\n" + text, [row(text), row(text, 28)], "appeal", set()))


@pytest.mark.parametrize("text", ["REGON: 24681357?", "NIP: PL 123456789?"])
def test_label_cannot_license_a_value_in_an_adjacent_column(text):
    label, *value = row(text)
    boxes = [label, *(word._replace(x0=word.x0 + 300, x1=word.x1 + 300) for word in value)]
    assert not list(lines._cells(text, [boxes], "appeal", set()))
