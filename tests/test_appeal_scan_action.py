import pytest

from kio2json import appeal


def extract_action(pages, scanned):
    from kio2json.appeal_scan_action import apply_action

    record = appeal.extract("\n".join(pages))
    apply_action(record, pages, scanned)
    return record["OdwolanieKIO"]


def test_challenged_omission_and_notification_before_unrelated_legal_charge():
    pages = [
        "Wnosze odwolanie wobec:\nI. zaniechania odrzucenia oferty konkurenta,",
        (
            "o czym spółkę poinformowano pismem z 9 grudnia 2031 roku;\n"
            "2. wyboru oferty w dniu 10 grudnia 2031 r.\nZamawiającemu zarzucam odrzucenie oferty."
        ),
    ]
    action = extract_action(pages, {1, 2})
    assert action["czynnosc_powod_id"] == 7
    assert action["czynnosc_opis"] == appeal.REASONS[7]
    assert action["czynnosc_dzien"] == "2031-12-09"


def test_junk_around_filing_line_and_missing_stamp_date():
    header = "| Nowa Ruda, dnia 8 listopada 2033 roku *\nPrezes Izby"
    action = extract_action([header], {1})
    assert action["data"] == "2033-11-08"
    assert action["miejscowosc"] == "Nowa Ruda"


def test_unknown_first_action_does_not_borrow_a_dated_second_item():
    pages = ["Wnosze odwolanie wobec:\n1. zatrzymania wadium;\n2. odrzucenia oferty w dniu 9 grudnia 2031 r."]
    action = extract_action(pages, {1})
    assert action["czynnosc_powod_id"] is None
    assert action["czynnosc_dzien"] is None


def test_native_filing_header_and_first_action_keep_base_rules():
    pages = [
        ("| Nowa Ruda, dnia 8 listopada 2033 roku *\nWnosze odwolanie wobec: odrzucenia oferty w dniu 1 marca 2032 r."),
        "Załącznik bez daty",
    ]
    original = appeal.extract("\n".join(pages))["OdwolanieKIO"]
    assert extract_action(pages, {2}) == original


def test_publication_of_contract_terms_precedes_specification_reference():
    pages = [
        (
            "Wnoszę odwołanie wobec:\n1. projektowanych postanowień umowy (załącznik do SWZ)\n"
            "opublikowanych w dniu 7 września 2034 roku; 2. odrzucenia oferty."
        )
    ]
    action = extract_action(pages, {1})
    assert action["czynnosc_powod_id"] == 12
    assert action["czynnosc_dzien"] == "2034-09-07"


def test_native_date_on_continuation_cannot_be_used_by_ocr_relaxation():
    pages = ["Wnosze odwolanie wobec: odrzucenia oferty, o ktorej", "poinformowano w dniu 9 grudnia 2031 r."]
    action = extract_action(pages, {1})
    assert action["czynnosc_powod_id"] == 1
    assert action["czynnosc_dzien"] is None


def test_date_of_a_submitted_offer_is_distinct_from_notice_of_rejection():
    pages = [
        (
            "Wnosze odwolanie wobec: odrzucenia oferty złożonej w dniu 13.01.2030 r., "
            "o którym zamawiający zawiadomił w dniu 17.01.2030 r."
        )
    ]
    assert extract_action(pages, {1})["czynnosc_dzien"] == "2030-01-17"


def test_header_keeps_period_after_year_abbreviation():
    pages = ["* Duszniki-Zdrój, dnia 19.12.2030 r. |\nPrezes Izby"]
    assert extract_action(pages, {1})["miejscowosc"] == "Duszniki-Zdrój"


def test_specific_first_allegation_survives_a_generic_introductory_reference():
    text = (
        "Wnoszę odwołanie wobec postanowień SIWZ.\n"
        "Zamawiającemu zarzucam naruszenie ustawy poprzez opis przedmiotu zamówienia sprzeczny z prawem."
    )
    action = extract_action([text], {1})
    assert action["czynnosc_powod_id"] == 11


def test_nested_numbering_preserves_the_omission():
    text = (
        "Wnoszę odwołanie wobec działań w tym postępowaniu:\n"
        "I. Zaniechania:\n(1) wykluczenia wykonawcy z postępowania.\n(2) udzielenia odpowiedzi."
    )
    assert extract_action([text], {1})["czynnosc_powod_id"] == 8


