from kio2json.llm import bounded_text


def test_document_budget_counts_utf8_bytes_and_keeps_complete_characters():
    text = "Długie pismo " * 2000
    result = bounded_text(text)
    assert text.startswith(result)
    assert 8190 <= len(result.encode()) <= 8192
