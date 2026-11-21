import pytest


@pytest.fixture(autouse=True)
def isolate_model_credential(monkeypatch):
    """A developer's shell or .env must not activate paid inference in rules fixtures."""
    monkeypatch.setenv("KIO_LLM_API_KEY", "")


@pytest.fixture
def in_process_cli(monkeypatch):
    """Run injected PDF/model backends in the process that owns the test doubles."""
    from kio2json import __main__ as cli
    from kio2json.batch import read_document

    def read_in_process(pdfs, sources, workers):
        classes = cli.parse_classes(sources)
        return (read_document(pdf, classes) for pdf in pdfs)

    monkeypatch.setattr(cli, "read_batch", read_in_process)
