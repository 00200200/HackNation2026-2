"""OCR noise in free-text fields becomes null or loses its noisy tail (invented strings only)."""

import pytest

from kio2json.ocr_plausibility import gate_appeal, plausible_text


@pytest.mark.parametrize(
    "noise",
    [
        "ąz =— KQ WWWW Lublin I |] OKA | Te XYV |",
        "[| ~~ 12 # 7 <> |",
        "== ## 4.5.6 // ..",
    ],
)
def test_noise_becomes_null(noise):
    assert plausible_text(noise) is None


@pytest.mark.parametrize(
    "name",
    [
        "Zielona Dolina Spółka z ograniczoną odpowiedzialnością",
        "PKX TRK S.A.",
        "Biuro Wzorcowe Nowak sp. z o.o. sp.k.",
        "Gmina Przykładowo",
        "Fikcyjna Firma S.A. Oddział w Opolu",
        "Dostawa sprzętu komputerowego dla szkół w 2026 r. (część 1–3)",
        None,
        "",
    ],
)
def test_plausible_values_are_kept(name):
    assert plausible_text(name) == name


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        (
            "Wodociągi Przykładowe Spółka z ograniczoną odpowiedzialnością K TRAZI NJ OMMO Opole W QXRT BE",
            "Wodociągi Przykładowe Spółka z ograniczoną odpowiedzialnością",
        ),
        ("Testowa Firma S.A. | EBX", "Testowa Firma S.A."),
    ],
)
def test_noisy_tail_after_legal_form_is_cut(raw, clean):
    assert plausible_text(raw) == clean


def test_gate_appeal_touches_only_free_text():
    lawyer = {"imie_nazwisko": "Jan Przykładowy", "nazwa": "| ][ =", "mail": "a@b.pl"}
    record = {
        "Odwolujacy": [{"nazwa": "wą =— QQ |] |", "nip": "1234567890", "pelnomocnik": lawyer}],
        "Zamawiajacy": [{"nazwa": "Gmina Przykładowo", "nip": None}],
        "ZamowieniePubliczne": {"tytul": "Budowa drogi gminnej", "numer_bzp": "2026/BZP00000001"},
    }
    gate_appeal(record)
    assert record["Odwolujacy"][0]["nazwa"] is None
    assert record["Odwolujacy"][0]["nip"] == "1234567890"
    assert lawyer == {"imie_nazwisko": "Jan Przykładowy", "nazwa": None, "mail": "a@b.pl"}
    assert record["Zamawiajacy"][0]["nazwa"] == "Gmina Przykładowo"
    assert record["ZamowieniePubliczne"]["tytul"] == "Budowa drogi gminnej"
