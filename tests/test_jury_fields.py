"""Independent excerpts exercising the jury's selective, page-grounded fill."""

from copy import deepcopy

import pytest

from kio2json import appeal, bank_transfer, llm, power_of_attorney


def enrich(monkeypatch, doc, record, pages, **answers):
    from kio2json import jury_fields

    calls = []

    def answer(schema, instructions, prompt, **options):
        assert options["single_request"]
        calls.append(set(schema.model_fields))
        return schema.model_validate({key: answers.get(key) for key in schema.model_fields})

    monkeypatch.setattr(llm, "structured", answer)
    jury_fields.enrich(doc, record, pages)
    return calls


def test_semantic_first_allegation_does_not_need_a_dictionary_keyword(monkeypatch):
    rules = appeal.extract("")
    clause = "Zamawiający 12.05.2025 pozostawił w grze ofertę mimo obowiązku jej eliminacji"
    later = "Zarzut drugi: 18.05.2025 usunięto oferenta."
    calls = enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause + ".\n" + later],
        pierwszy_zarzut={"reason_id": 7, "act_quote": clause, "dated_act_quote": clause},
    )
    assert len(calls) == 1
    assert rules["OdwolanieKIO"]["czynnosc_powod_id"] == 7
    assert rules["OdwolanieKIO"]["czynnosc_opis"] == "Zaniechanie odrzucenia oferty"
    # The semantic reason can be supported even when the date cannot be independently
    # tied to a recognized act or its notice.
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_charge_quotes_cannot_cross_pages_or_use_a_later_allegation(monkeypatch):
    rules = appeal.extract("")
    before = deepcopy(rules)
    enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: Zamawiający pozostawił", "w grze ofertę.\nZarzut drugi: usunięto oferenta."],
        pierwszy_zarzut={"reason_id": 7, "act_quote": "pozostawił\nw grze ofertę", "dated_act_quote": None},
    )
    assert rules == before


def test_freeform_counsel_belongs_to_appellant_only(monkeypatch):
    rules = appeal.extract("Odwołujący: Most S.A.\nZamawiający: Port Morski")
    rules["Odwolujacy"][0]["przez-pelnomocnika"] = 1
    page = (
        "Odwołujący: Most S.A.\nW imieniu odwołującego występuje adwokat Ada Lato\n"
        "Kancelaria nad Rzeką\nadres poczty: ada@example.org\n"
        "Pełnomocnik zamawiającego: adwokat Jan Luty\njan@example.org"
    )
    flag = "W imieniu odwołującego występuje adwokat Ada Lato"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        [page],
        reprezentacja=flag,
        imie_nazwisko="Ada Lato",
        kancelaria="Kancelaria nad Rzeką",
        mail="jan@example.org",
    )
    row = rules["Odwolujacy"][0]
    assert row["przez-pelnomocnika"] == 1
    assert row["pelnomocnik"] == {"imie_nazwisko": "Ada Lato", "nazwa": "Kancelaria nad Rzeką", "mail": None}


def test_explicit_self_representation_guard(monkeypatch):
    page = "Odwołujący: Most S.A.\nOdwołujący działa samodzielnie.\nPełnomocnik zamawiającego: radca prawny Ada Lato"
    rules = appeal.extract(page)
    before = deepcopy(rules)
    enrich(monkeypatch, "appeal", rules, [page], reprezentacja="radca prawny Ada Lato", imie_nazwisko="Ada Lato")
    assert rules == before


def test_party_title_and_separate_page_owner(monkeypatch):
    rules = appeal.extract("")
    pages = ["Odwołujący: Most S.A.\nZamawiający: Gmina Port\n", "Postępowanie prowadzone pod nazwą „Nowe nabrzeże”"]
    enrich(monkeypatch, "appeal", rules, pages, odwolujacy="Most S.A.", zamawiajacy="Most S.A.", tytul="Nowe nabrzeże")
    assert rules["Odwolujacy"][0]["nazwa"] == "Most S.A."
    assert rules["Zamawiajacy"] == []
    assert rules["ZamowieniePubliczne"]["tytul"] == "Nowe nabrzeże"


def test_grant_does_not_take_a_signer_as_recipient(monkeypatch):
    rules = power_of_attorney.extract("")
    page = "PEŁNOMOCNICTWO\nMocodawca: Wysoka Fala S.A.\nOsoba umocowana: Ada Lato\nPodpisujący: Jan Luty"
    enrich(monkeypatch, "power_of_attorney", rules, [page], mocodawca="Wysoka Fala S.A.", pelnomocnik="Jan Luty")
    assert rules["mocodawca"][0]["data"]["nazwa"] == "Wysoka Fala S.A."
    assert rules["pelnomocnicy"] == []


