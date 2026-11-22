"""OCR noise is trimmed off the end of names and titles; a value that is noise throughout becomes null (invented strings)."""

import pytest

from kio2json.ocr_plausibility import trim_appeal, trim_name, trim_title


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (
            "Wodociągi Przykładowe Spółka z ograniczoną odpowiedzialnością K TRAZI NJ OMMO Opole W QXRT BE",
            "Wodociągi Przykładowe Spółka z ograniczoną odpowiedzialnością",
        ),
        ("Testowa Firma S.A. | EBX", "Testowa Firma S.A."),
        ("Testowa Firma S.A. ` EBX", "Testowa Firma S.A."),
        ("Testowa Firma S.A. |EBX", "Testowa Firma S.A."),
        ("Biuro Wzorcowe Nowak sp. z o.o. sp.k. =— Lublin O |]", "Biuro Wzorcowe Nowak sp. z o.o. sp.k."),
    ],
)
def test_noisy_tail_after_legal_form_is_cut(raw, clean):
    assert trim_name(raw) == clean


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Gmina Przykładowo |]", "Gmina Przykładowo"),
        ("Firma Alfa `", "Firma Alfa"),
        ("Firma Alfa ~ ^ =", "Firma Alfa"),
        ("OMEGA S.A. i SIGMA BUD |", "OMEGA S.A. i SIGMA BUD"),
        ("Przedsiębiorstwo AG-BUD Adam Gil |", "Przedsiębiorstwo AG-BUD Adam Gil"),
        ("Kancelaria AG Legal |", "Kancelaria AG Legal"),
        ("Testowa S.A. Centrum Usług Wspólnych |", "Testowa S.A. Centrum Usług Wspólnych"),
        ("Wzorcowa Spółka S.A. W KRAKOWIE |", "Wzorcowa Spółka S.A. W KRAKOWIE"),
        ("WZOR SP. Z O.O. W ŁODZI |", "WZOR SP. Z O.O. W ŁODZI"),
        ("Wzorcowa Energia SA ODDZIAŁ PN WSCH |", "Wzorcowa Energia SA ODDZIAŁ PN WSCH"),
    ],
)
def test_trailing_stray_symbols_are_stripped(raw, clean):
    assert trim_name(raw) == clean


@pytest.mark.parametrize(
    "noise",
    [
        "wę =— MH EMMM Warszawa O |] EGO | Li ZWS |",
        "ąz =— KQ WWWW Lublin I |] OKA | Te XYV |",
        "Kancelaria Prawn — Radca Prawny Kaj EBM",
        "Kancelaria Praw — Radca Prawny Ola QBX |",
        "[| ~~ 12 # 7 <> |",
    ],
)
def test_value_that_is_scanner_noise_throughout_is_nulled(noise):
    assert trim_name(noise) is None


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Testowa Firma S.A. | EBX KQ XYV ZWS", "Testowa Firma S.A."),
        ("PKP |", "PKP"),
    ],
)
def test_value_with_a_recoverable_part_is_trimmed_not_nulled(raw, clean):
    assert trim_name(raw) == clean


@pytest.mark.parametrize("noise", ["| ]", "=== |", " ` "])
def test_name_made_only_of_stray_symbols_has_nothing_left(noise):
    assert trim_name(noise) is None


@pytest.mark.parametrize("noise", ["=== |", " ` ", "||"])
def test_title_made_only_of_stray_symbols_has_nothing_left(noise):
    assert trim_title(noise) is None


@pytest.mark.parametrize(
    "name",
    [
        "Zielona Dolina Spółka z ograniczoną odpowiedzialnością",
        "PKX TRK S.A.",
        "Biuro Wzorcowe Nowak sp. z o.o. sp.k.",
        "Gmina Przykładowo",
        "Fikcyjna Firma S.A. Oddział w Opolu",
        "Wzorcowa Energia SA ODDZIAŁ PN WSCH",
        "Wzorzec SA W LIKWIDACJI",
        "OMEGA S.A. i SIGMA SA",
        "Wzorzec Sp. z o.o. & KAPPA SA",
        "Lider: DELTA S.A., Partner: TAU SC",
        "Kancelaria Radców Prawnych Kowal i Wspólnicy sp.k.",
        "Kancelaria Radcy Prawnego Ewa Przykładowa",
        "Radca Prawny Ewa PRZYKŁADOWA",
        "Kancelaria Radców Prawnych Kowal & Wzór",
        "Kancelaria Adwokacka Adwokat Ewa Wzór – Opole",
        "Kancelaria Radców Prawnych QWZ",
        "OMEGA SP. Z O.O. I SIGMA BUD OPOL",
        "OMEGA S.A. ORAZ SIGMA BUD OPOL",
        "Nowak | Kowalski Kancelaria Prawna",
        "Przedsiębiorstwo AG-BUD Adam Gil",
        "Kancelaria AG Legal",
        "Testowa S.A. Centrum Usług Wspólnych",
        "Testowa S.A. Departament | Zakupów",
        "Wzorcowa Wytwórnia S.A. – ZW Przykładowo",
        "Wzorcowa Spółka SP. Z O.O. W NOWYM SĄCZU",
        "PKXM SP. Z O.O. W ZIELONEJ GÓRZE",
        "ABC S.A. Z SIEDZIBĄ W ŁODZI",
        "WZORCOWA WYTWÓRNIA S.A. ZW PRZYKŁADOWO III",
        "PHU ABC SC JAN NOWAK ADAM KOT",
        "FHU ABC SC ANNA KOWALSKA PIOTR NOWAK MAREK LIS",
        "FHU ABC SC JAN KOWALSKI ADAM KOWALSKI EWA NOWAK",
        "ABC SPÓŁKA CYWILNA ANNA NOWAK PIOTR LIS ADAM KOT MAREK WÓJT",
        "ABC S.A. ZW PN 2",
        "ABC S.A. ZW | PN 2",
        "Wodociągi | Przykładowe Spółka z ograniczoną odpowiedzialnością",
        "Kancelaria Radcy Prawnego Ewa PRZYKŁADOWA",
        "GMINA MIASTO | ŁÓDŹ",
        "URZĄD MIASTA | KRAKOWA",
        "WZOR SP. Z O.O. | W ŁODZI",
        "PRZEDSIĘBIORSTWO ABC SP. Z O.O. | ODDZIAŁ W ŁODZI",
        "Alfa ABC | SA",
        "Kancelaria Radców Prawnych Nowak I Wspólnicy sp.k.",
        "Kancelaria Radcy Prawnego Jan Nowak W Warszawie",
        "Kancelaria Radców Prawnych Anna Nowak Jan Kot SC",
        None,
        "",
    ],
)
def test_clean_names_are_kept(name):
    assert trim_name(name) == name


