"""Independent invented layouts covering party, filing and first-charge evidence."""

import pytest

from kio2json.appeal import extract
from kio2json.classify import classify


def test_single_company_with_consortium_in_its_registered_name():
    text = """ODWOŁANIE
Odwołujący: Konsorcjum Witraży sp. z o.o.
Zamawiający: Muzeum Klepsydr
Torfowo, 4 maja 2034 r.
Numer postępowania: WK/34/11
Odwołujący zarzuca odrzucenie oferty z dnia 2 maja 2034."""
    assert classify([text]) == "appeal"
    result = extract(text)
    assert [p["nazwa"] for p in result["Odwolujacy"]] == ["Konsorcjum Witraży sp. z o.o."]
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Muzeum Klepsydr"]
    assert result["ZamowieniePubliczne"]["numer_postepowania"] == "WK/34/11"
    action = result["OdwolanieKIO"]
    assert (action["miejscowosc"], action["data"], action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (
        "Torfowo",
        "2034-05-04",
        1,
        "2034-05-02",
    )


def test_two_column_reading_order_keeps_labelled_title_and_counsel():
    text = """ODWOŁANIE
Zamawiający:     Oficyna Południkowa
Odwołujący:      Huta Cynobru
Pełnomocnik Odwołującego:   Ada Cekin
Nazwa postępowania:         Wymiana szklanych półek
Znak sprawy:                WP/34/12
Odwołujący zarzuca zaniechanie odrzucenia oferty."""
    result = extract(text)
    (party,) = result["Odwolujacy"]
    assert (party["nazwa"], party["pelnomocnik"]["imie_nazwisko"]) == ("Huta Cynobru", "Ada Cekin")
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Oficyna Południkowa"]
    assert result["OdwolanieKIO"]["czynnosc_powod_id"] == 7
    proc = result["ZamowieniePubliczne"]
    assert (proc["tytul"], proc["numer_postepowania"]) == ("Wymiana szklanych półek", "WP/34/12")


def test_numbered_consortium_and_joint_purchasers():
    text = """ODWOŁANIE
Odwołujący: wykonawcy wspólnie ubiegający się o zamówienie:
1) Splot Lnu (członek konsorcjum)
2) Splot Wełny (lider konsorcjum)
Zamawiający: Dom Mozaiki
prowadzący postępowanie w imieniu i na rzecz:
1) Warsztat Szkliwa
2) Instytut Pigmentu
Numer postępowania: WM/34/13
Odwołujący zarzuca zaniechanie wykluczenia wykonawcy."""
    result = extract(text)
    assert [p["nazwa"] for p in result["Odwolujacy"]] == ["Splot Wełny"]
    assert [(p["nazwa"], p["prowadzacy_postepowanie"]) for p in result["Zamawiajacy"]] == [
        ("Dom Mozaiki", 1),
        ("Warsztat Szkliwa", 0),
        ("Instytut Pigmentu", 0),
    ]
    assert result["OdwolanieKIO"]["czynnosc_powod_id"] == 8
    assert result["ZamowieniePubliczne"]["numer_postepowania"] == "WM/34/13"


def test_signed_letterhead_with_both_parties_in_prose():
    text = """Kancelaria Srebrna Nuta
Smyczkowo, 9 maja 2034 r.
ODWOŁANIE
W imieniu spółki Smyk Harfy, jako odwołującego, wnoszę odwołanie wobec
wyboru oferty w postępowaniu prowadzonym przez Dom Altówki.
Postępowanie pod nazwą „Naprawa tłumików” (numer sprawy: DA/34/14).
Pełnomocnik Odwołującego
Ada Smyk"""
    assert classify([text]) == "appeal"
    result = extract(text)
    (party,) = result["Odwolujacy"]
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Dom Altówki"]
    assert (party["nazwa"], party["przez-pelnomocnika"], party["pelnomocnik"]["imie_nazwisko"]) == (
        "Smyk Harfy",
        1,
        "Ada Smyk",
    )
    assert party["pelnomocnik"]["nazwa"] == "Kancelaria Srebrna Nuta"
    action = result["OdwolanieKIO"]
    assert (action["miejscowosc"], action["data"], action["czynnosc_powod_id"]) == ("Smyczkowo", "2034-05-09", 2)
    proc = result["ZamowieniePubliczne"]
    assert (proc["tytul"], proc["numer_postepowania"]) == ("Naprawa tłumików", "DA/34/14")


@pytest.mark.parametrize("mark", ["brak", "IN/99", ""])
def test_form_prefers_specific_reference_and_stops_title_at_next_row(mark):
    text = f"""ODWOŁANIE
Odwołujący: Studio Gnomonu
Zamawiający: Pałac Cieni
Znak: {mark}
Numer postępowania: PC/34/15
Nazwa postępowania: Montaż zegara słonecznego
Data złożenia: 12 maja 2034 r.
Zarzut nr 1 – wykluczenie wykonawcy."""
    result = extract(text)
    assert [p["nazwa"] for p in result["Odwolujacy"]] == ["Studio Gnomonu"]
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Pałac Cieni"]
    proc = result["ZamowieniePubliczne"]
    assert (proc["tytul"], proc["numer_postepowania"]) == ("Montaż zegara słonecznego", "PC/34/15")
    assert (result["OdwolanieKIO"]["data"], result["OdwolanieKIO"]["czynnosc_powod_id"]) == ("2034-05-12", 3)


def test_register_requires_positive_filing_evidence_for_plural_heading():
    header = "ODWOŁANIA\nZamawiający: Oficyna Zakładek\nOdwołujący: Fabryka Nitek\n"
    assert classify(["Spis korespondencji\n" + header + "Wykaz doręczonych pism."]) is None
    assert classify([header + "Wnoszę odwołanie wobec wyboru oferty."]) == "appeal"


def test_third_person_filing_names_both_roles_in_one_sentence():
    text = "ODWOŁANIE\nPełnomocnik wnosi odwołanie w imieniu Domu Wagi wobec czynności zamawiającego Studio Wstęgi."
    assert classify([text]) == "appeal"
    result = extract(text)
    assert [p["nazwa"] for p in result["Odwolujacy"]] == ["Domu Wagi"]
    assert [p["nazwa"] for p in result["Zamawiajacy"]] == ["Studio Wstęgi"]


def test_branch_office_name_and_registered_seat_are_distinct():
    result = extract("Zamawiający: Muzeum Metronomu Oddział Północny z siedzibą w Rytmowie\nODWOŁANIE")
    assert result["Zamawiajacy"][0]["nazwa"] == "Muzeum Metronomu Oddział Północny"


def test_counsel_employer_field_and_email_are_scoped_to_the_mandate():
    result = extract(
        "Odwołujący: Dom Splotu\nPełnomocnik Odwołującego: Ida Splot\n"
        "Pracodawca: Biuro Prawne Szpula\ne-mail: ida@example.test\n"
        "Zamawiający: Szpulka\nKancelaria Obca\ne-mail: druga@example.test"
    )
    attorney = result["Odwolujacy"][0]["pelnomocnik"]
    assert attorney == {"imie_nazwisko": "Ida Splot", "nazwa": "Biuro Prawne Szpula", "mail": "ida@example.test"}


def test_first_person_mandate_needs_an_appellant_link():
    start = "Odwołujący: Port Barw\nZamawiający: Dom Kredy\nODWOŁANIE\n"
    affirmative = "W imieniu odwołującego, na mocy pełnomocnictwa, składam niniejsze odwołanie."
    unrelated = "W dokumentacji zamawiającego znajduje się pełnomocnictwo. Wnoszę odwołanie."
    assert extract(start + affirmative)["Odwolujacy"][0]["przez-pelnomocnika"] == 1
    assert extract(start + unrelated)["Odwolujacy"][0]["przez-pelnomocnika"] == 0


def test_date_in_unrelated_clause_or_subsequent_sentence_is_not_the_act_date():
    text = "Odwołujący zarzuca odrzucenie oferty. Dnia 6 maja 2034 r. stanowi początkową datę biegu terminu płatności."
    action = extract(text)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, None)
    header = "Zarzut nr 1 – odrzucenie oferty, a fakturę wystawiono w dniu 6 maja 2034."
    assert extract(header)["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_introductory_challenge_stops_at_any_new_sentence():
    text = "Wnoszę odwołanie wobec braku uzasadnienia. Dokumentacja wspomina o odrzuceniu oferty."
    assert extract(text)["OdwolanieKIO"]["czynnosc_powod_id"] is None


def test_later_notice_must_link_the_date_to_the_first_act():
    text = (
        "Odwołujący zarzuca odrzucenie oferty.\n2) wybór oferty z dnia 7 maja 2034.\n"
        "Zachowanie terminu: O odrzuceniu oferty poinformowano dnia 8 maja 2034."
    )
    action = extract(text)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, "2034-05-08")


