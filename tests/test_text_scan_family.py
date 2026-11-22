"""A text layer in the scan-set wording gets the readers that were written for the 30 organizer scans (#101).

The documents in tests/fixtures/scan_family were re-typed from the page images of organizer scans (the same
documents as the scans, now with a text layer). The two receipts are the OCR text of scans 0003 and 0005 used as a
text layer; they stand in for text receipts in the same layouts.
"""

import copy
from pathlib import Path

import pytest
from snapshots.generate_native import write_native_pdf

from evals.metrics import compare, load_reference
from kio2json import appeal, ocr_extract
from kio2json.appeal_scan_parties import apply_text_parties, sole_trader_name
from kio2json.ocr_accounts import normalize_receipt, repair_receipt_layout
from kio2json.pdf_text import join_pages
from kio2json.pipeline import process_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "scan_family"
SCANS = Path(__file__).parents[1] / "data" / "uzp" / "dane" / "skany"

PAGE_LINES = 58


def write_text_pdf(path: Path, text: str) -> None:
    """A text-layer PDF: a form-feed line starts a new page, and so do 58 lines without one."""
    pages = [[]]
    for line in text.rstrip("\n").split("\n"):
        if line == "\f" or len(pages[-1]) >= PAGE_LINES:
            pages.append([])
        if line != "\f":
            pages[-1].append(line)
    write_native_pdf(path, ["\n".join(lines) for lines in pages], size=(842, 1000))


CASES = [
    ("appeal_0001", "appeal", "odwolania"),
    ("appeal_0004", "appeal", "odwolania"),
    ("appeal_0007", "appeal", "odwolania"),
    ("appeal_0009", "appeal", "odwolania"),
    ("appeal_0010", "appeal", "odwolania"),
    ("poa_0003", "power_of_attorney", "pelnomocnictwa"),
    ("poa_0004", "power_of_attorney", "pelnomocnictwa"),
    ("poa_0005", "power_of_attorney", "pelnomocnictwa"),
    ("poa_0007", "power_of_attorney", "pelnomocnictwa"),
    ("poa_0009", "power_of_attorney", "pelnomocnictwa"),
    ("poa_0010", "power_of_attorney", "pelnomocnictwa"),
    ("receipt_0003", "bank_transfer", "potwierdzenia"),
    ("receipt_0005", "bank_transfer", "potwierdzenia"),
]


def read_fixture(tmp_path, name):
    pdf = tmp_path / f"{name}.pdf"
    write_text_pdf(pdf, (FIXTURES / f"{name}.txt").read_text(encoding="utf-8"))
    return process_pdf(pdf)


# The text reader names a sole-trader grantor by its firm, as the four training references do. The organizer's
# reference for scan 0010 leaves that name null, and the scan reader abstains on it (check_ocr_trade_names).
KNOWN_DIFFERENCES = {"poa_0010": {"mocodawca[].data.nazwa"}}


@pytest.mark.parametrize(("name", "label", "folder"), CASES)
def test_text_pdf_matches_the_organizer_reference(tmp_path, name, label, folder):
    number = name.rsplit("_", 1)[1]
    kind, record = read_fixture(tmp_path, name)
    by_field = {}
    compare(record, load_reference(SCANS / folder / number / f"{number}.json"), by_field=by_field)
    assert kind == label
    assert {path for path, count in by_field.items() if count.fp or count.fn} == KNOWN_DIFFERENCES.get(name, set())


def test_text_appeal_gets_the_action_date_its_text_reader_leaves_empty():
    pages = [
        "Wnosze odwolanie wobec:\n1. zaniechania odrzucenia oferty konkurenta, o czym spolke poinformowano w dniu 9 grudnia 2031 r."
    ]
    record = appeal.extract(join_pages(pages))
    assert record["OdwolanieKIO"]["czynnosc_dzien"] is None
    ocr_extract.complete_text_appeal(record, pages)
    assert (record["OdwolanieKIO"]["czynnosc_dzien"], record["OdwolanieKIO"]["czynnosc_powod_id"]) == ("2031-12-09", 7)


