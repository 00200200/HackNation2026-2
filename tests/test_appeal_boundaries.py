"""Party sections and sentences in appeals."""

import pytest

from kio2json import appeal


@pytest.mark.parametrize(
    "section", ["Uzasadnienie:", "Uczestnik: Dom Prób", "Interwenient: Inny Zakład", "Dowody:", "UZASADNIENIE"]
)
def test_next_section_closes_party_and_attorney(section):
    text = f"ODWOŁANIE\nOdwołujący: Wrzosik\n{section}\nWnoszę jak na wstępie.\nreprezentowany przez: adw. Olga Letnia\nNIP: 8912345689"
    (party,) = appeal.extract(text)["Odwolujacy"]
    assert (party["nazwa"], party["nip"], party["przez-pelnomocnika"]) == ("Wrzosik", None, 0)
    assert all(v is None for v in party["pelnomocnik"].values())


@pytest.mark.parametrize(
    ("body", "day"),
    [
        ("odrzucenie oferty Rdest sp. z o.o. Odwołanie wniesiono 15.05.2026.", None),
        ("odrzucenie oferty Krokus S.A. Pismo opłacono 01.02.2026.", None),
        ("odrzucenie oferty Dymka sp.j. Skargę złożono 04.02.2026.", None),
        ("odrzucenie oferty na podstawie art. 12 ust. 4 pkt. 7 w dniu 03.06.2026.", "2026-06-03"),
        ("odrzucenie oferty Lilia sp. z o.o. w dniu 04.06.2026.", "2026-06-04"),
        ("odrzucenie oferty. odwołanie złożono 04.06.2026.", None),
        ("odrzucenie oferty Krokus S.A., dokonane dnia 05.06.2026 r.", "2026-06-05"),
        ("odrzucenie oferty bez zawiadomienia; pismo nadano 15.08.2026.", None),
    ],
)
def test_action_sentence(body, day):
    action = appeal.extract("Zarzut nr 1 – " + body)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, day)


def test_empty_procurement_subject_and_reference_end_at_other_fields():
    data = appeal.extract("dotyczy:\nZałącznik: „Dowód nadania”\nnumer postępowania:\nAdres: Dolna")[
        "ZamowieniePubliczne"
    ]
    assert data["numer_postepowania"] is data["tytul"] is None


def test_attorney_name_in_correspondence_address_is_not_the_representative():
    data = appeal.extract(
        "Odwołujący: Wrzosik\nreprezentowany przez:\nadres do korespondencji: Kancelaria adw. Olga Letnia, ul. Dolna 5"
    )
    attorney = data["Odwolujacy"][0]["pelnomocnik"]
    assert attorney["imie_nazwisko"] is None
    assert attorney["nazwa"] == "Kancelaria adw. Olga Letnia"