def test_transfer_respects_fee_section_and_populated_account(monkeypatch):
    page = "POTWIERDZENIE PRZELEWU\nPrzekazana kwota: 48,10 PLN\nSzczegóły prowizji\nKwota: 4,10 PLN"
    rules = bank_transfer.extract("")
    rules["przelew_bankowy"]["na_rachunek"] = "61109010140000071219812874"
    calls = enrich(monkeypatch, "bank_transfer", rules, [page], kwota="4,10 PLN", na_rachunek="other")
    assert len(calls) == 1 and "na_rachunek" not in calls[0]
    assert rules["przelew_bankowy"]["kwota"] is None
    enrich(monkeypatch, "bank_transfer", rules, [page], kwota="48,10 PLN")
    assert rules["przelew_bankowy"]["kwota"] == 48.1


def test_transfer_quote_cannot_drop_the_leading_group_of_a_printed_amount(monkeypatch):
    rules = bank_transfer.extract("")
    enrich(monkeypatch, "bank_transfer", rules, ["Przekazana kwota: 4 048,10 PLN"], kwota="048,10 PLN")
    assert rules["przelew_bankowy"]["kwota"] is None


def test_anonymous_filing_can_identify_parties_in_narrative(monkeypatch):
    page = "Odwołanie niniejsze wnosi wykonawca Fala S.A.\nPostępowanie prowadzi Gmina Port."
    rules = appeal.extract("")
    enrich(monkeypatch, "appeal", rules, [page], odwolujacy="Fala S.A.", zamawiajacy="Gmina Port")
    assert rules["Odwolujacy"][0]["nazwa"] == "Fala S.A."
    assert rules["Zamawiajacy"][0]["nazwa"] == "Gmina Port"


def test_counsel_may_identify_client_by_name(monkeypatch):
    rules = appeal.extract("Odwołujący: Most S.A.\nZamawiający: Gmina Port")
    rules["Odwolujacy"][0]["przez-pelnomocnika"] = None
    opening = "Radca prawny Ada Lato, działając w imieniu Most S.A., wnosi odwołanie."
    calls = enrich(monkeypatch, "appeal", rules, [opening], reprezentacja=opening, imie_nazwisko="Ada Lato")
    assert "imie_nazwisko" not in calls[0]
    row = rules["Odwolujacy"][0]
    assert row["przez-pelnomocnika"] == 1
    assert row["pelnomocnik"]["imie_nazwisko"] is None


def test_later_allegation_cannot_supply_missing_first_act_after_page_break(monkeypatch):
    rules = appeal.extract("")
    pages = ["Zarzut pierwszy:", "Zarzut drugi: stwierdzono brak usunięcia wykonawcy."]
    calls = enrich(
        monkeypatch,
        "appeal",
        rules,
        pages,
        pierwszy_zarzut={"reason_id": 8, "act_quote": "brak usunięcia wykonawcy", "dated_act_quote": None},
    )
    assert not calls
    assert rules["OdwolanieKIO"]["czynnosc_powod_id"] is None


def test_populated_reason_and_date_are_final(monkeypatch):
    rules = appeal.extract("")
    header = rules["OdwolanieKIO"]
    header.update(czynnosc_powod_id=4, czynnosc_opis=appeal.REASONS[4], czynnosc_dzien="2025-03-03")
    clause = "Pozostawiono w grze ofertę mimo obowiązku jej eliminacji"
    assert not enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause],
        pierwszy_zarzut={"reason_id": 7, "act_quote": clause, "dated_act_quote": None},
    )
    assert header["czynnosc_powod_id"] == 4
    assert header["czynnosc_dzien"] == "2025-03-03"


def test_exact_action_label_and_checksum_fields_are_preserved(monkeypatch):
    page = (
        "Zaskarżona czynność: odrzucenie oferty\nData czynności: 03.03.2025\n"
        "Zarzut pierwszy: Pozostawiono w grze ofertę mimo obowiązku jej eliminacji"
    )
    rules = appeal.extract(page)
    before = deepcopy(rules)
    assert rules["OdwolanieKIO"]["czynnosc_powod_id"] == 1
    assert not enrich(monkeypatch, "appeal", rules, [page])
    assert rules == before


def test_document_ending_in_an_attachment_cannot_supply_its_counsel(monkeypatch):
    rules = appeal.extract("Odwołujący: Most S.A.")
    pages = ["Odwołujący: Most S.A.\nZałączniki:", "Pełnomocnik odwołującego: adwokat Jan Luty"]
    assert not enrich(monkeypatch, "appeal", rules, pages)
    assert rules["Odwolujacy"][0]["przez-pelnomocnika"] == 0