def test_text_appeal_keeps_an_action_date_its_text_reader_found(monkeypatch):
    pages = ["Zarzut nr 1 – odrzucenie oferty Lilia sp. z o.o. w dniu 04.06.2026."]
    record = appeal.extract(join_pages(pages))
    assert record["OdwolanieKIO"]["czynnosc_dzien"] == "2026-06-04"
    monkeypatch.setattr(ocr_extract, "apply_action", lambda *args: pytest.fail("the scan reader replaced a text date"))
    before = copy.deepcopy(record)
    ocr_extract.complete_text_appeal(record, pages)
    assert record == before


OPENING = "Działając w imieniu Odwołującego wnoszę odwołanie wobec:"
ACT = "1. zaniechania odrzucenia oferty konkurenta, o czym spółkę poinformowano w dniu 9 grudnia 2031 r."


@pytest.mark.parametrize(
    ("dateline", "read", "kept"),
    [
        # A labelled filing date alone: the date stays, and the place of the later line is new.
        (
            ["Data złożenia odwołania: 05.04.2026", OPENING, "Kraków, 07.04.2026"],
            ("2026-04-05", None),
            ("2026-04-05", "Kraków"),
        ),
        # Both read by the text reader: a line that only the scan reader can parse replaces neither.
        (
            ["*Kraków, 07.04.2026*", "Warszawa, 05.04.2026", OPENING],
            ("2026-04-05", "Warszawa"),
            ("2026-04-05", "Warszawa"),
        ),
    ],
)
def test_text_appeal_keeps_a_dateline_the_text_reader_found(dateline, read, kept):
    # The scan reader's header rule is written for OCR lines: it takes the first line it can parse.
    pages = ["\n".join([*dateline, ACT])]
    record = appeal.extract(join_pages(pages))
    action = record["OdwolanieKIO"]
    assert (action["data"], action["miejscowosc"]) == read
    ocr_extract.complete_text_appeal(record, pages)
    action = record["OdwolanieKIO"]
    assert (action["data"], action["miejscowosc"], action["czynnosc_dzien"]) == (*kept, "2031-12-09")


@pytest.mark.parametrize(
    ("printed", "registered"),
    [
        (
            "Paweł Brzozowski prowadzący działalność gospodarczą pod firmą Paweł Brzozowski Asterion Usługi Techniczne",
            "Paweł Brzozowski Asterion Usługi Techniczne",
        ),
        # The owner is not part of the firm name, so the printed text stays.
        (
            "Jan Nowak prowadzący działalność gospodarczą pod firmą Inna Firma",
            "Jan Nowak prowadzący działalność gospodarczą pod firmą Inna Firma",
        ),
        ("Kancelaria Adwokacka Spółka z ograniczoną odpowiedzialnością",) * 2,
    ],
)
def test_sole_trader_is_named_by_the_registered_firm(printed, registered):
    assert sole_trader_name(printed) == registered


COVER = [
    "Zamawiający: Zamawiający wspólnie udzielający zamówienia:",
    "1) Zarząd Dróg Powiatowych w Brzozowcu",
    "ul. Polna 103/20",
    "– Zamawiający prowadzący postępowanie",
    "2) Zakład Gospodarki Komunalnej w Zielonkowie",
    "ul. Szkolna 39A",
]
AUTHORITIES = ["Zarząd Dróg Powiatowych w Brzozowcu", "Zakład Gospodarki Komunalnej w Zielonkowie"]


def authorities(*flags, names=AUTHORITIES):
    return {
        "Odwolujacy": [],
        "Zamawiajacy": [
            {"nazwa": name, "krs": None, "nip": None, "regon": None, "prowadzacy_postepowanie": flag}
            for name, flag in zip(names, flags, strict=False)
        ],
    }


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ((0, 0), [1, 0]),  # the caption under the first authority marks it as the lead
        ((0, 1), [0, 1]),  # a lead the text reader already found is not overruled
        ((None,), [None]),  # a single authority has no lead flag
    ],
)
def test_caption_under_a_numbered_authority_marks_the_lead(flags, expected):
    record = authorities(*flags)
    apply_text_parties(record, ["\n".join(COVER)])
    assert [a["prowadzacy_postepowanie"] for a in record["Zamawiajacy"]] == expected


