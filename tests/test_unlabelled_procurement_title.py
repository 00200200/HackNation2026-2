import random

import pytest

from evals.variant_pages import render
from kio2json.pipeline import process_pdf

REF = "Numer postępowania: RZ-27/2031"


def read_procurement(tmp_path, block):
    sections = [
        ["Odwołujący:", "Laboratorium Testowe sp. z o.o."],
        ["Zamawiający:", "Gmina Próbna"],
        block,
        ["Zarzuty", "Wnoszę odwołanie do Prezesa Krajowej Izby Odwoławczej."],
    ]
    pdf = tmp_path / "pleading.pdf"
    pdf.write_bytes(render("Odwołanie do Prezesa KIO", sections, "single-column", random.Random(81)))
    kind, record = process_pdf(pdf)
    assert kind == "appeal"
    result = record["ZamowieniePubliczne"]
    assert result["numer_postepowania"] == "RZ-27/2031"
    return result["tytul"]


def test_reads_complete_unlabelled_subject_at_reference(tmp_path):
    assert read_procurement(
        tmp_path, ["Renowacja historycznej elewacji muzeum", "wraz z odtworzeniem detali – etap II", REF]
    ) == ("Renowacja historycznej elewacji muzeum wraz z odtworzeniem detali – etap II")


def test_nominal_subject_belongs_to_the_procurement(tmp_path):
    assert read_procurement(tmp_path, ["Sieć kanalizacyjna przy ulicy Tęczowej", REF]) == (
        "Sieć kanalizacyjna przy ulicy Tęczowej"
    )


@pytest.mark.parametrize(
    "block",
    [
        ["Zakup ekspertyzy na potrzeby wniesienia odwołania", REF],
        ["Koszty postępowania:", "Zakup opinii prawnej", REF],
        ["Koszty postępowania", "Zakup opinii prawnej", REF],
        ["Przykład z innego postępowania:", "Renowacja okien muzeum", REF],
        ["Poprzednio prowadzone postępowanie:", "Remont ogrodzenia szkoły", REF],
        ["Zakup Serwis sp. z o.o.", REF],
        ["Kancelaria Radcy Prawnego", REF],
        ["Wcześniejsze postępowanie:", "Budowa pawilonu wystawowego", REF],
        ["Budowa pawilonu wystawowego", REF, "Dostawa mebli do jadalni", "Znak sprawy: ZW-9/2030"],
    ],
)
def test_abstains_on_legal_costs_owners_and_unrelated_references(tmp_path, block):
    assert read_procurement(tmp_path, block) is None