def test_reference_suffix_and_second_receipt_are_rejected(monkeypatch):
    rules = bank_transfer.extract("")
    enrich(monkeypatch, "bank_transfer", rules, ["Numer transakcji: REP/17"], numer_transakcji="17")
    assert rules["przelew_bankowy"]["numer_transakcji"] is None
    pages = ["Potwierdzenie przelewu\nPrzekazana kwota: 48,10 PLN\nPotwierdzenie przelewu\nNumer transakcji: T/2"]
    assert not enrich(monkeypatch, "bank_transfer", rules, pages)


def test_existing_project_title_and_party_never_trigger_model_choice(monkeypatch):
    page = "Odwołujący: Biały Brzeg\nPrzedmiot zamówienia: Budowa kładki w ramach projektu pn. „Port”"
    rules = appeal.extract(page)
    rules["ZamowieniePubliczne"]["tytul"] = "Port"
    rules["Odwolujacy"][0]["nazwa"] = "Biały Brzeg Adres siedziby"
    before = deepcopy(rules)
    assert not enrich(monkeypatch, "appeal", rules, [page], tytul="Budowa kładki", odwolujacy="Biały Brzeg")
    assert rules == before


def test_unlabelled_transfer_prior_is_final(monkeypatch):
    rules = bank_transfer.extract("")
    rules["przelew_bankowy"]["kwota"] = 9.99
    page = "Przekazano 9,99 PLN\nKwota przelewu: 10,99 PLN"
    assert not enrich(monkeypatch, "bank_transfer", rules, [page], kwota="10,99 PLN")
    assert rules["przelew_bankowy"]["kwota"] == 9.99


def test_other_party_or_quoted_pleading_cannot_supply_counsel(monkeypatch):
    page = (
        "Odwołujący: Most S.A.\nOdpowiedź zamawiającego:\n"
        "Zacytowano: „W imieniu odwołującego występuje adwokat Jan Luty”."
    )
    rules = appeal.extract("Odwołujący: Most S.A.")
    calls = enrich(monkeypatch, "appeal", rules, [page], reprezentacja="adwokat Jan Luty", imie_nazwisko="Jan Luty")
    assert not calls


def test_first_act_date_cannot_be_a_separate_deadline_in_the_same_sentence(monkeypatch):
    rules = appeal.extract("")
    clause = "Odwołujący kwestionuje usunięcie oferty, a termin złożenia wniosku mija 03.05.2025"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause],
        pierwszy_zarzut={"reason_id": 1, "act_quote": "usunięcie oferty", "dated_act_quote": clause},
    )
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_bare_legal_reference_cannot_support_a_reason_id(monkeypatch):
    rules = appeal.extract("")
    clause = "naruszenie art. 42 ust. 2 ustawy przez niezgodne z prawem czynności"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause],
        pierwszy_zarzut={"reason_id": 7, "act_quote": "art. 42 ust. 2", "dated_act_quote": None},
    )
    assert rules["OdwolanieKIO"]["czynnosc_powod_id"] is None


def test_wrong_contact_cannot_be_attached_to_an_already_identified_lawyer(monkeypatch):
    rules = appeal.extract("Odwołujący: Most S.A.")
    row = rules["Odwolujacy"][0]
    row["przez-pelnomocnika"] = 1
    row["pelnomocnik"]["imie_nazwisko"] = "Ada Lato"
    page = "Pełnomocnik odwołującego: radca prawny Jan Luty\njan@example.org"
    enrich(monkeypatch, "appeal", rules, [page], mail="jan@example.org")
    assert row["pelnomocnik"]["mail"] is None


def test_missing_owner_cannot_borrow_its_neighbor_in_an_inline_grant(monkeypatch):
    rules = power_of_attorney.extract("")
    page = "Mocodawca: Biała Fala S.A. udziela pełnomocnictwa Adzie Lato."
    enrich(monkeypatch, "power_of_attorney", rules, [page], mocodawca="Adzie Lato")
    assert rules["mocodawca"] == []


def test_exact_field_on_another_page_protects_purchase_title(monkeypatch):
    page = "Przedmiot zamówienia: Budowa kładki w ramach projektu pn. „Port”\nZnak sprawy: P/4"
    rules = appeal.extract("")
    rules["ZamowieniePubliczne"]["tytul"] = "Port"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        [page, "Nazwa postępowania: Port"],
        tytul="Budowa kładki w ramach projektu pn. „Port”",
    )
    assert rules["ZamowieniePubliczne"]["tytul"] == "Port"


def test_bid_submission_cannot_date_challenged_act(monkeypatch):
    rules = appeal.extract("")
    clause = "Kwestionuję usunięcie oferty, którą wykonawca złożył 03.05.2025"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause],
        pierwszy_zarzut={"reason_id": 1, "act_quote": "usunięcie oferty", "dated_act_quote": clause},
    )
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] is None


