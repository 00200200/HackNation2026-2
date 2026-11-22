"""Facts printed in the opening account of an appeal."""

import pytest

from kio2json.appeal import extract


@pytest.mark.parametrize(
    ("clause", "reason", "day"),
    [
        ("Zamawiającyw dniu 11.04.2035 r.\nodrzucił ofertę spółki.", 1, "2035-04-11"),
        ("Zamawiającywykluczył przedsiębiorcę z przetargu.", 3, None),
        ("Zamawiający nie unieważnił postępowania mimo uchybienia.", 10, None),
        ("Zamawiający dnia 11 kwietnia 2035 r.zmodyfikował postanowienia SWZ.", 5, "2035-04-11"),
        ("Zamawiający poinformował o zmianie adresu. Wykluczenie wykonawcy dotyczy innego przetargu.", None, None),
        ("Zamawiający dnia 11.04.2035 otrzymał pytanie, czy trzeba odrzucić ofertę.", None, None),
        ("Zamawiający podtrzymał ocenę.\nW uzasadnieniu przytoczono odrzucenie oferty.", None, None),
    ],
)
def test_opening_account_is_bounded_by_first_charge(clause, reason, day):
    text = f"Składam odwołanie.\n{clause}\nZarzut pierwszy:\nWskazuję poniższe uchybienia."
    act = extract(text)["OdwolanieKIO"]
    assert (act["czynnosc_powod_id"], act["czynnosc_dzien"]) == (reason, day)


def test_later_charge_cannot_supply_the_opening_act():
    body = "Zarzut pierwszy:\nBrak podpisu.\nZamawiającyodrzucił ofertę.\nZarzut drugi:\nInne uwagi."
    assert extract(body)["OdwolanieKIO"]["czynnosc_powod_id"] is None


def test_year_abbreviation_can_adjoin_the_predicate():
    text = "Zamawiający dnia 30.09.2031 rwykluczył przedsiębiorcę.\nPierwszy zarzut\nWskazuję uchybienia."
    act = extract(text)["OdwolanieKIO"]
    assert (act["czynnosc_powod_id"], act["czynnosc_dzien"]) == (3, "2031-09-30")


@pytest.mark.parametrize(
    "clause",
    [
        "Zamawiający odrzucił wniosek o wydanie kopii SWZ.",
        "Zamawiający wykluczył możliwość przeniesienia środków.",
        "Zamawiający udostępnił informację o posiedzeniu w sprawie odrzucenia oferty.",
        "Zamawiający w dniu 02.01.2031 odrzucił wniosek o wydanie kopii SWZ.",
    ],
)
def test_action_object_must_identify_the_challenged_act(clause):
    text = f"Składam odwołanie.\n{clause}\nZarzut pierwszy\nNaruszono zasady."
    assert extract(text)["OdwolanieKIO"]["czynnosc_powod_id"] is None


def test_explicit_first_charge_overrides_a_different_earlier_decision():
    text = "Zamawiający dnia 03.02.2037 odrzucił ofertę.\nPierwszy zarzut\nUnieważnienie postępowania."
    act = extract(text)["OdwolanieKIO"]
    assert (act["czynnosc_powod_id"], act["czynnosc_dzien"]) == (9, None)


def test_an_intervening_sentence_separates_background_from_the_challenge():
    text = (
        "Zamawiający w dniu 07.05.2036 unieważnił postępowanie.\n"
        "W tym odwołaniu skarżę jedynie sposób doręczenia.\nZarzut pierwszy\nBrak podpisu."
    )
    act = extract(text)["OdwolanieKIO"]
    assert (act["czynnosc_powod_id"], act["czynnosc_dzien"]) == (None, None)


def test_labelled_act_and_date_survive_an_unrelated_opening_statement():
    text = (
        "Data czynności: 05.09.2038\nZaskarżona czynność: unieważnienie postępowania\n"
        "Zamawiający ogłosił godzinę odbioru dokumentacji.\nPierwszy zarzut\nBrak uzasadnienia."
    )
    act = extract(text)["OdwolanieKIO"]
    assert (act["czynnosc_powod_id"], act["czynnosc_dzien"]) == (9, "2038-09-05")
