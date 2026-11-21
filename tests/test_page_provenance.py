"""The same receipt can be printed, scanned, or followed by a scanned attachment."""

from pathlib import Path

import pytest

from kio2json import pipeline

NUMBER = "87432198765432198765432123"
MASKED_RECEIPT = (
    f"Potwierdzenie przelewu\nRachunek nadawcy: ****\nRachunek odbiorcy: {NUMBER}\n"
    "Kwota przelewu: 17,25 PLN\nData operacji: 03.04.2025"
)


@pytest.mark.parametrize("source_pages, expected", [([], None), ([2], None), ([1], "bank_transfer")])
def test_only_recognized_account_fields_enable_masked_routing(monkeypatch, source_pages, expected):
    def read_pages(path, *, ocr_pages, **kwargs):
        ocr_pages.extend(source_pages)
        return [MASKED_RECEIPT, "Informacja dodatkowa"]

    monkeypatch.setattr(pipeline, "read_pages", read_pages)
    label, record = pipeline.process_pdf(Path("document.pdf"))
    assert label == expected
    if expected:
        transfer = record["przelew_bankowy"]
        assert (transfer["z_rachunku"], transfer["na_rachunek"]) == (None, NUMBER)
    else:
        assert record == {}