@pytest.mark.parametrize("separator", [":", " –", ""])
def test_counsel_block_ends_at_other_owners_contact(monkeypatch, separator):
    rules = appeal.extract("Odwołujący: Most S.A.")
    rules["Odwolujacy"][0]["przez-pelnomocnika"] = 1
    page = f"W imieniu odwołującego występuje adwokat Ada Lato\nE-mail zamawiającego{separator} biuro@example.org"
    calls = enrich(monkeypatch, "appeal", rules, [page], reprezentacja="adwokat Ada Lato", mail="biuro@example.org")
    assert calls and "mail" not in calls[0]


def test_rules_full_label_grammar_protects_amount_and_day(monkeypatch):
    page = "Data operacji przelewu: 03.05.2025\nData realizacji: 04.05.2025\nKwota przelewu: 10,00 EUR\nSuma przelewu: 20,00 PLN"
    rules = bank_transfer.extract(page)
    before = deepcopy(rules)
    assert not enrich(monkeypatch, "bank_transfer", rules, [page], data_operacji="04.05.2025", kwota="20,00 PLN")
    assert rules == before


def test_opening_date_cannot_date_a_subsequent_coordinated_act(monkeypatch):
    rules = appeal.extract("")
    later = "pozostawił w grze ofertę mimo obowiązku jej eliminacji"
    clause = "Zamawiający 03.05.2025 otworzył oferty i tydzień później " + later
    for quote in [later, clause]:
        enrich(
            monkeypatch,
            "appeal",
            rules,
            ["Zarzut pierwszy: " + clause],
            pierwszy_zarzut={"reason_id": 7, "act_quote": quote, "dated_act_quote": clause},
        )
        assert rules["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_opposing_party_section_cannot_authorize_counsel(monkeypatch):
    rules = appeal.extract("Odwołujący: Most S.A.")
    pages = ["Przystępujący: Drugi Podmiot\nW imieniu odwołującego występuje adwokat Jan Luty"]
    assert not enrich(monkeypatch, "appeal", rules, pages, reprezentacja="adwokat Jan Luty")


def test_date_of_opening_cannot_date_a_later_nominal_act(monkeypatch):
    rules = appeal.extract("")
    clause = "Zamawiający 03.05.2025 otworzył oferty przed późniejszym odrzuceniem oferty"
    enrich(
        monkeypatch,
        "appeal",
        rules,
        ["Zarzut pierwszy: " + clause],
        pierwszy_zarzut={"reason_id": 1, "act_quote": clause, "dated_act_quote": clause},
    )
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] is None


def test_date_from_filing_sentence_mentions_the_same_challenged_act(monkeypatch):
    rules = appeal.extract("")
    intro = "Wnoszę odwołanie wobec odrzucenia oferty dokonanego dnia 09.04.2025."
    charge = "Zarzut pierwszy: odrzucenie oferty wbrew warunkom procedury."
    enrich(
        monkeypatch,
        "appeal",
        rules,
        [intro + "\n" + charge],
        pierwszy_zarzut={
            "reason_id": 1,
            "act_quote": "odrzucenie oferty",
            "dated_act_quote": "odrzucenia oferty dokonanego dnia 09.04.2025",
        },
    )
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] == "2025-04-09"


@pytest.mark.parametrize(
    "other_event",
    [
        "i przekazanie protokołu kontroli dopiero dnia 03.05.2025",
        "po przekazaniu protokołu kontroli dnia 03.05.2025",
        "wraz z przekazaniem protokołu kontroli dnia 03.05.2025",
        "dokonanego dnia 01.05.2025 i przekazanie protokołu 03.05.2025",
    ],
)
def test_delivery_of_an_unrelated_document_does_not_date_rejection(monkeypatch, other_event):
    clause = "bezpodstawne odrzucenie oferty " + other_event
    page = "Zarzut pierwszy: " + clause + "."
    rules = appeal.extract(page)
    before = rules["OdwolanieKIO"]["czynnosc_dzien"]
    enrich(
        monkeypatch,
        "appeal",
        rules,
        [page],
        pierwszy_zarzut={"reason_id": 1, "act_quote": "odrzucenie oferty", "dated_act_quote": clause},
    )
    assert rules["OdwolanieKIO"]["czynnosc_dzien"] == before


def test_personal_grantor_cannot_be_written_as_business_name(monkeypatch):
    page = "PEŁNOMOCNICTWO\nMocodawca: Jan Luty\nOsoba umocowana: Ada Lato"
    rules = power_of_attorney.extract(page)
    prior = deepcopy(rules["mocodawca"])
    calls = enrich(monkeypatch, "power_of_attorney", rules, [page], mocodawca="Jan Luty")
    assert all("mocodawca" not in fields for fields in calls)
    assert rules["mocodawca"] == prior
