from kio2json import appeal
from kio2json.appeal_scan_procurement import apply_procurement


def procurement(*pages, scanned=(1,)):
    record = {"ZamowieniePubliczne": appeal._procurement("\n".join(pages)), "OdwolanieKIO": {}}
    apply_procurement(record, list(pages), scanned)
    return record["ZamowieniePubliczne"]


def test_notice_and_reference_with_scan_gaps():
    page = (
        "Dotyczy: postępowania pn. .. Zaopatrzenie pracowni ”, nr referencyjny: BB/ 15/2031, "
        "ogłoszenie w Dzienniku Urzędowym UE nr 2031/8S\n022-654321"
    )
    fields = procurement(page)
    assert fields["numer_ted"] == "654321-2031"
    assert fields["numer_postepowania"] == "BB/15/2031"
    assert fields["tytul"] == "Zaopatrzenie pracowni"
    assert procurement("Identyfikator magazynu 2031/8S 022-654321")["numer_ted"] is None


def test_mismatched_quotes_and_lexical_repair_in_scan_title():
    page = (
        'Postępowania pn. „Wyposażenie biurówej części pawilonu", numer sprawy: BA/31. '
        "W imieniu „Wykonawcy” składam odwołanie."
    )
    assert procurement(page)["tytul"] == "Wyposażenie biurowej części pawilonu"
    assert procurement(page, scanned=()) == appeal._procurement(page)


def test_native_title_and_reference_survive_scanned_enclosure():
    native = "Dotyczy: zamówienia pn. „Skrzynie do archiwum”, nr referencyjny: AA/31."
    enclosure = "zamówienia pn. ,,Naprawa sprzętu”, nr referencyjny: BB/ 33"
    result = procurement(native, enclosure, scanned=(2,))
    assert result["tytul"] == "Skrzynie do archiwum"
    assert result["numer_postepowania"] == "AA/31"


def test_title_boundaries_before_publication_or_later_role_definitions():
    assert (
        procurement("w postępowaniu na: Remont ośrodka w ramach zadania „Sala spotkań”, ogłoszonym w dniu 4 maja.")[
            "tytul"
        ]
        == "Remont ośrodka w ramach zadania „Sala spotkań”"
    )
    assert (
        procurement(
            "Dotyczy: Przebudowa rynku\ni pawilonów handlowych,\nnr ogłoszenia o zamówieniu: 31/31\n"
            "Ocena ofert pn. „jakość”"
        )["tytul"]
        == "Przebudowa rynku i pawilonów handlowych"
    )
    assert (
        procurement("Dalej: „Zamawiający”, którego przedmiotem jest „Wyposażenie laboratorium” — dalej: „Zadanie”")[
            "tytul"
        ]
        == "Wyposażenie laboratorium"
    )


def test_named_form_subject_and_project_complement():
    assert (
        procurement("Określenie przedmiotu zamówienia: Wymiana masztów” (nr postępowania: Z/314).")["tytul"]
        == "Wymiana masztów"
    )
    assert (
        procurement("Zamówienie publiczne na zadanie: na obsługę pawilonów, znak sprawy BA/88")["tytul"]
        == "Obsługa pawilonów"
    )
    assert (
        procurement("Przetargu nieograniczonego na: dostawę aparatury dla | Wydziału Nauki, nr sprawy: Q/19")["tytul"]
        == "Dostawa aparatury dla I Wydziału Nauki"
    )
    assert (
        procurement('Zamówienia publicznego pn. „Prace remontowe w oddziale" (oznaczenie postępowania: G/52).')["tytul"]
        == "Prace remontowe w oddziale"
    )


def test_bzp_issue_with_scanned_spaces_does_not_consume_a_ted():
    page = "Ogłoszenie nr 2032 / B2P 00007539 / 04, dodatkowo ogłoszenie nr 2032 / S050-710044."
    fields = procurement(page)
    assert fields["numer_bzp"] == "2032/BZP00007539/04"
    assert fields["numer_ted"] == "710044-2032"
    assert procurement("Dokument księgowy 2032 / B2P 00007539 / 04")["numer_bzp"] is None


def test_title_crossing_native_to_ocr_page_has_mixed_provenance():
    opening = "Dotyczy: postępowania pn. „Budowa sali"
    scanned = "do prób”, nr postępowania: PP/90.\nZałącznik dotyczy innego zamówienia pn. „Naprawa trybun”."
    assert procurement(opening, scanned, scanned=(2,))["tytul"] == "Budowa sali do prób"


def test_windows_dictionary_lookup_uses_the_wheel_manifest(tmp_path, monkeypatch):
    from importlib.metadata import PackagePath
    from types import SimpleNamespace

    import tesserocr

    from kio2json import appeal_scan_procurement as module

    paths = [PackagePath("unrelated/tesseract77-invented.dll"), PackagePath("tesserocr.libs/tesseract77-invented.dll")]
    for path in paths:
        path.dist = SimpleNamespace(locate_file=lambda value: tmp_path / value)
    opened = []

    def load(path):
        opened.append(path)
        raise OSError("unavailable on this host")

    monkeypatch.setattr(tesserocr, "PyTessBaseAPI", object)
    monkeypatch.setattr(module, "files", lambda name: paths)
    monkeypatch.setattr(module.ctypes, "CDLL", load)
    with module._polish_dictionary() as valid:
        assert valid is None
    assert opened == [str(tmp_path / paths[1])]