def test_nested_employer_and_branch_names_can_wrap_across_rows():
    doc = (
        "Odwołujący: Dom Dźwięku\nPełnomocnik Odwołującego: Ida Nutka\n"
        "adres do korespondencji: Kancelaria Dolnych\nGłosów, ul. Perłowa 9\n"
        "Zamawiający: Instytut Nut z siedzibą w Fletowie, Oddział Dzwonów\nODWOŁANIE"
    )
    result = extract(doc)
    assert result["Odwolujacy"][0]["pelnomocnik"]["nazwa"] == "Kancelaria Dolnych Głosów"
    assert result["Zamawiajacy"][0]["nazwa"] == "Instytut Nut, Oddział Dzwonów"


def test_invalid_specific_reference_does_not_consume_next_label():
    doc = "Numer postępowania:\nNumer postępowania: ZK/35\nZnak: IN/42"
    assert extract(doc)["ZamowieniePubliczne"]["numer_postepowania"] == "ZK/35"


def test_first_charge_introduction_ends_party_and_excludes_later_charge_from_members():
    doc = "ODWOŁANIE\nOdwołujący: Port Rur\nZamawiający: Huta Rur\nOdwołujący zarzuca zmianę SWZ.\n2) wybór oferty."
    assert [p["nazwa"] for p in extract(doc)["Zamawiajacy"]] == ["Huta Rur"]