@pytest.mark.parametrize(
    ("cover", "names"),
    [
        # Reached from both unnumbered entries, the caption is attached to neither.
        (
            [
                "Zamawiający:",
                "Gmina Alfa, ul. Polna 1",
                "Gmina Beta, ul. Szkolna 2",
                "– Zamawiający prowadzący postępowanie",
            ],
            ["Gmina Alfa", "Gmina Beta"],
        ),
        # Body text after the cover can use the same words.
        (
            [
                "Zamawiający:",
                f"1) {AUTHORITIES[0]}",
                f"2) {AUTHORITIES[1]}",
                "Działając w imieniu Odwołującego wnoszę odwołanie.",
                "Zamawiający prowadzący postępowanie nie wezwał Odwołującego do uzupełnienia dokumentów.",
            ],
            AUTHORITIES,
        ),
        # A sentence that only contains the words is not a caption, even when no stop line precedes it.
        (
            [
                "Zamawiający:",
                f"1) {AUTHORITIES[0]}",
                f"2) {AUTHORITIES[1]}",
                "Na podstawie art. 505 ust. 1 Pzp wnoszę odwołanie.",
                "Zamawiający prowadzący postępowanie nie wezwał Odwołującego do uzupełnienia dokumentów.",
            ],
            AUTHORITIES,
        ),
    ],
)
def test_caption_that_belongs_to_no_single_authority_names_no_lead(cover, names):
    record = authorities(0, 0, names=names)
    apply_text_parties(record, ["\n".join(cover)])
    assert [a["prowadzacy_postepowanie"] for a in record["Zamawiajacy"]] == [0, 0]


@pytest.mark.parametrize("caption", ["- Zamawiający prowadzący postępowanie", "(Zamawiający prowadzący postępowanie)"])
def test_caption_is_found_whatever_dash_or_bracket_opens_the_line(caption):
    record = authorities(0, 0)
    apply_text_parties(record, ["\n".join(COVER).replace("– Zamawiający prowadzący postępowanie", caption)])
    assert [a["prowadzacy_postepowanie"] for a in record["Zamawiajacy"]] == [1, 0]


def test_caption_is_found_under_a_name_that_opens_with_a_quotation_mark():
    # The cover lines lose a leading quotation mark; the name the text reader keeps it.
    names = ["„Alfa” Sp. z o.o.", "Gmina Beta"]
    cover = ["Zamawiający:", names[0], "– Zamawiający prowadzący postępowanie", "Zamawiający:", names[1]]
    record = authorities(0, 0, names=names)
    apply_text_parties(record, ["\n".join(cover)])
    assert [a["prowadzacy_postepowanie"] for a in record["Zamawiajacy"]] == [1, 0]


def test_grant_readers_run_only_when_no_later_page_grants(monkeypatch):
    calls = []
    for name in ("read_declaration", "complete_represented_company"):
        monkeypatch.setattr(ocr_extract, name, lambda page, record, name=name: calls.append(name))
    monkeypatch.setattr(
        ocr_extract.ocr_signatures, "confirmed_scan_signer", lambda page, record: calls.append("signer")
    )
    ocr_extract.read_grant_declaration(["Pełnomocnictwo", "Druga strona"], {})
    assert calls == ["read_declaration", "complete_represented_company", "signer"]
    calls.clear()
    ocr_extract.read_grant_declaration(["Pełnomocnictwo", "Mocodawca udziela pełnomocnictwa"], {})
    assert calls == []


def test_layout_repairs_leave_an_account_as_printed():
    text = "Rachunek nadawcy: 12 3456 7890 1234 5678 9012 3456\n"
    assert repair_receipt_layout(text) == text
    assert normalize_receipt(text) == "Rachunek nadawcy: ?\n"


def test_text_receipt_keeps_a_printed_account_that_fails_the_checksum(tmp_path):
    # A guard for the split: only scans may have a printed account replaced by its checksum-valid reading.
    original = (FIXTURES / "receipt_0003.txt").read_text(encoding="utf-8")
    altered = original.replace("34 1240 1111 0246 3566 1382 2453", "34 1240 1111 0246 3566 1382 2454")
    assert altered != original
    path = tmp_path / "receipt.pdf"
    write_text_pdf(path, altered)
    kind, record = process_pdf(path)
    assert kind == "bank_transfer"
    assert record["przelew_bankowy"]["z_rachunku"] == "34124011110246356613822454"
