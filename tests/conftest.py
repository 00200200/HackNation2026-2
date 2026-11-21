import pytest


@pytest.fixture(autouse=True)
def isolate_model_credential(monkeypatch):
    """A developer's shell or .env must not activate paid inference in rules fixtures."""
    monkeypatch.setenv("KIO_LLM_API_KEY", "")
