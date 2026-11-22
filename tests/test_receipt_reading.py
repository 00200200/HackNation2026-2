from unittest.mock import MagicMock

import pytest

from kio2json import pipeline


@pytest.mark.parametrize("heading", ["Zaświadczenie o wykonaniu przelewu", "Historia operacji", "Szczegóły zlecenia"])
def test_bank_document_recovers_only_printed_spacing(heading):
    from kio2json.receipt_reading import restore_receipt_spacing

    page = MagicMock()
    fused = f"Bank Testowy\n{heading}\nObciążono konto14.07.2024 na sumę125,10 EUR."
    spaced = fused.replace("konto14", "konto 14").replace("sumę125", "sumę 125")
    page.extract_text.return_value = spaced
    assert restore_receipt_spacing(page, fused) == spaced
    page.extract_text.return_value = spaced.replace("125,10", "25,10")
    assert restore_receipt_spacing(page, fused) == fused


@pytest.mark.parametrize(
    "page, expected",
    [
        ("Bank Przykładowy\nZaświadczenie o wykonaniu przelewu\nPozdrawiamy", True),
        ("Bank Przykładowy\nZaświadczenie o wykonaniu przelewu\nKwota 125,10 EUR", False),
        ("Bank Przykładowy\nProśba o korektę\nZaświadczenie o wykonaniu przelewu", False),
        ("Bank Przykładowy\nZaświadczenie o wykonaniu przelewu\nStatus: anulowany", False),
        ("Zaświadczenie o wykonaniu przelewu", False),
    ],
)
def test_optional_block_read_needs_an_incomplete_bank_letter(page, expected):
    from kio2json.receipt_reading import missing_letter_body

    assert missing_letter_body(page) is expected


def test_expired_letter_reread_retains_the_primary_reading(monkeypatch, tmp_path):
    from kio2json.ocr_budget import RereadExpired

    page = "Bank Przykładowy\nZaświadczenie o wykonaniu przelewu"
    monkeypatch.setattr(pipeline, "read_letter_body", MagicMock(side_effect=RereadExpired))
    pages, definition, _ = pipeline._read_receipt(
        [page], tmp_path / "input.pdf", [], scanned=True, boxes=[], retry=True
    )
    assert pages == [page] and definition is None
