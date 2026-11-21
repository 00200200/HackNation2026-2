"""Invented appeal layouts with role labels, contacts, joint parties and charges."""

import pytest

from kio2json.appeal import extract
from kio2json.classify import classify


def test_joint_purchaser_list_survives_contacts_and_multiline_addresses():
    result = extract(
        "Zamawiający: Port Papierowy, ul. Zmyślona 8\n"
        "telefon: 000 000 000\n"
        "prowadzący postępowanie w imieniu i na rzecz:\n"
        "1. Archiwum Zielonych\nArkuszy, ul. Nowa 7\n"
        "2. Dom Kopert\n04 — 876 Papierowo\n"
        "3) Fabryka Linijek\nkontakt: druk@example.test\n"
        "Odwołujący: Wytwórnia Pieczątek\nODWOŁANIE"
    )
    assert [(p["nazwa"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Port Papierowy", 1),
        ("Archiwum Zielonych Arkuszy", 0),
        ("Dom Kopert", 0),
        ("Fabryka Linijek", 0),
    ]


def test_marked_consortium_leader_keeps_own_registry_and_counsel():
    result = extract(
        "Odwołujący: wykonawcy wspólnie ubiegający się o zamówienie:\n"
        "1. Atramentowa Wieża (członek konsorcjum)\nKRS 0000087654\n"
        "2. Zegar z Papieru z siedzibą w Kolorowie (lider konsorcjum)\nKRS 0000098765\n"
        "Pełnomocnik Odwołującego: Iga Szpulka\nKancelaria Złoty Ołówek\n"
        "e-mail: iga@example.test\nZamawiający: Korbka\ne-mail: korbka@example.test"
    )
    party = result["Odwolujacy"][0]
    assert (party["nazwa"], party["krs"], party["przez-pelnomocnika"]) == ("Zegar z Papieru", "0000098765", 1)
    assert party["pelnomocnik"] == {
        "imie_nazwisko": "Iga Szpulka",
        "nazwa": "Kancelaria Złoty Ołówek",
        "mail": "iga@example.test",
    }


def test_letterhead_date_and_officer_distinct_from_counsel():
    result = extract(
        "— Kolorowo, 11 marca 2032 r.\nWykonawca: Papierowy Wiatr\n"
        "81- 903 Kolorowo\nreprezentowany przez\nIgora Piórko – Prezesa Zarządu\n"
        "Zamawiający: Baszta\nKolorowo, ul. Rulonowa 9\nwww.example.test\nODWOŁANIE"
    )
    assert result["OdwolanieKIO"]["miejscowosc"] == "Kolorowo"
    assert result["OdwolanieKIO"]["data"] == "2032-03-11"
    assert result["Odwolujacy"][0]["nazwa"] == "Papierowy Wiatr"
    assert result["Odwolujacy"][0]["przez-pelnomocnika"] == 0
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Baszta"]


def test_two_columns_use_printed_rows_for_detached_labels(monkeypatch):
    from pathlib import Path

    from kio2json import appeal_layout, pipeline
    from kio2json.pdf_text import WordBox

    rows = [("Zamawiający:", "Fabryka", "Tęczy"), ("Odwołujący:", "Port", "Mgły")]
    boxes = [
        WordBox(1, word, x, y, x + 36, y + 10)
        for y, row in zip((40, 92), rows, strict=True)
        for x, word in zip((65, 200, 244), row, strict=True)
    ]

    reads = []

    def read(path, **options):
        reads.append(path)
        options.get("ocr_pages", []).append(1)
        if (out := options.get("word_boxes")) is not None:
            out.extend(boxes)
        return ["Zamawiający:\nOdwołujący:\nFabryka Tęczy\nPort Mgły\nODWOŁANIE"]

    monkeypatch.setattr(pipeline, "read_pages", read)
    monkeypatch.setattr(appeal_layout, "read_pages", read)
    label, result = pipeline.process_pdf(Path("invented.pdf"))
    assert len(reads) == 1
    assert label == "appeal"
    assert [a["nazwa"] for a in result["Zamawiajacy"]] == ["Fabryka Tęczy"]
    assert result["Odwolujacy"][0]["nazwa"] == "Port Mgły"


@pytest.mark.parametrize("heading", ["ODW0ŁANIE", "O D W O L A N I E"])
def test_damaged_heading_requires_an_appeal_party(heading):
    assert classify([f"Zamawiający: Port\nWykonawca: Kreda\n{heading}"]) == "appeal"
    assert classify([f"Dowód doręczenia\n{heading}"]) is None
    assert classify([f"Wyrok\nZamawiający: Port\nOdwołujący: Kreda\n{heading}"]) is None


def test_challenge_in_prose_takes_first_act_and_its_date():
    result = extract(
        "Kolorowo, 17 czerwca 2032 r.\nODWOŁANIE\n"
        "Odwołujący zarzuca Zamawiającemu:\n"
        "1) naruszenie art. 71 ust. 2 poprzez zaniechanie odrzucenia oferty.\n"
        "2) zmianę treści SWZ w dniu 10 czerwca 2032 r."
    )["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (7, None)


def test_quoted_subject_and_prose_reference():
    result = extract(
        "Dotyczy: zadania pod nazwą „Budowa papierowego mostu”, znak sprawy DM/88/Z.\nOgłoszenie w TED: 907654 — 2032."
    )["ZamowieniePubliczne"]
    assert (result["tytul"], result["numer_postepowania"], result["numer_ted"]) == (
        "Budowa papierowego mostu",
        "DM/88/Z",
        "907654-2032",
    )


def test_registry_details_in_appellants_self_identification():
    result = extract(
        "Odwołujący: Most z Bibuły\nZamawiający: Wiatrak\nODWOŁANIE\n"
        "Most z Bibuły z siedzibą w Kolorowie, wpisany pod numerem KRS 0000047128 "
        "(dalej „Odwołujący”), wnosi odwołanie.\nKRS 0000085421"
    )["Odwolujacy"][0]
    assert result["krs"] == "0000047128"


def test_publication_date_after_allegations_requires_same_challenged_document():
    result = extract(
        "Odwołanie dotyczy treści specyfikacji.\nOdwołujący zarzuca:\n"
        "1. wadliwe sporządzenie specyfikacji.\n2. wybór oferty.\n"
        "Termin wniesienia odwołania:\n"
        "Specyfikacja została opublikowana w dniu 07 lutego 2031 r."
    )["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (4, "2031-02-07")


def test_evidence_of_employment_or_same_day_does_not_imply_counsel():
    party = extract(
        "Odwołujący: Piramida\nZamawiający: Domek\nreprezentowany przez: adw. Ula Zmyślona\n"
        "ODWOŁANIE\nPracownik Odwołującego wnosi odwołanie."
    )["Odwolujacy"][0]
    assert party["przez-pelnomocnika"] == 0


def test_dated_first_charge_takes_precedence_over_different_introductory_act():
    result = extract(
        "Zamawiający w dniu 9 maja 2031 unieważnił postępowanie. "
        "Zarzut nr 1 – odrzucenie oferty. "
        "Zarzut nr 2 – wskazanie wadliwego kryterium."
    )["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (1, None)


def test_date_in_first_numbered_charge():
    result = extract(
        "Odwołujący zarzuca:\n1) odrzucenie oferty z dnia 06.05.2031.\n2) wykluczenie wykonawcy w dniu 10.05.2031."
    )["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (1, "2031-05-06")


@pytest.mark.parametrize(("first", "reason"), [("wybór oferty", 2), ("nie odrzucił oferty", 7)])
def test_inline_second_number_does_not_supply_first_charge(first, reason):
    text = f"Odwołujący zarzuca: 1) {first}. 2) zaniechanie wykluczenia wykonawcy."
    assert extract(text)["OdwolanieKIO"]["czynnosc_powod_id"] == reason


def test_inline_registry_and_other_partys_mandate():
    result = extract(
        "Odwołujący: Pałac Kalki, KRS 0000076194\nZamawiający: Skład Bibuły, NIP 7912036548\n"
        "Reprezentowany na podstawie załączonego pełnomocnictwa.\nODWOŁANIE"
    )
    party = result["Odwolujacy"][0]
    assert (party["nazwa"], party["krs"], party["przez-pelnomocnika"]) == ("Pałac Kalki", "0000076194", 0)
    assert result["Zamawiajacy"][0]["nip"] == "7912036548"


def test_one_ocr_substitution_in_a_role_keeps_the_printed_name():
    result = extract("Zamawiajacy: Rzeka Żetonów\nOdwołujacy: Złota Klamra\nODWOŁANIE")
    assert result["Zamawiajacy"][0]["nazwa"] == "Rzeka Żetonów"
    assert result["Odwolujacy"][0]["nazwa"] == "Złota Klamra"


def test_nearby_heading_with_only_a_body_reference_is_insufficient():
    assert classify(["ODWOŁANIA\nLista pism odwołującego i doręczeń."]) is None


def test_generic_procedural_charge_keeps_its_introductory_dated_act():
    result = extract(
        "Zamawiający w dniu 13 maja 2031 odrzucił ofertę. "
        "Zarzut nr 1 – zaniechanie doprecyzowania wezwania do wyjaśnień."
    )["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (1, "2031-05-13")
