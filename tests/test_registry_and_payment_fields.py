"""Field ownership in legal letterheads and payment detail tables."""

from kio2json import appeal, bank_transfer


def test_repeated_register_key_links_a_capital_and_tax_row():
    header = "Odwołujący: Fikcyjna spółka\nul. Górna 8\nKRS 0000000123\nZamawiający: Przykładowa gmina"
    footer = "KRS 0000000123, kapitał zakładowy 8000 PLN\nRegon: 123456785 NIP: 123-45-67-890"
    party = appeal.extract(header + "\n" + footer)["Odwolujacy"][0]
    assert (party["regon"], party["nip"]) == ("123456785", "1234567890")
    other = footer.replace("0000000123", "0000000456")
    assert appeal.extract(header + "\n" + other)["Odwolujacy"][0]["nip"] is None


def test_wrapped_reference_label_and_explicit_operation_id():
    assert appeal.extract("Znak\nsprawy: AB/37")["ZamowieniePubliczne"]["numer_postepowania"] == "AB/37"
    fields = bank_transfer.extract("Szczegóły Naprawa hali\nReferencje klienta\nID operacji WZ/9172")["przelew_bankowy"]
    assert (fields["numer_transakcji"], fields["tytul"]) == ("WZ/9172", "Naprawa hali")


def test_scan_self_identification_restores_company_and_links_its_footer():
    from kio2json.ocr_extract import extract_scanned_appeal

    pages = [
        "ODWOŁANIE\nOdwołujący: Lesny Pomost Spółka Akcyjna\nul. Dolna 1\nUzasadnienie:",
        (
            "Leśny Pomost Spółka Akcyjna z siedzibą w Gdyni (dalej „Odwołujący”) wnosi odwołanie.\n"
            "Leśny Pomost S.A., ul. Dolna 1\nKRS 0000000123 REGON 123456785\n"
            "Inna Firma S.A.\nKRS 0000000456"
        ),
    ]
    record = extract_scanned_appeal(pages, {1, 2}, None, [])
    party = record["Odwolujacy"][0]
    assert party["nazwa"] == "Leśny Pomost Spółka Akcyjna"
    assert party["regon"] == "123456785"
    assert party["krs"] is None


def test_later_owners_and_empty_details_do_not_supply_fields():
    header = "Odwołujący: Fikcyjna spółka\nul. Górna 8\nKRS 0000000123\nUzasadnienie:"
    body = "KRS 0000000123, NIP: 1234567890, konsorcjant: Inna Spółka, REGON 123456785"
    assert appeal.extract(header + "\n" + body)["Odwolujacy"][0]["regon"] is None
    assert (
        bank_transfer.extract("ID operacji T/61\nSzczegóły operacji:\nReferencje klienta: brak")["przelew_bankowy"][
            "tytul"
        ]
        is None
    )


def test_named_registry_footer_stops_at_another_party():
    from kio2json.appeal_scan_parties import _registry_footer

    party = {"nazwa": "Srebrny Kamień S.A.", "nip": None, "krs": None, "regon": None}
    _registry_footer(party, ["Srebrny Kamień S.A.\nPełnomocnik: Inna Firma S.A., REGON 123456785"])
    assert party["regon"] is None


def test_same_company_name_with_conflicting_identifier_cannot_supply_tax_id():
    from kio2json.appeal_scan_parties import _registry_footer

    party = {"nazwa": "Srebrny Kamień S.A.", "nip": None, "krs": "0000000123", "regon": None}
    _registry_footer(party, ["Srebrny Kamień S.A.\nKRS 0000000999 REGON 123456785"])
    assert party["regon"] is None
    fields = bank_transfer.extract("ID operacji H/576\nSzczegóły transakcji\nReferencje klienta: Brak")
    assert fields["przelew_bankowy"]["tytul"] is None


def test_fee_label_is_not_a_remittance_title():
    fields = bank_transfer.extract("Tytuł: Opłata za przelew: 0,00 PLN\nKwota: 69,00 PLN")
    assert fields["przelew_bankowy"]["tytul"] is None