def test_communication_date_takes_precedence_over_preparation_of_decision():
    text = (
        "Odwołujący zarzuca naruszenie przepisów poprzez odrzucenie oferty.\n"
        "Czynność odrzucenia oferty miała miejsce 3 lutego 2037 r., "
        "a do publicznej wiadomości została przekazana w dniu 5 lutego 2037 r."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == "2037-02-05"


def test_subject_specific_publication_takes_precedence_over_contract_notice():
    text = (
        "Ogłoszenie o zamówieniu opublikowano dnia 11 lipca 2038 r.\n"
        "Ogłoszenie SIWZ w dniu 13. 07. 2038 roku.\n"
        "Wnosi niniejszym odwolanie od sporządzenia specyfikacji warunków zamówienia."
    )
    action = extract_action([text], {1})
    assert action["czynnosc_powod_id"] == 4
    assert action["czynnosc_dzien"] == "2038-07-13"


def test_first_form_allegation_and_header_take_precedence_over_summary():
    text = (
        "miejscowość: Czerwieńsk „2036-01-22\n"
        "Wskazanie czynności: badanie i ocena ofert; wybór oferty.\n"
        "Zwięzłe przedstawienie zarzutów: zarzucam naruszenie ustawy: "
        "1) art. 204 poprzez odrzucenie oferty. 2) art. 205 poprzez zaniechanie odrzucenia oferty.\n"
        "Dnia 18 stycznia 2036 r. Odwołujący otrzymał informację o odrzuceniu oferty."
    )
    action = extract_action([text], {1})
    assert (action["miejscowosc"], action["data"]) == ("Czerwieńsk", "2036-01-22")
    assert action["czynnosc_powod_id"] == 1
    assert action["czynnosc_dzien"] == "2036-01-18"


def test_publication_of_notice_does_not_date_an_offer_rejection():
    text = (
        "Ogłoszenie o zamówieniu zamieszczono w dniu 12 marca 2030 r.\n"
        "Zarzucam Zamawiającemu, że dokonał bezzasadnego odrzucenia oferty."
    )
    action = extract_action([text], {1})
    assert action["czynnosc_powod_id"] == 1
    assert action["czynnosc_dzien"] is None


@pytest.mark.parametrize("gap", [" ", "\n  "])
def test_notice_for_another_action_does_not_date_the_first(gap):
    text = (
        "Wnoszę odwołanie wobec: 1. odrzucenia oferty.\n2. wyboru oferty.\n"
        f"W dniu 8 maja 2039 r. Odwołujący otrzymał informację o{gap}wyborze oferty."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] is None


def test_notice_of_publication_dates_a_challenge_to_commencement():
    text = (
        "Wnoszę odwołanie na czynność polegającą na wszczęciu nowego postępowania.\n"
        "Zarzucam naruszenie poprzez zaniechanie unieważnienia postępowania.\n"
        "Zachowanie terminu do wniesienia odwołania:\n"
        "Postępowanie opublikowano w biuletynie w dniu 24 czerwca 2032 r."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == "2032-06-24"


def test_matching_transmission_headers_confirm_the_damaged_year_only():
    pages = [
        (
            "2030-09-14 08:51 kancelaria\nSulejówek, dnia 14 września 2080 roku\n"
            "Wnosze odwolanie wobec: odrzucenia oferty w dniu 11 września 2030 r."
        ),
        "2030-09-14 08:53 kancelaria\nDruga strona.",
    ]
    assert extract_action(pages, {1, 2})["data"] == "2030-09-14"
    assert extract_action(pages[:1], {1})["data"] == "2080-09-14"


def test_publication_of_explicitly_challenged_contract_notice_is_grounded():
    text = (
        "Data opublikowania w Dz. U. UE: 11 sierpnia 2031 r.\nWnoszę odwołanie wobec postanowień "
        "ogłoszenia o zamówieniu oraz specyfikacji warunków zamówienia."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == "2031-08-11"


def test_locally_reported_notification_postdates_the_decision_itself():
    text = (
        "Wnoszę odwołanie wobec:\n1. odrzucenia oferty w dniu 2 czerwca 2032 r., "
        "o którym poinformowano wykonawcę w dniu 4 czerwca 2032 r.;\n"
        "2. zaniechania wykluczenia wykonawcy."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == "2032-06-04"


def test_roman_numeral_stops_before_independent_second_act():
    text = "Wnoszę odwołanie wobec:\nI. zatrzymania wadium.\nII. odrzucenia oferty w dniu 6 maja 2031 r."
    action = extract_action([text], {1})
    assert action["czynnosc_powod_id"] is None
    assert action["czynnosc_dzien"] is None


@pytest.mark.parametrize(
    ("subject", "expected"), [("odrzuceniu oferty", "2031-06-04"), ("wyborze oferty", "2031-06-02")]
)
def test_separate_notification_must_name_the_first_decision(subject, expected):
    text = (
        "Wnoszę odwołanie wobec:\n1. odrzucenia oferty w dniu 2 czerwca 2031 r.;\n2. wyboru oferty.\n"
        f"W dniu 4 czerwca 2031 r. Odwołujący otrzymał informację o\n  {subject}."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == expected


def test_separate_notice_of_another_bidders_rejection_keeps_the_first_date():
    text = (
        "Wnoszę odwołanie wobec:\n1. odrzucenia oferty spółki Alfa w dniu 2 czerwca 2031 r.;\n"
        "2. odrzucenia oferty spółki Beta.\n"
        "W dniu 4 czerwca 2031 r. Odwołujący otrzymał informację o odrzuceniu oferty spółki Beta."
    )
    assert extract_action([text], {1})["czynnosc_dzien"] == "2031-06-02"
