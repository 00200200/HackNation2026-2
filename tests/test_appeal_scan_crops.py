"""Each repaired contact character needs support from the printed field."""

from kio2json.appeal_scan_crops import _contact, _disputed_counsel
from kio2json.pdf_text import OCRWord, WordBox


def test_mailbox_dot_and_at_may_come_from_different_reads_of_the_same_box():
    page = "e-mail: i purpuraQpapier.test"
    words = [
        WordBox(1, "i", 30, 10, 32, 18),
        WordBox(1, "purpuraQpapier.test", 34, 10, 80, 18),
    ]

    def read(span, language, deskew):
        assert span == words
        return "i.purpuraQpapier.test" if deskew else "i purpura@papier.test"

    assert _contact("Iga Purpura", page, words, read) == "i.purpura@papier.test"
    assert _contact("Iga Purpura", page, words, lambda *_: "i purpura@papier.test") is None
    assert _contact("Iga Purpura", page, words, lambda *_: "i.purpura@tektura.test") is None
    assert _contact("Celina Purpura", page, words, read) is None


def test_lawyer_name_needs_two_weak_words_and_a_disagreeing_reread():
    firm = "Kancelaria Wzorcowa — radca prawny Anna LIS"
    words = [OCRWord(1, w, 0, 0, 1, 1, 40) for w in firm.split()]

    def disputed(span, language, deskew):
        assert span == words[-2:] and language == "pol"
        return "Alna LAS"

    assert _disputed_counsel(firm, words, disputed)
    assert not _disputed_counsel(firm, words, lambda *_: "Anna Lis")
    assert not _disputed_counsel(firm, words, lambda *_: "Anna\n LIS.")
    assert not _disputed_counsel(firm, words, lambda *_: " | . ")
    assert not _disputed_counsel(firm, words, lambda *_: "")
    words[-1] = OCRWord(*words[-1], confidence=90)
    assert not _disputed_counsel(firm, words, disputed)
