"""Date the first challenged act when its sentence does not open with "Zamawiający w dniu"."""

from copy import deepcopy
from pathlib import Path

import pytest

from kio2json import pipeline
from kio2json.appeal import ACTION_RE, REWORDED_ACTION_RE, extract, fill_action_date

OPENING = "Wnoszę odwołanie wobec czynności Zamawiającego. "
CHARGES = " Zaskarżonym czynnościom zarzucam naruszenie art. 226 ust. 1 Pzp."
ACT = "Pismem z dnia 5 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
OTHER_CHARGE = (
    " Zaskarżonym czynnościom zarzucam naruszenie: Zarzut nr 1 – zaniechanie odrzucenia oferty wykonawcy Rys."
)


def read(text: str) -> tuple[str | None, int | None]:
    """Date and reason as the main reader (`extract`) reports them."""
    action = extract(text)["OdwolanieKIO"]
    return action["czynnosc_dzien"], action["czynnosc_powod_id"]


def dated(text: str) -> tuple[str | None, int | None]:
    """Date and reason as the text path of the pipeline reports them."""
    record = extract(text)
    fill_action_date(record, text)
    action = record["OdwolanieKIO"]
    return action["czynnosc_dzien"], action["czynnosc_powod_id"]


@pytest.mark.parametrize("year", ["roku", "r."])
@pytest.mark.parametrize(
    "sentence",
    [
        "Zamawiający w dniu {day} {year} unieważnił postępowanie.",
        "W dniu {day} {year} Zamawiający unieważnił postępowanie.",
        "Dnia {day} {year} Zamawiający unieważnił postępowanie.",
        "Zamawiający dnia {day} {year} unieważnił postępowanie.",
        "Zamawiający, w dniu {day} {year}, unieważnił postępowanie.",
    ],
)
def test_act_sentence_may_open_with_the_buyer_or_the_date(sentence, year):
    text = OPENING + sentence.format(day="12 marca 2034", year=year) + CHARGES
    assert read(text) == ("2034-03-12", 9)


@pytest.mark.parametrize(
    "sentence",
    [
        "Odwołujący wskazuje, że w dniu 12 marca 2034 roku Zamawiający unieważnił postępowanie.",
        "Postępowanie trwało, mimo że Zamawiający w dniu 12 marca 2034 roku unieważnił umowę.",
        "W dniu 12 marca 2034 roku Odwołujący złożył ofertę.",
        "Postępowanie trwało, mimo że Zamawiający dnia 12 marca 2034 roku unieważnił umowę.",
        "Odwołujący wskazuje, że Zamawiający, w dniu 12 marca 2034 roku, unieważnił postępowanie.",
        # Only a capital "W dniu" or "Dnia" can match the date-first opening, so the anchor is what rejects these.
        "Odwołujący wskazuje, że W dniu 12 marca 2034 roku Zamawiający unieważnił postępowanie.",
        "Odwołujący wskazuje, że Dnia 12 marca 2034 roku Zamawiający unieważnił postępowanie.",
    ],
)
def test_the_date_must_open_a_sentence_about_the_buyer(sentence):
    assert not ACTION_RE.search(sentence)
    assert not REWORDED_ACTION_RE.search(sentence)


