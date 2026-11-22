"""After the shared OCR deadline a reading that is already cached stays usable; only new OCR work stops."""

from pathlib import Path

import pytest

from kio2json import ocr_budget, pipeline

SCAN = Path("invented.pdf")
KEYED = {
    "BASE_URL": "https://offline.invalid/v1",
    "MODEL": "invented",
    "API_KEY": "invented-secret",
    "MODE": "L",
    "ROUTING": "rules",
}


@pytest.fixture
def hybrid(monkeypatch):
    """Hybrid OCR on a fake clock. The first reading routes nothing, the alternate is a power of attorney."""
    now = [100.0]
    reads = []

    def read_pages(path, *, engine, ocr_pages, reread=False, **kwargs):
        if reread:  # as in pdf_text.read_pages: an optional reread needs time left
            ocr_budget.require_remaining_ms()
        reads.append(engine)
        ocr_pages.append(1)
        return ["Informacja"] if engine == "tesseract-dpi" else ["PEŁNOMOCNICTWO\ninvented"]

    monkeypatch.setattr(ocr_budget, "monotonic", lambda: now[0])
    monkeypatch.setattr(pipeline, "read_pages", read_pages)
    monkeypatch.setenv("KIO_OCR_ENGINE", "hybrid")
    return now, reads


def test_an_expired_deadline_still_blocks_a_new_alternate_reading(hybrid):
    now, reads = hybrid
    deadline = ocr_budget.batch_deadline(1)
    now[0] = deadline  # earlier documents of the batch used the shared time
    assert pipeline.process_pdf(SCAN, batch_deadline=deadline) == (None, {})
    assert reads == ["tesseract-dpi"]


def test_recovery_after_the_deadline_still_uses_the_cached_alternate_reading(hybrid, monkeypatch):
    now, reads = hybrid
    for name, value in KEYED.items():
        monkeypatch.setenv("KIO_LLM_" + name, value)
    deadline = ocr_budget.batch_deadline(1)
    rules_extract = pipeline.extract

    def extract(definition, *args, **kwargs):
        if definition.profile.keyed:
            now[0] = deadline  # the shared deadline passes while the model works, then the call fails
            raise RuntimeError("model unavailable")
        return rules_extract(definition, *args, **kwargs)

    monkeypatch.setattr(pipeline, "extract", extract)
    recoveries = []
    label, record = pipeline.process_pdf(SCAN, on_recovery=recoveries.append, batch_deadline=deadline)
    assert label == "power_of_attorney"
    assert "mocodawca" in record
    assert recoveries == ["Used rules after document processing failed."]
    assert reads == ["tesseract-dpi", "rapidocr"]  # the recovery read nothing again