def test_prose_notification_date_is_not_taken_from_another_clause():
    doc = "Odwołujący zarzuca odrzucenie oferty, a fakturę opublikowano 4 maja 2034."
    assert extract(doc)["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_notice_in_same_clause_takes_precedence_over_background():
    doc = (
        "Odrzucenie oferty z dnia 3 maja 2034 dotyczyło wcześniejszej sprawy.\n"
        "Odwołujący zarzuca odrzucenie oferty z dnia 5 maja 2034."
    )
    assert extract(doc)["OdwolanieKIO"]["czynnosc_dzien"] == "2034-05-05"


def test_empty_form_title_cannot_consume_next_inline_field():
    body = "Nazwa postępowania:                     Numer sprawy: ZT/88"
    assert extract(body)["ZamowieniePubliczne"]["tytul"] is None
    body = "Nazwa postępowania: Remont kładki    Numer sprawy: ZT/88"
    assert extract(body)["ZamowieniePubliczne"]["tytul"] == "Remont kładki"


def test_attorney_filing_in_prose_has_an_affirmative_mandate():
    body = "ODWOŁANIE\nPełnomocnik wnosi odwołanie w imieniu Domu Wagi wobec czynności zamawiającego Studio Wstęgi."
    assert extract(body)["Odwolujacy"][0]["przez-pelnomocnika"] == 1


def test_introductory_background_alone_does_not_date_uncertain_first_charge():
    body = "Odwołujący zarzuca naruszenie przepisów, którego skutkiem jest wykluczenie wykonawcy. Drugą ofertę złożono dnia 2 maja 2034."
    assert extract(body)["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_body_mandate_for_a_different_principal_does_not_represent_the_appellant():
    text = (
        "Odwołujący: Port Zegarów\nZamawiający: Fabryka Piór\nODWOŁANIE\n"
        "Pełnomocnik wnosi odwołanie w imieniu Fabryka Piór."
    )
    assert extract(text)["Odwolujacy"][0]["przez-pelnomocnika"] == 0


def test_act_and_date_can_be_linked_in_a_second_clause():
    text = "Odwołujący zarzuca błędy proceduralne, w tym odrzucenie oferty z dnia 8 czerwca 2034."
    action = extract(text)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, "2034-06-08")


def test_decimal_first_list_item_is_not_a_sentence_boundary():
    text = "Odwołujący zarzuca:\n1. odrzucenie oferty z dnia 8 czerwca 2034.\n2. wybór oferty."
    action = extract(text)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, "2034-06-08")


def test_introductory_date_does_not_cross_into_another_act_clause():
    text = "Zamawiający w dniu 4 maja 2034 odebrał fakturę, a później odrzucił ofertę. Zarzut nr 1 – odrzucenie oferty."
    action = extract(text)["OdwolanieKIO"]
    assert (action["czynnosc_powod_id"], action["czynnosc_dzien"]) == (1, None)


def test_counsel_firm_keeps_legal_period_and_drops_address_separator():
    text = (
        "Odwołujący: Dom Grobli\nPełnomocnik Odwołującego: Ada Grobla\n"
        "adres do korespondencji: Kancelaria Śluza sp. z o.o.,\nul. Wodna 8\nZamawiający: Scena"
    )
    assert extract(text)["Odwolujacy"][0]["pelnomocnik"]["nazwa"] == "Kancelaria Śluza sp. z o.o."


def test_contact_word_and_number_in_a_labelled_legal_name():
    doc = "Odwołujący: Kontakt 24 sp. z o.o.\nZamawiający: Muzeum Lin"
    assert extract(doc)["Odwolujacy"][0]["nazwa"] == "Kontakt 24 sp. z o.o."


def test_register_with_filing_quoted_on_a_separate_row():
    doc = "SPIS KORESPONDENCJI\nODWOŁANIA\nOdwołujący: Kosz\nZamawiający: Kula\nTreść wpisu:\nWnoszę odwołanie."
    assert classify([doc]) is None


def test_wrapped_plain_title_stops_at_the_following_field():
    doc = "Nazwa postępowania: Budowa mostu\nnad rzeką\nNumer postępowania: MR/61"
    assert extract(doc)["ZamowieniePubliczne"]["tytul"] == "Budowa mostu nad rzeką"