@pytest.mark.parametrize(
    "acts",
    [
        (
            "Zamawiający w dniu 5 maja 2034 r. odrzucił ofertę Odwołującego. "
            "W dniu 12 maja 2034 r. Zamawiający unieważnił postępowanie."
        ),
        (
            "W dniu 12 maja 2034 r. Zamawiający unieważnił postępowanie. "
            "Zamawiający w dniu 5 maja 2034 r. odrzucił ofertę Odwołującego."
        ),
    ],
)
def test_the_printed_wording_keeps_priority_over_a_reworded_sentence(acts):
    assert read(OPENING + acts + CHARGES) == ("2034-05-05", 1)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        # Under the heading of the second charge.
        ("Zarzut pierwszy:\nBrak podpisu.\nZarzut drugi:\nW dniu 7 maja 2034 r. Zamawiający odrzucił ofertę.\n", None),
        # In the text that supports the first charge, or in the argument.
        (
            (
                "Wnoszę odwołanie od odrzucenia oferty Odwołującego.\n"
                "Zarzucam Zamawiającemu naruszenie art. 226 ust. 1 pkt 2 Pzp poprzez odrzucenie oferty Odwołującego.\n"
                "W dniu 20 maja 2034 r. Zamawiający wykluczył z postępowania wykonawcę Rys."
            ),
            1,
        ),
        (
            (
                "Wnoszę odwołanie od odrzucenia oferty Odwołującego.\nUzasadnienie.\n"
                "W dniu 20 maja 2034 r. Zamawiający wykluczył wykonawcę Rys."
            ),
            1,
        ),
        (
            (
                "Wnoszę odwołanie od odrzucenia oferty Odwołującego. Zaskarżonym czynnościom: Zarzut nr 1 – "
                "naruszenie art. 16 Pzp. W dniu 20 maja 2034 r. Zamawiający wykluczył wykonawcę Rys."
            ),
            None,
        ),
        (
            (
                "Wnoszę odwołanie od odrzucenia oferty Odwołującego. Wobec powyższego: "
                "W dniu 20 maja 2034 r. Zamawiający wykluczył wykonawcę Rys."
            ),
            1,
        ),
        # The first charge named inline, without a line of its own.
        (
            (
                "Wnoszę odwołanie od wyboru oferty.\nZarzut 1: naruszenie art. 16 Pzp.\n"
                "Zarzut 2: naruszenie art. 17 Pzp. W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Zarzut nr. 1 – naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Zarzut I naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        # The word "nr" in a capitalised or upper-case heading.
        (
            (
                "Wnoszę odwołanie od wyboru oferty. ZARZUT NR 1: naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Zarzut Nr. 1 – naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        # Only the allegations marker ends the introduction: no charge verb, no numbered charge, no argument.
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Zaskarżonym czynnościom: naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Zarzut pierwszy: naruszenie art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
        (
            (
                "Wnoszę odwołanie od wyboru oferty. Pierwszy zarzut dotyczy art. 16 Pzp. "
                "W dniu 7 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego."
            ),
            2,
        ),
    ],
)
def test_a_reworded_act_sentence_below_the_first_charge_is_not_the_first_act(text, reason):
    assert read(text) == (None, reason)
    assert dated(text) == (None, reason)


def test_an_objection_and_a_request_are_not_the_heading_of_the_first_charge():
    # "zarzut i" is "an objection and": the numeral of a heading is a capital I or a digit.
    text = (
        "Wnoszę odwołanie. Podnoszę zarzut i wniosek o unieważnienie. "
        "W dniu 12 marca 2034 r. Zamawiający unieważnił postępowanie."
    )
    assert read(text) == ("2034-03-12", 9)
    # The same words wrapped so that "zarzut i" stands alone on a line.
    wrapped = (
        "Wnoszę odwołanie. Podnoszę\nzarzut i\nwniosek o unieważnienie. "
        "W dniu 12 marca 2034 r. Zamawiający unieważnił postępowanie."
    )
    assert read(wrapped) == ("2034-03-12", 9)


def test_a_date_that_ends_a_sentence_does_not_open_the_next_one():
    # "r." before a capital letter is read as "roku" only when the date opens its sentence.
    text = f"{OPENING}Ogłoszenie zamieszczono w dniu 1 marca 2034 r. Zamawiający odrzucił ofertę Odwołującego pismem z dnia 5 maja 2034 r.{CHARGES}"
    assert dated(text) == ("2034-05-05", 1)
    anchored = (
        f"{OPENING}Zamawiający w dniu 5 maja 2034 r. odrzucił ofertę Odwołującego złożoną w dniu 3 maja 2034 r. "
        f"Zamawiający wykluczył także wykonawcę Rys.{CHARGES}"
    )
    assert read(anchored) == ("2034-05-05", 1)


@pytest.mark.parametrize(
    ("sentence", "reason"),
    [
        ("Pismem z dnia 5 maja 2034 r. Zamawiający odrzucił ofertę Odwołującego.", 1),
        ("Zamawiający odrzucił ofertę Odwołującego pismem z dnia 5 maja 2034 roku.", 1),
        ("Odwołujący w dniu 5 maja 2034 r. otrzymał informację o unieważnieniu postępowania.", 9),
        ("Pismem z dnia 05.05.2034 r. Zamawiający odrzucił ofertę Odwołującego.", 1),
        # What follows a contrast describes another event.
        ("Pismem z dnia 5 maja 2034 r. Zamawiający odrzucił ofertę, a następnie unieważnił postępowanie.", 1),
    ],
)
def test_act_sentence_with_another_opening_is_dated_from_the_opening(sentence, reason):
    assert read(OPENING + sentence + CHARGES)[0] is None
    assert dated(OPENING + sentence + CHARGES) == ("2034-05-05", reason)


def test_first_item_of_a_list_of_challenged_acts_gives_the_act_and_its_date():
    text = (
        "Wnoszę odwołanie wobec:\n"
        "1. treści wyjaśnień SWZ (odpowiedzi na pytania wykonawców) udzielonych przez Zamawiającego "
        "w dniu 2 czerwca 2034 r.;\n"
        "2. określenia warunków udziału w postępowaniu;\n"
        "Zaskarżonym czynnościom zarzucam naruszenie:\n"
        "1) art. 255 pkt 6 Pzp poprzez jego błędne zastosowanie i unieważnienie postępowania;\n"
    )
    # The main reader takes the act from the first charge and finds no date.
    assert read(text) == (None, 9)
    # The first item names the act, and its reason wins over the one of the charge.
    assert dated(text) == ("2034-06-02", 6)


@pytest.mark.parametrize(
    ("item", "day", "reason"),
    [
        (
            (
                "1. postanowień Opisu Przedmiotu Zamówienia (OPZ), stanowiącego załącznik nr 1 do SWZ, "
                "opublikowanego w dniu 23 marca 2034 r.;"
            ),
            "2034-03-23",
            11,
        ),
        (
            (
                "1. projektowanych postanowień umowy (PPU), stanowiących załącznik nr 2 do SWZ, "
                "opublikowanych w dniu 23 marca 2034 r.;"
            ),
            "2034-03-23",
            12,
        ),
        ("1. postanowienia projektu umowy opublikowanego w dniu 23 marca 2034 r.;", "2034-03-23", 12),
        (
            (
                "1. ustaleniu treści Specyfikacji Warunków Zamówienia, opublikowanej wraz z ogłoszeniem o zamówieniu "
                "w dniu 23 czerwca 2034 r., w zakresie warunków udziału;"
            ),
            "2034-06-23",
            4,
        ),
    ],
)
def test_the_publication_of_the_tender_documents_is_an_act_even_without_the_buyer(item, day, reason):
    text = f"Wnoszę odwołanie wobec:\n{item}\n2. określenia warunków udziału w postępowaniu;\n{CHARGES}"
    assert dated(text) == (day, reason)


@pytest.mark.parametrize(
    "distractor",
    [
        "Odwołujący wnosi odwołanie od odrzucenia swojej oferty w terminie do dnia 15 maja 2034 r.",
        "Odwołujący wnosi odwołanie od odrzucenia swojej oferty na podstawie ustawy z dnia 11 września 2019 r.",
        "Odwołanie od odrzucenia oferty Odwołującego zostało wniesione dnia 10 maja 2034 r.",
        "Odwołujący zapłacił za odrzucenie oferty fakturą z dnia 3 maja 2034 r.",
        "Odwołujący zapłacił za odrzucenie oferty płatnością z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty, o którym orzekał wyrok z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty po ogłoszeniu w BZP w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża przepis (Dz. U. z dnia 3 maja 2034 r. poz. 5) Zamawiający odrzucił ofertę Odwołującego.",
        "Odwołujący zaskarża odrzucenie oferty niezgodne z rozporządzeniem z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty niezgodne z dyrektywą z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty wbrew uchwale z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty wbrew postanowieniu z dnia 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty, której okres związania ofertą upływa dnia 15 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty po wniesieniu protestu dnia 10 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty po ogłoszeniu w TED w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty złożonej w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty w postępowaniu wszczętym w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty po ogłoszeniu w Biuletynie Zamówień Publicznych w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty po ogłoszeniu w Dzienniku Urzędowym w dniu 3 maja 2034 r.",
        "Odwołujący zaskarża odrzucenie oferty wbrew postanowieniu Krajowej Izby Odwoławczej z dnia 3 maja 2034 r.",
    ],
)
def test_deadline_filing_invoice_statute_and_notice_dates_do_not_date_the_act(distractor):
    assert dated(f"Wnoszę odwołanie. {distractor} {ACT}{CHARGES}") == ("2034-05-05", 1)
    assert dated(f"Wnoszę odwołanie. {distractor}{CHARGES}")[0] is None


def test_a_notice_in_the_filing_sentence_does_not_date_the_first_listed_act():
    text = (
        "Wnoszę odwołanie od czynności Zamawiającego podjętych w postępowaniu pn. „Dostawa” "
        "(ogłoszenie o zamówieniu opublikowane w BZP w dniu 12 grudnia 2033 r.), polegających na: "
        f"1) odrzuceniu oferty Odwołującego; 2) wyborze oferty innego wykonawcy.{CHARGES}"
    )
    assert dated(text) == (None, 1)


@pytest.mark.parametrize(
    "items",
    [
        "1) wyboru oferty najkorzystniejszej; 2) odrzucenia oferty Odwołującego z dnia 5 maja 2034 r.",
        "1) wyboru oferty najkorzystniejszej. 2) Odrzucenie oferty Odwołującego z dnia 5 maja 2034 r.",
    ],
)
def test_the_second_item_of_an_inline_list_ends_the_act_segment(items):
    assert dated(f"Wnoszę odwołanie od: {items}{CHARGES}") == (None, 2)


@pytest.mark.parametrize(
    ("dateline", "filed", "day"),
    [
        ("4 maja 2034", "2034-05-04", None),
        ("6 maja 2034", "2034-05-06", None),
        ("8 maja 2034", "2034-05-08", "2034-05-06"),
    ],
)
def test_a_date_on_or_after_the_filing_date_is_not_the_act(dateline, filed, day):
    text = f"Torfowo, {dateline} r.\nODWOŁANIE\n{OPENING}{ACT.replace('5 maja', '6 maja')}{CHARGES}"
    assert extract(text)["OdwolanieKIO"]["data"] == filed
    assert dated(text)[0] == day


@pytest.mark.parametrize(
    "text",
    [
        # The only date has no act: a second offer is not a challenged act.
        (
            "Wnoszę odwołanie. Skutkiem naruszenia przepisów jest wykluczenie wykonawcy. "
            "Odwołujący złożył drugą ofertę dnia 2 maja 2034."
        ),
        OPENING + "Pismo z dnia 5 maja 2034 r. dotyczy sprawy." + CHARGES,
        # Background events name neither the buyer nor the first listed act.
        f"{OPENING}SWZ została opublikowana w dniu 1 marca 2034 r.{CHARGES}",
        (
            "Wnoszę odwołanie wobec:\n1. nieokreślonych czynności. SWZ została opublikowana w dniu 1 marca 2034 r.;\n"
            "2. określenia warunków udziału w postępowaniu;" + CHARGES
        ),
        # The second listed act is not the first one.
        "Wnoszę odwołanie wobec:\n1. nieokreślonych czynności;\n2. odrzucenia oferty Odwołującego w dniu 5 maja 2034 r.;"
        + CHARGES,
        # What follows a contrast describes another event.
        f"{OPENING}Zamawiający wezwał Odwołującego do wyjaśnień, a pismem z dnia 10 maja 2034 r. odrzucił jego ofertę.{CHARGES}",
        (
            "Wnoszę odwołanie wobec czynności polegających na zaniechaniu odrzucenia oferty wykonawcy Rys, "
            f"mimo że Zamawiający w dniu 1 sierpnia 2034 r. wzywał go do wyjaśnień.{CHARGES}"
        ),
        # The charges are not part of the introduction.
        (
            OPENING + "Zaskarżonym czynnościom zarzucam naruszenie art. 226 ust. 1 pkt 2 Pzp przez odrzucenie oferty "
            "Odwołującego pismem z dnia 7 maja 2034 r."
        ),
        # A question about an act is not the act.
        f"{OPENING}Zamawiający dnia 11.04.2035 otrzymał pytanie, czy trzeba odrzucić ofertę.{CHARGES}",
        f"{OPENING}Pismem z dnia 5 maja 2034 r. Zamawiający zapytał, czy odrzucić ofertę Odwołującego.{CHARGES}",
        # The act sentence has to come soon after the filing sentence.
        "Wnoszę odwołanie. " + "Zamawiający złożył wyjaśnienia. " * 60 + ACT + CHARGES,
        "Odwołujący zarzuca. " + ACT,
    ],
)
def test_a_date_that_no_sentence_ties_to_an_act_stays_empty(text):
    assert dated(text)[0] is None


@pytest.mark.parametrize(
    "text",
    [
        (
            "ODWOŁANIE od czynności wyboru oferty. Pismem z dnia 5 maja 2034 r. Zamawiający poinformował o wyborze "
            "oferty innego wykonawcy. Zaskarżonym czynnościom zarzucam naruszenie art. 16 Pzp. Wobec powyższego "
            "wnoszę o: 1) unieważnienie czynności wyboru oferty z dnia 7 maja 2034 r.; 2) nakazanie powtórzenia "
            "badania ofert."
        ),
        (
            "ODWOŁANIE od czynności wyboru oferty. Zarzucam Zamawiającemu naruszenie art. 16 Pzp. Wobec powyższego "
            "wnoszę o: 1) unieważnienie czynności wyboru oferty z dnia 7 maja 2034 r.; 2) nakazanie powtórzenia "
            "badania ofert."
        ),
        (
            "ODWOŁANIE od czynności wyboru oferty.\nZarzut pierwszy\nNaruszenie art. 16 Pzp.\n"
            "Wobec powyższego wnoszę o:\n1) unieważnienie czynności wyboru oferty z dnia 7 maja 2034 r.;\n"
            "2) nakazanie powtórzenia badania ofert."
        ),
    ],
)
def test_the_petition_after_the_charges_is_not_read_for_the_act(text):
    assert dated(text)[0] is None


def test_the_charges_heading_ends_the_act_segment():
    text = (
        "Wnoszę odwołanie.\nZarzut pierwszy\nZamawiający naruszył art. 226 ust. 1 pkt 2 Pzp, "
        "odrzucając ofertę Odwołującego z dnia 7 maja 2034 r."
    )
    assert dated(text)[0] is None


def test_an_account_read_above_the_first_charge_heading_is_not_second_guessed():
    # The account just above the heading names another act than the first charge, so its date stays empty
    # although an earlier sentence of the introduction names a dated act.
    text = (
        "Wnoszę odwołanie.\nPismem z dnia 5 maja 2034 r. Zamawiający wykluczył Odwołującego.\n"
        "Zamawiający odrzucił ofertę.\nPierwszy zarzut\nUnieważnienie postępowania."
    )
    assert read(text) == (None, 9)
    assert dated(text) == (None, 9)


def test_an_anchored_sentence_that_names_no_act_does_not_block_the_fallback():
    text = f"{OPENING}W dniu 1 marca 2034 r. Zamawiający wszczął postępowanie. {ACT}{CHARGES}"
    assert read(text)[0] is None
    assert dated(text) == ("2034-05-05", 1)


@pytest.mark.parametrize(
    "sentence",
    [
        "Pismem z dnia 5 maja 2034 r. Zamawiający dokonał wyboru oferty wykonawcy Rys.",
        # The anchored sentence was judged by the main reader: its empty date is deliberate.
        "Zamawiający w dniu 5 maja 2034 roku dokonał wyboru oferty wykonawcy Rys.",
    ],
)
def test_first_charge_naming_another_act_keeps_the_act_undated(sentence):
    assert read(OPENING + sentence + OTHER_CHARGE) == (None, 7)
    assert dated(OPENING + sentence + OTHER_CHARGE) == (None, 7)


def test_the_first_act_sentence_settles_the_act():
    # The first sentence names another act than the first charge, so the date stays empty although the second
    # sentence names the act of the charge.
    text = (
        f"{OPENING}Pismem z dnia 5 maja 2034 r. Zamawiający dokonał wyboru oferty wykonawcy Rys. "
        f"Pismem z dnia 6 maja 2034 r. Zamawiający zaniechał odrzucenia oferty wykonawcy Rys.{OTHER_CHARGE}"
    )
    assert dated(text) == (None, 7)


def test_an_anchored_sentence_settles_the_act_even_when_its_date_stays_empty():
    # Documents that read correctly with the printed wording keep what the main reader made of them.
    text = (
        f"{OPENING}Pismem z dnia 1 maja 2034 r. Zamawiający zaniechał odrzucenia oferty wykonawcy Rys. "
        f"Zamawiający w dniu 5 maja 2034 r. dokonał wyboru oferty wykonawcy Rys.{OTHER_CHARGE}"
    )
    assert read(text) == (None, 7)
    assert dated(text) == (None, 7)


def test_an_act_dated_by_the_main_reader_is_not_touched():
    text = (
        OPENING
        + "Zamawiający w dniu 5 maja 2034 roku odrzucił ofertę. Pismem z dnia 9 maja 2034 r. Zamawiający wykluczył Odwołującego."
    )
    record = extract(text)
    before = deepcopy(record)
    fill_action_date(record, text)
    assert record == before
    assert record["OdwolanieKIO"]["czynnosc_dzien"] == "2034-05-05"


def test_a_date_the_main_reader_took_from_the_first_charge_is_not_replaced():
    charge = " Zaskarżonym czynnościom zarzucam naruszenie: Zarzut nr 1 – odrzucenie oferty Odwołującego z dnia 9 maja 2034 r."
    text = OPENING + ACT + charge
    assert read(text) == ("2034-05-09", 1)
    assert dated(text) == ("2034-05-09", 1)


def test_the_first_dated_act_wins_over_later_acts():
    text = OPENING + ACT + " Pismem z dnia 9 maja 2034 r. Zamawiający wykluczył Odwołującego." + CHARGES
    assert dated(text) == ("2034-05-05", 1)


def test_the_text_path_of_the_pipeline_dates_the_act(monkeypatch):
    page = f"Zamawiający: Port Mgły\nOdwołujący: Dom Wag\nODWOŁANIE\n{OPENING}{ACT}{CHARGES}"
    monkeypatch.setattr(pipeline, "read_pages", lambda path, **options: [page])
    label, result = pipeline.process_pdf(Path("invented.pdf"))
    action = result["OdwolanieKIO"]
    assert label == "appeal"
    assert (action["czynnosc_dzien"], action["czynnosc_powod_id"], action["czynnosc_opis"]) == (
        "2034-05-05",
        1,
        "Decyzja o odrzuceniu oferty",
    )
