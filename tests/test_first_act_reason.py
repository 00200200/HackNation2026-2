"""Independent first-act examples with handwritten Polish inflections and owners."""

import pytest

from kio2json.appeal import REASONS

# The same fixtures drive the optional, paired model diagnostic.
EXAMPLES = [
    ("Odwołuję się od tego, że odrzucona została nasza oferta. Wnoszę o ponowny wybór.", 1),
    ("Zaskarżamy wybór dokonany przez zamawiającego spośród ofert złożonych w pakiecie B.", 2),
    ("Kwestionujemy decyzję, którą wykluczono nas z udziału w przetargu.", 3),
    ("Wnosimy odwołanie wobec ogłoszenia specyfikacji warunków zamówienia.", 4),
    ("Odwołanie obejmuje zmianę wprowadzoną do treści specyfikacji warunków zamówienia.", 5),
    ("Przedmiotem odwołania są odpowiedzi dotyczące postanowień SWZ, przekazane oferentom.", 6),
    ("Zaskarżam fakt, że oferta konkurenta nie została odrzucona. Z ostrożności podważam też wybór.", 7),
    ("Kwestionuję niewykluczenie z przetargu innego oferenta.", 8),
    ("Odwołanie od decyzji, na mocy której postępowanie zostało unieważnione.", 9),
    ("Zaskarżone czynności:\n(a) niedokonanie przez kupującego unieważnienia postępowania.\n(b) wybór oferty.", 10),
    ("Odwołanie dotyczy opisu technicznego przedmiotu zamówienia zamieszczonego w SWZ.", 11),
    ("Odwołujemy się od warunków projektowanej umowy zawartych w specyfikacji.", 12),
    ("Odwołanie od odmowy wydania protokołu. Tytułem ewentualnym kwestionujemy odrzucenie oferty.", None),
    ("Odwołanie dotyczy braku uzasadnienia. Załącznik: zawiadomienie o wyborze oferty.", None),
    ("Kwestionuję odrzucenie wniosku o kopię oferty przeciwnika.", None),
    ("Zaskarżam zmianę terminu składania ofert, wspomnianą w piśmie dotyczącym SWZ.", None),
    ("Zaskarżam niezłożenie oferty. Wnioski: unieważnić postępowanie.", None),
    ("Odwołanie od odmowy uznania reklamacji.\nZałączniki:\na) wykluczenie wykonawcy", None),
]


def test_authored_examples_on_missing_fields():
    from kio2json.first_act import fill_missing_action

    for text, reason in EXAMPLES:
        header = {"czynnosc_powod_id": None, "czynnosc_opis": None, "czynnosc_dzien": None}
        fill_missing_action(header, text)
        assert (header["czynnosc_powod_id"], header["czynnosc_opis"]) == (reason, REASONS.get(reason))


def test_existing_reason_skips_both_readers(monkeypatch):
    from kio2json import first_act

    monkeypatch.setattr(first_act, "first_phrase", lambda _: pytest.fail("populated reason must bypass the reader"))
    header = {"czynnosc_powod_id": 2, "czynnosc_opis": REASONS[2], "czynnosc_dzien": None}
    first_act.fill_missing_action(header, "Kwestionuję odrzucenie naszej oferty.")
    assert header == {"czynnosc_powod_id": 2, "czynnosc_opis": REASONS[2], "czynnosc_dzien": None}


def test_existing_date_is_never_reread(monkeypatch):
    from kio2json import first_act

    monkeypatch.setattr(
        first_act, "phrase_day", lambda *args: pytest.fail("populated date must bypass the date reader")
    )
    header = {"czynnosc_powod_id": None, "czynnosc_opis": None, "czynnosc_dzien": "2031-04-13"}
    first_act.fill_missing_action(header, "Kwestionuję odrzucenie naszej oferty (decyzja z dnia 4 maja 2031).")
    assert header == {"czynnosc_powod_id": 1, "czynnosc_opis": REASONS[1], "czynnosc_dzien": "2031-04-13"}


def test_null_id_and_date_can_use_single_local_notice():
    from kio2json.first_act import fill_missing_action

    header = {"czynnosc_powod_id": None, "czynnosc_opis": None, "czynnosc_dzien": None}
    fill_missing_action(header, "Kwestionuję odrzucenie naszej oferty (decyzja z dnia 4 maja 2031).")
    assert header == {"czynnosc_powod_id": 1, "czynnosc_opis": REASONS[1], "czynnosc_dzien": "2031-05-04"}


def test_optional_model_must_quote_the_complete_localized_phrase(monkeypatch):
    from kio2json import charge_model

    phrase = "niedokonanie przez komisję odrzucenia oferty"
    proposal = charge_model.PhraseReason(reason_id=1, act_quote="odrzucenia oferty")
    monkeypatch.setattr(charge_model.llm, "structured", lambda *a, **kw: proposal)
    assert charge_model.model_reason(phrase) is None
    proposal = charge_model.PhraseReason(reason_id=7, act_quote=phrase)
    assert charge_model.model_reason(phrase) == 7


@pytest.mark.parametrize("view", ["native", "scan"])
def test_routed_appeal_fills_the_missing_reason_after_existing_readers(tmp_path, view):
    import random

    from evals.case_scans import scan_pdf
    from evals.variant_pages import render
    from kio2json.pipeline import process_pdf

    path = tmp_path / "appeal.pdf"
    path.write_bytes(
        render(
            "Krajowa Izba Odwoławcza",
            [
                ["Odwołujący: Pracownia Systemów", "Zamawiający: Instytut Dokumentacji"],
                ["ODWOŁANIE"],
                [EXAMPLES[0][0]],
            ],
            "single-column",
            random.Random(115),
        )
    )
    if view == "scan":
        scan = tmp_path / "scan.pdf"
        scan_pdf(path, scan, dpi=300, codec="jpeg-gray", quality=80, angle=0, seed=115)
        path = scan
    kind, record = process_pdf(path)
    assert kind == "appeal"
    assert record["OdwolanieKIO"]["czynnosc_powod_id"] == 1


def test_incompatible_preexisting_label_is_preserved():
    from kio2json.first_act import fill_missing_action

    header = {"czynnosc_powod_id": None, "czynnosc_opis": REASONS[3], "czynnosc_dzien": None}
    fill_missing_action(header, "Kwestionuję odrzucenie naszej oferty.")
    assert header == {"czynnosc_powod_id": None, "czynnosc_opis": REASONS[3], "czynnosc_dzien": None}