@pytest.mark.parametrize(
    "title",
    [
        "Dostawa olejów [ON, B7]",
        "Przebudowa linii <15 kV",
        "Usługa #2 odśnieżania",
        "Dostawa 2026/03/04 - 05/2026",
        "Dostawa elementów A=B",
        "Dostawa dla OMEGA S.A. UPS APC 3000",
        "Dostawa sprzętu komputerowego dla szkół w 2026 r. (część 1–3)",
        None,
        "",
    ],
)
def test_titles_keep_brackets_numbers_and_legal_forms(title):
    assert trim_title(title) == title


def test_title_loses_only_trailing_stray_symbols():
    assert trim_title("Dostawa olejów [ON, B7] |") == "Dostawa olejów [ON, B7]"


def _appeal(**fields):
    lawyer = {"imie_nazwisko": "Jan Przykładowy |", "nazwa": "Kancelaria Wzorcowa | ][ =", "mail": "a@b.pl"}
    party = {"nazwa": "Testowa Firma S.A. | EBX", "nip": "1234567890", "pelnomocnik": lawyer}
    return {
        "Odwolujacy": [party],
        "Zamawiajacy": [{"nazwa": "Gmina Przykładowo", "nip": None}],
        "ZamowieniePubliczne": {"tytul": "Budowa drogi gminnej 2026/1 ~", "numer_bzp": "2026/BZP00000001"},
    } | fields


def test_trim_appeal_touches_only_free_text():
    record = _appeal()
    trim_appeal(record)
    party = record["Odwolujacy"][0]
    assert party["nazwa"] == "Testowa Firma S.A."
    assert party["nip"] == "1234567890"
    assert party["pelnomocnik"] == {
        "imie_nazwisko": "Jan Przykładowy",
        "nazwa": "Kancelaria Wzorcowa",
        "mail": "a@b.pl",
    }
    assert record["Zamawiajacy"][0] == {"nazwa": "Gmina Przykładowo", "nip": None}
    assert record["ZamowieniePubliczne"] == {"tytul": "Budowa drogi gminnej 2026/1", "numer_bzp": "2026/BZP00000001"}


def test_trim_appeal_leaves_null_fields_null():
    record = _appeal()
    record["Odwolujacy"][0].update(nazwa=None, pelnomocnik={"imie_nazwisko": None, "nazwa": None, "mail": None})
    record["ZamowieniePubliczne"]["tytul"] = None
    trim_appeal(record)
    assert record["Odwolujacy"][0]["nazwa"] is None
    assert record["Odwolujacy"][0]["pelnomocnik"] == {"imie_nazwisko": None, "nazwa": None, "mail": None}
    assert record["ZamowieniePubliczne"]["tytul"] is None


def test_value_printed_on_a_native_page_is_not_trimmed():
    native = "Odwołujący: Testowa Firma S.A. | EBX\nBudowa drogi gminnej 2026/1 ~\nKancelaria  Wzorcowa | ][ ="
    record = _appeal()
    trim_appeal(record, native)
    party = record["Odwolujacy"][0]
    assert party["nazwa"] == "Testowa Firma S.A. | EBX"
    assert party["pelnomocnik"]["nazwa"] == "Kancelaria Wzorcowa | ][ ="
    assert party["pelnomocnik"]["imie_nazwisko"] == "Jan Przykładowy"
    assert record["ZamowieniePubliczne"]["tytul"] == "Budowa drogi gminnej 2026/1 ~"


def test_trim_appeal_nulls_a_name_that_is_only_noise():
    record = _appeal()
    record["Odwolujacy"][0]["nazwa"] = "wę =— MH EMMM Warszawa O |] EGO | Li ZWS |"
    trim_appeal(record)
    assert record["Odwolujacy"][0]["nazwa"] is None
    assert record["Odwolujacy"][0]["nip"] == "1234567890"


def test_scanned_appeal_trims_ocr_pages_and_leaves_native_pages_alone():
    from kio2json.ocr_extract import extract_scanned_appeal

    pages = [
        "ODWOŁANIE\nOdwołujący: Testowa Firma S.A. | EBX\nul. Dolna 1\nUzasadnienie:",
        "Testowa Firma S.A. wnosi odwołanie.",
    ]
    scanned = extract_scanned_appeal(pages, {1, 2}, None, [])
    native_cover = extract_scanned_appeal(pages, {2}, None, [])
    assert scanned["Odwolujacy"][0]["nazwa"] == "Testowa Firma S.A."
    assert native_cover["Odwolujacy"][0]["nazwa"] == "Testowa Firma S.A. | EBX"
