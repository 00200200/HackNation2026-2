from pathlib import Path

import pytest

from kio2json import receipt_account_crop
from kio2json.pdf_text import WordBox

PRINTED = "06 1987 6543 1234 5678 0000 3456"
MISREAD = PRINTED[:-1] + "3"


def word_boxes(line, top=10):
    return [WordBox(1, w, m * 30, top, m * 30 + 21, top + 8) for m, w in enumerate(line.split())]


def test_correct_only_localized_account_and_retain_printed_format(monkeypatch):
    account = "Rachunek płatnika: PL " + MISREAD
    reference = "Numer referencyjny: " + MISREAD
    pages = [reference + "\n" + account, account]
    boxes = word_boxes(reference) + word_boxes(account, 30)

    def read_crops(path, groups):
        assert len(groups) == 1
        assert all(box.y0 == 30 for box in groups[0])
        return [{PRINTED.replace(" ", ""), MISREAD.replace(" ", "")}]

    monkeypatch.setattr(receipt_account_crop, "_read_crops", read_crops)
    result = receipt_account_crop.recover_account_crops(Path("receipt.pdf"), pages, boxes)
    assert result == [reference + "\nRachunek płatnika: PL " + PRINTED, account]


@pytest.mark.parametrize(
    "readings",
    [
        {"06198765431234567800003553", PRINTED.replace(" ", "")},
        {"012345", MISREAD.replace(" ", "")},
        {"0619876543123456780000355"},
    ],
)
def test_conflicting_or_incomplete_crop_readings_preserve_source(monkeypatch, readings):
    line = "Z rachunku: " + MISREAD
    monkeypatch.setattr(receipt_account_crop, "_read_crops", lambda path, groups: [readings])
    pages = [line]
    assert receipt_account_crop.recover_account_crops(Path("unused"), pages, word_boxes(line)) is pages


@pytest.mark.parametrize(
    "line",
    [
        "Na rachunek: " + PRINTED,
        "Numer referencyjny: " + MISREAD,
        "Na rachunek: ****" + MISREAD,
    ],
)
def test_valid_accounts_unrelated_ids_and_masks_skip_pdf(line):
    pages = [line]
    assert receipt_account_crop.recover_account_crops(Path("no-such.pdf"), pages, word_boxes(line)) is pages


def test_optional_render_failure_preserves_the_original_read(monkeypatch):
    line = "Na rachunek: " + MISREAD

    def unavailable(path, groups):
        raise OSError("simulated renderer failure")

    monkeypatch.setattr(receipt_account_crop, "_read_crops", unavailable)
    pages = [line]
    assert receipt_account_crop.recover_account_crops(Path("receipt.pdf"), pages, word_boxes(line)) is pages
