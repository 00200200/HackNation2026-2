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


def test_punctuation_on_scanned_appeal_heading_requires_filing_evidence():
    from kio2json.classify import classify
    from kio2json.ocr_accounts import account_evidence

    page = "Odwołujący: Studio Papieru\nZamawiający: Gmina Mosty\n* ODWOŁANIE\nDziałając w imieniu spółki, wnoszę odwołanie."
    assert classify([page]) is None
    assert classify([page], ocr_accounts=account_evidence(page)) == "appeal"
    assert classify(["* ODWOŁANIE"], ocr_accounts=account_evidence("")) is None


def test_ocr_heading_inside_a_filing_requires_address_and_both_roles():
    from kio2json.classify import classify
    from kio2json.ocr_accounts import account_evidence

    page = (
        "Do Krajowej Izby Odwoławczej\nOdwołujący: Studio Papieru\nZamawiający: Gmina Mosty\n"
        "ODWQŁANIE\nNa podstawie pełnomocnictwa wnoszę odwołanie."
    )
    assert classify([page], ocr_accounts=account_evidence(page)) == "appeal"
    assert classify([page.replace("Zamawiający:", "Do:")], ocr_accounts=account_evidence(page)) is None
