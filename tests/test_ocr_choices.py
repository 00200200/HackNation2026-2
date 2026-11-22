import random

import pytest
from stdnum import iban
from stdnum.pl import regon

from kio2json.ocr_accounts import disputed_account_cells
from kio2json.ocr_choices import candidates, shape, valid, verify_cells
from kio2json.ocr_grant_register import disputed_register_cells
from kio2json.pdf_text import WordBox


def synthetic_account(country="PL"):
    rng = random.Random(3481)
    bban = "".join(rng.choices("0123456789", k=24 if country == "PL" else 18))
    return country + iban.calc_check_digits(country + "00" + bban) + bban


def synthetic_regon():
    base = "0" + "".join(random.Random(2207).choices("0123456789", k=7))
    return base + regon.calc_check_digit(base)


def next_digit(digit):
    return str((int(digit) + 1) % 10)


@pytest.mark.parametrize("field,country", [("z_rachunku", "PL"), ("na_rachunek", "DE"), ("regon", "")])
def test_checksum_accepts_only_visually_supported_digit(field, country):
    correct = synthetic_account(country) if country else synthetic_regon()
    wrong = correct[:-1] + next_digit(correct[-1])
    choices = [[(char, 1)] for char in wrong]
    choices[-1].append((correct[-1], 5))
    assert not valid(field, wrong)
    assert [v for v in candidates(field, wrong, choices) if valid(field, v)] == [correct]
    choices[-1][-1] = (correct[-1], 45)
    assert candidates(field, wrong, choices) == (wrong,)
    assert candidates(field, correct, choices) == (correct,)


def test_excess_disputes_excess_beam_and_missing_symbol_abstain():
    correct = synthetic_regon()
    wrong = correct[:-1] + next_digit(correct[-1])
    choices = [[(char, 1)] for char in wrong]
    assert candidates("regon", wrong, choices[:-1]) == (wrong,)
    for i in range(3):
        choices[i].append((next_digit(wrong[i]), 2))
    assert candidates("regon", wrong, choices) == (wrong,)
    choices[2].pop()
    for i in range(2):
        choices[i].append((next_digit(next_digit(wrong[i])), 3))
    assert candidates("regon", wrong, choices) == (wrong,)


def test_prefix_mask_and_checksumless_register_are_immutable():
    correct = synthetic_account("DE")
    wrong = correct[:-1] + next_digit(correct[-1])
    choices = [[(char, 1)] for char in correct]
    choices[0] = [("P", 1)]
    assert candidates("na_rachunek", wrong, choices) == (wrong,)
    assert not shape("na_rachunek", correct[:-4] + "XXXX")
    assert not shape("na_rachunek", correct[:-1])
    krs = "0" * 10
    assert candidates("krs", krs, [[("1", 1)]] * 10) == (krs,)


def test_accounts_on_reversed_columns_remain_bound_to_their_header():
    labels = [("Rachunek", 0), ("odbiorcy:", 46), ("Rachunek", 220), ("nadawcy:", 266)]
    row = [WordBox(1, word, x, 0, x + 40, 10) for word, x in labels]
    sender, recipient = synthetic_account("DE"), synthetic_account()
    row.extend([WordBox(1, recipient, 0, 15, 200, 25), WordBox(1, sender, 220, 15, 420, 25)])
    fields = {"przelew_bankowy": {"na_rachunek": recipient, "z_rachunku": sender}}
    assert {c.field: c.original for c in disputed_account_cells(fields, row)} == {
        "na_rachunek": recipient,
        "z_rachunku": sender,
    }


@pytest.mark.parametrize("mask", ["****", "12******1234", "12 **** 1234"])
@pytest.mark.parametrize("label", [["Rachunek", "płatnika:"], ["1.", "Rachunek", "nadawcy:"]])
def test_conflicting_mask_and_full_number_cannot_restore_a_null_sender(mask, label):
    account = synthetic_account()[2:]
    rows = [[*label, *mask.split()], ["Z", "rachunku:", account]]
    boxes = [
        WordBox(1, word, i * 48, y * 18, i * 48 + 43, y * 18 + 11)
        for y, row in enumerate(rows)
        for i, word in enumerate(row)
    ]
    fields = {"przelew_bankowy": {"na_rachunek": None, "z_rachunku": None}}
    assert disputed_account_cells(fields, boxes) == []


def test_register_crop_belongs_to_its_printed_party():
    number = synthetic_regon()
    record = {"mocodawca": [{"data": {"nazwa": "Example", "regon": number}}]}
    row = [WordBox(2, word, i * 60, 20, i * 60 + 55, 30) for i, word in enumerate(["Appendix", "REGON:", number])]
    assert disputed_register_cells(record, row) == []
    row[0] = row[0]._replace(text="Example")
    [cell] = disputed_register_cells(record, row)
    assert cell.parent is record["mocodawca"][0]["data"]
    for i in (1, 2):
        row[i] = row[i]._replace(x0=row[i].x0 + 350, x1=row[i].x1 + 350)
    assert disputed_register_cells(record, row) == []


def test_expired_shared_budget_skips_even_localization(monkeypatch):
    monkeypatch.setattr("kio2json.ocr_choices.remaining_ms", lambda limit: 0)
    verify_cells(None, lambda *_: pytest.fail("expired"), {}, [])
