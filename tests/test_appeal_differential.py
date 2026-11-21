"""Compare every routed field with the baseline checkout before accepting intentional differences."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from snapshots.generate_appeal_baseline import extract_page

from kio2json.class_config import load_classes

SNAPSHOTS = Path(__file__).parent / "snapshots"
INPUTS = json.loads((SNAPSHOTS / "appeal_review_inputs.json").read_text(encoding="utf-8"))
BASELINE = json.loads((SNAPSHOTS / "appeal_baseline.json").read_text(encoding="utf-8"))["records"]
DEFINITIONS = load_classes()
# Each row records the input, schema path, baseline value, corrected value and source evidence.
ABSENT = "<absent>"
INTENDED_CHANGES = [
    (
        "r11-R3c",
        "/output/OdwolanieKIO/czynnosc_dzien",
        "2028-04-14",
        None,
        "The date describes delivery of the complaint copy.",
    ),
    (
        "r11-R3d",
        "/output/OdwolanieKIO/czynnosc_dzien",
        "2028-04-16",
        None,
        "The date belongs to submission of the offer.",
    ),
    (
        "r11-Xact",
        "/output/OdwolanieKIO/czynnosc_dzien",
        "2028-03-11",
        None,
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-Xact",
        "/output/OdwolanieKIO/czynnosc_opis",
        "Modyfikacja treści SWZ",
        "Decyzja o odrzuceniu oferty",
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-Xact",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        5,
        1,
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-Xact2",
        "/output/OdwolanieKIO/czynnosc_dzien",
        "2028-03-11",
        None,
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-Xact2",
        "/output/OdwolanieKIO/czynnosc_opis",
        "Decyzja o wykluczeniu wykonawcy",
        "Decyzja o odrzuceniu oferty",
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-Xact2",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        3,
        1,
        "The first charge explicitly challenges an undated rejection. The dated background describes another act.",
    ),
    (
        "r11-R5d",
        "/output/Odwolujacy/0/nazwa",
        "Luneta 2) Interwenient: Firma Drewno",
        "Luneta",
        "The numbered intervenor is a different party from Luneta.",
    ),
    (
        "r11-R3e",
        "/output/OdwolanieKIO/czynnosc_dzien",
        "2028-04-15",
        None,
        "The date belongs to dispatch of a separate request.",
    ),
    (
        "r29-one-column",
        "/output/OdwolanieKIO/czynnosc_dzien",
        None,
        "2034-05-02",
        "The rejection is explicitly dated in the first charge.",
    ),
    (
        "r29-one-column",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Decyzja o odrzuceniu oferty",
        "The rejection is explicitly dated in the first charge.",
    ),
    (
        "r29-one-column",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        1,
        "The rejection is explicitly dated in the first charge.",
    ),
    (
        "r29-two-column",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Zaniechanie odrzucenia oferty",
        "The appeal challenges an omission to reject the offer.",
    ),
    (
        "r29-two-column",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        7,
        "The appeal challenges an omission to reject the offer.",
    ),
    (
        "r29-two-column",
        "/output/Odwolujacy/0/pelnomocnik/imie_nazwisko",
        None,
        "Ada Cekin",
        "The appellant counsel field expressly appoints the named person.",
    ),
    (
        "r29-two-column",
        "/output/Odwolujacy/0/przez-pelnomocnika",
        0,
        1,
        "The appellant counsel field expressly appoints the named person.",
    ),
    (
        "r29-two-column",
        "/output/ZamowieniePubliczne/numer_postepowania",
        None,
        "WP/34/12",
        "The procedure reference is explicitly printed after a valid label.",
    ),
    (
        "r29-two-column",
        "/output/ZamowieniePubliczne/tytul",
        None,
        "Wymiana szklanych półek",
        "The procedure title is printed after its field label or introducing phrase.",
    ),
    (
        "r29-numbered",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Zaniechanie wykluczenia wykonawcy",
        "The appeal challenges an omission to exclude the contractor.",
    ),
    (
        "r29-numbered",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        8,
        "The appeal challenges an omission to exclude the contractor.",
    ),
    (
        "r29-numbered",
        "/output/Odwolujacy/0/nazwa",
        "wykonawcy wspólnie ubiegający się o zamówienie: 1) Splot Lnu (członek konsorcjum) 2) Splot Wełny (lider konsorcjum)",
        "Splot Wełny",
        "The second consortium member is explicitly the leader.",
    ),
    (
        "r29-numbered",
        "/output/Zamawiajacy",
        [{"krs": None, "nazwa": "Dom Mozaiki", "nip": None, "regon": None, "prowadzacy_postepowanie": None}],
        [
            {"krs": None, "nazwa": "Dom Mozaiki", "nip": None, "regon": None, "prowadzacy_postepowanie": 1},
            {"krs": None, "nazwa": "Warsztat Szkliwa", "nip": None, "regon": None, "prowadzacy_postepowanie": 0},
            {"krs": None, "nazwa": "Instytut Pigmentu", "nip": None, "regon": None, "prowadzacy_postepowanie": 0},
        ],
        "The lead purchaser acts for both named, numbered purchasers.",
    ),
    (
        "r29-letterhead",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Ogłoszenie wyboru oferty",
        "The opening explicitly challenges selection of the offer.",
    ),
    (
        "r29-letterhead",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        2,
        "The opening explicitly challenges selection of the offer.",
    ),
    (
        "r29-letterhead",
        "/output/Odwolujacy",
        [],
        [
            {
                "krs": None,
                "nazwa": "Smyk Harfy",
                "nip": None,
                "regon": None,
                "przez-pelnomocnika": 1,
                "pelnomocnik": {"imie_nazwisko": "Ada Smyk", "nazwa": "Kancelaria Srebrna Nuta", "mail": None},
            }
        ],
        "The filing names the appellant, the signature identifies its counsel, and the letterhead names the firm.",
    ),
    (
        "r29-letterhead",
        "/output/Zamawiajacy",
        [],
        [{"krs": None, "nazwa": "Dom Altówki", "nip": None, "regon": None, "prowadzacy_postepowanie": None}],
        "The filing names Dom Altówki as the body conducting the proceeding.",
    ),
    (
        "r29-letterhead",
        "/output/ZamowieniePubliczne/tytul",
        None,
        "Naprawa tłumików",
        "The procedure title is printed after its field label or introducing phrase.",
    ),
    ("r29-form", "/output/OdwolanieKIO/data", None, "2034-05-12", "The form labels this date as the filing date."),
    (
        "r29-form",
        "/output/ZamowieniePubliczne/tytul",
        None,
        "Montaż zegara słonecznego",
        "The procedure title is printed after its field label or introducing phrase.",
    ),
    (
        "r29-payment-deadline",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Decyzja o odrzuceniu oferty",
        "The appeal alleges rejection, with no date linked to that act.",
    ),
    (
        "r29-payment-deadline",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        1,
        "The appeal alleges rejection, with no date linked to that act.",
    ),
    (
        "r29-payment-deadline",
        "/output/Zamawiajacy/0/nazwa",
        "Fabryka Nitek Odwołujący zarzuca odrzucenie oferty. W odrębnej sprawie 6 maja 2034 r. stanowi początkową datę biegu terminu płatności faktury.",
        "Fabryka Nitek",
        "The first allegation begins a new section after the contracting authority name.",
    ),
    (
        "fresh-empty-ref",
        "/output/ZamowieniePubliczne/numer_postepowania",
        None,
        "CM/17",
        "The procedure reference is explicitly printed after a valid label.",
    ),
    (
        "fresh-file-only",
        "/output/ZamowieniePubliczne/numer_postepowania",
        None,
        "MG/31",
        "The procedure reference is explicitly printed after a valid label.",
    ),
    (
        "fresh-plain-title",
        "/output/ZamowieniePubliczne/tytul",
        None,
        "Renowacja wahadeł",
        "The procedure title is printed after its field label or introducing phrase.",
    ),
    (
        "fresh-registered-seat",
        "/output/Odwolujacy/0/nazwa",
        "Warsztat Wahadeł z siedzibą w Minutowie",
        "Warsztat Wahadeł",
        "The registered-seat phrase introduces the address after the company name.",
    ),
    (
        "fresh-filing-form",
        "/output/OdwolanieKIO/data",
        None,
        "2037-05-05",
        "The form labels this date as the filing date.",
    ),
    (
        "fresh-omission",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Zaniechanie wykluczenia wykonawcy",
        "The first charge explicitly alleges an omission to exclude.",
    ),
    (
        "fresh-omission",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        8,
        "The first charge explicitly alleges an omission to exclude.",
    ),
    (
        "fresh-omission",
        "/output/Zamawiajacy/0/nazwa",
        "Dom Sekund Odwołujący zarzuca zaniechanie wykluczenia wykonawcy.",
        "Dom Sekund",
        "The first allegation begins a new section after the contracting authority name.",
    ),
    (
        "fresh-two-charges",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Ogłoszenie wyboru oferty",
        "The first numbered charge challenges selection of the offer.",
    ),
    (
        "fresh-two-charges",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        2,
        "The first numbered charge challenges selection of the offer.",
    ),
    (
        "fresh-notice",
        "/output/OdwolanieKIO/czynnosc_dzien",
        None,
        "2037-05-03",
        "The first charge and the later dated publication both identify the same change to the specification.",
    ),
    (
        "fresh-notice",
        "/output/OdwolanieKIO/czynnosc_opis",
        None,
        "Modyfikacja treści SWZ",
        "The first charge and the later dated publication both identify the same change to the specification.",
    ),
    (
        "fresh-notice",
        "/output/OdwolanieKIO/czynnosc_powod_id",
        None,
        5,
        "The first charge and the later dated publication both identify the same change to the specification.",
    ),
    (
        "fresh-notice",
        "/output/Zamawiajacy/0/nazwa",
        "Dom Sekund Odwołujący zarzuca zmianę treści SWZ. 2) wybór oferty.",
        "Dom Sekund",
        "The first allegation begins a new section after the contracting authority name.",
    ),
    (
        "fresh-explicit-counsel",
        "/output/Odwolujacy/0/pelnomocnik/imie_nazwisko",
        None,
        "Ula Szpula",
        "The appellant counsel field expressly appoints the named person.",
    ),
    (
        "fresh-explicit-counsel",
        "/output/Odwolujacy/0/przez-pelnomocnika",
        0,
        1,
        "The appellant counsel field expressly appoints the named person.",
    ),
    ("fresh-prose-roles", "/class", None, "appeal", "The counsel files an appeal on behalf of the named party."),
    (
        "fresh-prose-roles",
        "/output/OdwolanieKIO",
        "<absent>",
        {"data": None, "czynnosc_dzien": None, "czynnosc_powod_id": None, "czynnosc_opis": None, "miejscowosc": None},
        "The appeal supplies no filing date or challenged act.",
    ),
    (
        "fresh-prose-roles",
        "/output/Odwolujacy",
        "<absent>",
        [
            {
                "krs": None,
                "nazwa": "Kopalni Barw",
                "nip": None,
                "regon": None,
                "przez-pelnomocnika": 1,
                "pelnomocnik": {"imie_nazwisko": None, "nazwa": None, "mail": None},
            }
        ],
        "The filing identifies the represented appellant.",
    ),
    (
        "fresh-prose-roles",
        "/output/Zamawiajacy",
        "<absent>",
        [{"krs": None, "nazwa": "Dom Belki", "nip": None, "regon": None, "prowadzacy_postepowanie": None}],
        "The text explicitly identifies the contracting authority.",
    ),
    (
        "fresh-prose-roles",
        "/output/ZamowieniePubliczne",
        "<absent>",
        {"numer_bzp": None, "numer_postepowania": None, "numer_ted": None, "tytul": None},
        "The appeal supplies no procurement identifiers or title.",
    ),
    (
        "fresh-scanned-heading",
        "/class",
        None,
        "appeal",
        "The spaced OCR heading and the two party roles identify an appeal.",
    ),
    (
        "fresh-scanned-heading",
        "/output/OdwolanieKIO",
        "<absent>",
        {"data": None, "czynnosc_dzien": None, "czynnosc_powod_id": None, "czynnosc_opis": None, "miejscowosc": None},
        "The appeal supplies no filing date or challenged act.",
    ),
    (
        "fresh-scanned-heading",
        "/output/Odwolujacy",
        "<absent>",
        [
            {
                "krs": None,
                "nazwa": "Szpula",
                "nip": None,
                "regon": None,
                "przez-pelnomocnika": 0,
                "pelnomocnik": {"imie_nazwisko": None, "nazwa": None, "mail": None},
            }
        ],
        "The contractor field identifies the appellant.",
    ),
    (
        "fresh-scanned-heading",
        "/output/Zamawiajacy",
        "<absent>",
        [{"krs": None, "nazwa": "Splot", "nip": None, "regon": None, "prowadzacy_postepowanie": None}],
        "The text explicitly identifies the contracting authority.",
    ),
    (
        "fresh-scanned-heading",
        "/output/ZamowieniePubliczne",
        "<absent>",
        {"numer_bzp": None, "numer_postepowania": None, "numer_ted": None, "tytul": None},
        "The appeal supplies no procurement identifiers or title.",
    ),
    (
        "native-task22/role-ascii",
        "/class",
        None,
        "appeal",
        "The filing heading and ASCII appellant label identify an appeal.",
    ),
    (
        "native-task22/role-ascii",
        "/output/OdwolanieKIO",
        "<absent>",
        {"data": None, "czynnosc_dzien": None, "czynnosc_powod_id": None, "czynnosc_opis": None, "miejscowosc": None},
        "The filing gives no date or challenged act.",
    ),
    (
        "native-task22/role-ascii",
        "/output/Odwolujacy",
        "<absent>",
        [
            {
                "krs": None,
                "nazwa": "Imię",
                "nip": None,
                "regon": None,
                "przez-pelnomocnika": 0,
                "pelnomocnik": {"imie_nazwisko": None, "nazwa": None, "mail": None},
            }
        ],
        "The appellant label names Imię.",
    ),
    ("native-task22/role-ascii", "/output/Zamawiajacy", "<absent>", [], "The filing names no authority."),
    (
        "native-task22/role-ascii",
        "/output/ZamowieniePubliczne",
        "<absent>",
        {"numer_bzp": None, "numer_postepowania": None, "numer_ted": None, "tytul": None},
        "The filing supplies no procurement fields.",
    ),
    (
        "native-task22/mail-paren-at",
        "/output/Odwolujacy/0/nazwa",
        "Studio E-mail: anna (at) firma.example",
        "Studio",
        "The appellant name ends before the labelled e-mail contact.",
    ),
    (
        "native-task22/mail-square-at",
        "/output/Odwolujacy/0/nazwa",
        "Studio E-mail: anna [at] firma.example",
        "Studio",
        "The appellant name ends before the labelled e-mail contact.",
    ),
    (
        "native-task22/mail-bare-q",
        "/output/Odwolujacy/0/nazwa",
        "Studio E-mail: annaQfirma.example",
        "Studio",
        "The appellant name ends before the labelled e-mail contact.",
    ),
    (
        "native-task22/mail-crop-q",
        "/output/Odwolujacy/0/nazwa",
        "Studio E-mail: testQx.example",
        "Studio",
        "The appellant name ends before the labelled e-mail contact.",
    ),
]


def differences(base, current, path=""):
    if isinstance(base, dict) and isinstance(current, dict):
        for field in sorted(base.keys() | current.keys()):
            yield from differences(base.get(field, ABSENT), current.get(field, ABSENT), f"{path}/{field}")
    elif isinstance(base, list) and isinstance(current, list) and len(base) == len(current):
        for index, value in enumerate(base):
            yield from differences(value, current[index], f"{path}/{index}")
    elif base != current or type(base) is not type(current):
        yield path, base, current


def test_differential_inventory():
    assert INPUTS.keys() == BASELINE.keys()
    assert all(key in INPUTS and reason.strip() for key, _, _, _, reason in INTENDED_CHANGES)


@pytest.mark.parametrize("key", list(INPUTS))
def test_against_integration_baseline(key):
    actual = list(differences(BASELINE[key], extract_page(INPUTS[key], DEFINITIONS)))
    allowed = [(field, old, new) for case, field, old, new, reason in INTENDED_CHANGES if case == key]
    assert sorted(actual) == sorted(allowed)


def expected_native_result(pages, base):
    """Apply the reviewed field corrections only when both input text and original output match."""
    if len(pages) != 1:
        return base
    result = {"class": base[0], "output": deepcopy(base[1])}
    for key, field, old, new, _ in INTENDED_CHANGES:
        if INPUTS[key] != pages[0]:
            continue
        assert BASELINE[key] == {"class": base[0], "output": base[1]}
        parent = result
        *parts, leaf = field.lstrip("/").split("/")
        for part in parts:
            parent = parent[int(part) if isinstance(parent, list) else part]
        assert parent.get(leaf, ABSENT) == old
        parent[leaf] = new
    return [result["class"], result["output"]]
