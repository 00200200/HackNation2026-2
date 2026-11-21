"""Extractors and classifier on small synthetic texts (no organizer data needed)."""

import sys
from unittest.mock import MagicMock

import pytest

from kio2json import __main__ as cli
from kio2json import appeal, bank_transfer, pdf_text, power_of_attorney
from kio2json.classify import classify
from kio2json.common import registry_ids, to_iso

APPEAL = """Kraków, dnia 7 września 2026 r.
Zamawiający:
Gmina Przykładowa
ul. Ratuszowa 1, 30-001 Kraków
NIP: 9990000001, REGON: 999000001
Odwołujący:
Firma Testowa sp. z o.o.
ul. Długa 2, 30-002 Kraków
KRS: 9990000002, NIP: 9990000003, REGON: 999000003
reprezentowany przez: adw. Jan Kowalski
adres do korespondencji: Kancelaria Kowalski, ul. Krótka 3, 30-003 Kraków
tel. 000 000 000, e-mail: jan@kancelaria.example
dotyczy: postępowania pn. „Dostawa testowa”, nr referencyjny: ZP.1.2026, ogłoszenie nr 2026/BZP 00999001
ODWOŁANIE
Działając w imieniu Firma Testowa sp. z o.o., wnoszę odwołanie wobec czynności polegających na:
1) zaniechaniu wezwania, mimo że Zamawiający w dniu 1 sierpnia 2026 r. wzywał do wyjaśnień ceny.
Zamawiający w dniu 28 sierpnia 2026 roku odrzucił ofertę Odwołującego. Uprzednio wezwał do wyjaśnień.
Zarzut nr 1 – bezpodstawnego odrzucenia oferty;
Zarzut nr 2 – zaniechania odrzucenia oferty innego wykonawcy;
"""


def test_classify_routes_by_content():
    assert classify([APPEAL]) == "appeal"
    assert classify([APPEAL.upper()]) == "appeal"
    assert classify(["P E Ł N O M O C N I C T W O\nudzielam pełnomocnictwa adw. Jan Kowalski"]) == "power_of_attorney"
    assert (
        classify(
            [
                "Potwierdzenie przelewu\nKwota: 14,20 PLN\n11 1111 1111 1111 1111 1111 1111\n22 2222 2222 2222 2222 2222 2222"
            ]
        )
        == "bank_transfer"
    )


def test_classify_rejects_other_documents():
    assert classify([]) is None
    assert classify([""]) is None
    assert classify(["WYROK\nSygn. akt KIO 1/26\nODWOŁANIE\nOdwołujący: X"]) is None
    assert classify(["Przelew na rachunek 11 1111 1111 1111 1111 1111 1111"]) is None  # one account only


def test_appeal_fields():
    result = appeal.extract(APPEAL)
    assert result["OdwolanieKIO"] == {
        "data": "2026-09-07",
        "czynnosc_dzien": "2026-08-28",
        "czynnosc_powod_id": 1,
        "czynnosc_opis": "Decyzja o odrzuceniu oferty",
        "miejscowosc": "Kraków",
    }
    assert result["Odwolujacy"] == [
        {
            "krs": "9990000002",
            "nazwa": "Firma Testowa sp. z o.o.",
            "nip": "9990000003",
            "regon": "999000003",
            "przez-pelnomocnika": 1,
            "pelnomocnik": {
                "imie_nazwisko": "Jan Kowalski",
                "nazwa": "Kancelaria Kowalski",
                "mail": "jan@kancelaria.example",
            },
        }
    ]
    assert result["Zamawiajacy"] == [
        {
            "krs": None,
            "nazwa": "Gmina Przykładowa",
            "nip": "9990000001",
            "regon": "999000001",
            "prowadzacy_postepowanie": None,
        }
    ]
    assert result["ZamowieniePubliczne"] == {
        "numer_bzp": "2026/BZP00999001",
        "numer_postepowania": "ZP.1.2026",
        "numer_ted": None,
        "tytul": "Dostawa testowa",
    }


def test_appeal_with_uppercase_party_labels_and_dn_abbreviation():
    text = (
        APPEAL.replace("Zamawiający:", "ZAMAWIAJĄCY:").replace("Odwołujący:", "ODWOŁUJĄCY:").replace("dnia 7", "dn. 7")
    )
    result = appeal.extract(text)
    assert result["Odwolujacy"][0]["nazwa"] == "Firma Testowa sp. z o.o."
    assert result["Zamawiajacy"][0]["nazwa"] == "Gmina Przykładowa"
    assert result["OdwolanieKIO"]["data"] == "2026-09-07"


def test_power_of_attorney_binds_signers_to_their_principal():
    text = """PEŁNOMOCNICTWO
Konsorcjum: 1) Alfa Budowa sp. z o.o., KRS 9990000011, NIP 9990000012; 2) Beta Instalacje sp.j., KRS
9990000021, NIP 9990000022 udzielają pełnomocnictwa: adw. Anna Nowak, PESEL 85010112345, r. pr. Piotr Lis.
W imieniu Alfa Budowa sp. z o.o.:
............................................
Marek Zielony
Prezes Zarządu
W imieniu Beta Instalacje sp.j.:
............................................
Ewa Biała
Wspólnik
Pełnomocnictwo przyjmuję:
adw. Anna Nowak
"""
    result = power_of_attorney.extract(text)
    assert [(m["data"]["nazwa"], [s["imie_nazwisko"] for s in m["podpisujacy"]]) for m in result["mocodawca"]] == [
        ("Alfa Budowa sp. z o.o.", ["Marek Zielony"]),
        ("Beta Instalacje sp.j.", ["Ewa Biała"]),
    ]
    assert result["pelnomocnicy"] == [
        {"imie_nazwisko": "Anna Nowak", "pesel": "85010112345"},
        {"imie_nazwisko": "Piotr Lis", "pesel": None},
    ]


def test_power_of_attorney_accepts_capitalized_and_spelled_out_legal_forms():
    for name in ("LUMETRA Sp. z o.o.", "Lunafik Spółka Akcyjna", "Torwika SP. Z O.O."):
        text = f"PEŁNOMOCNICTWO\n{name}, KRS 9990000471, NIP 1234567890\nudziela pełnomocnictwa adw. Jan Kowalski"
        assert [m["data"]["nazwa"] for m in power_of_attorney.extract(text)["mocodawca"]] == [name]


def test_bank_transfer_fields():
    text = """Potwierdzenie przelewu
Rachunek nadawcy: PL11 1111 1111 1111 1111 1111 1111
Rachunek odbiorcy: PL22 2222 2222 2222 2222 2222 2222
Kwota: 15 000,00 PLN
Data operacji: 9 października 2025
Tytuł: wpis od odwołania
w postępowaniu ZP.1.2025
Numer referencyjny: ABC123456789
Opłata: 0,00 PLN
"""
    assert bank_transfer.extract(text)["przelew_bankowy"] == {
        "data_operacji": "2025-10-09",
        "kwota": 15000.0,
        "na_rachunek": "22222222222222222222222222",
        "numer_transakcji": "ABC123456789",
        "tytul": "wpis od odwołania w postępowaniu ZP.1.2025",
        "z_rachunku": "11111111111111111111111111",
    }


def test_bank_transfer_account_roles_follow_labels_not_order():
    sender, recipient = "1" * 26, "2" * 26
    recipient_first = f"Przelew\nNa rachunek: {recipient}\nRachunek nadawcy: {sender}"
    only_recipient_labelled = f"Przelew\nNa rachunek: {recipient}\nKonto: {sender}"
    repeated = f"Przelew\nRachunek nadawcy: {sender}\nKonto: {sender}\nRachunek odbiorcy: {recipient}"
    two_column_header = f"Przelew\nPłatnik Beneficjent\nFirma A Firma B\n{sender}\n{recipient}"
    for text in (recipient_first, only_recipient_labelled, repeated, two_column_header):
        result = bank_transfer.extract(text)["przelew_bankowy"]
        assert (result["z_rachunku"], result["na_rachunek"]) == (sender, recipient)


def test_registry_ids_and_dates():
    assert registry_ids("KRS: 9990000471, NIP: 526-104-08-28, REGON 012345678") == {
        "krs": "9990000471",
        "nip": "5261040828",
        "regon": "012345678",
    }
    assert registry_ids("NIP: 526 104 08 28")["nip"] == "5261040828"
    assert registry_ids("NIP PL5261040828")["nip"] == "5261040828"
    assert registry_ids("brak numerów") == {"krs": None, "nip": None, "regon": None}
    assert [to_iso(d) for d in ("2026-03-21", "21.03.2026", "21-03-2026", "21 marca 2026")] == ["2026-03-21"] * 4
    assert to_iso("31.02.2026") is None


@pytest.mark.parametrize(
    "failure",
    [
        ImportError("OCR library missing"),
        FileNotFoundError("Polish data missing"),
        RuntimeError("OCR timed out"),
    ],
)
def test_required_ocr_failure_reports_path_and_continues(tmp_path, monkeypatch, capsys, failure):
    inputs, outputs = tmp_path / "input", tmp_path / "output"
    inputs.mkdir()
    scan = inputs / "first.pdf"
    scan.touch()
    negative = inputs / "second.pdf"
    negative.touch()

    def open_document(path):
        page = MagicMock()
        page.extract_text.return_value = "" if path == scan else "Informacja o dostawie"
        doc = MagicMock()
        doc.__enter__.return_value.pages = [page]
        return doc

    monkeypatch.setattr(pdf_text.pdfplumber, "open", open_document)
    monkeypatch.setattr(pdf_text, "_ocr", MagicMock(side_effect=failure))
    monkeypatch.setattr(sys, "argv", ["kio2json", "--input", str(inputs), "--output", str(outputs)])
    assert cli.main() == 1
    stderr = capsys.readouterr().err
    assert str(scan) in stderr and str(failure) in stderr
    assert (outputs / "first.json").read_bytes() == (outputs / "second.json").read_bytes() == b""
    scan.unlink()
    assert cli.main() == 0


@pytest.mark.parametrize("stub", ["Strona 1 z 2", "1 / 2", "– 1 –"])
def test_page_number_only_layer_uses_ocr(monkeypatch, stub):
    page = MagicMock()
    page.extract_text.return_value = stub
    doc = MagicMock()
    doc.__enter__.return_value.pages = [page]
    monkeypatch.setattr(pdf_text.pdfplumber, "open", lambda _: doc)
    monkeypatch.setattr(pdf_text, "_ocr", lambda page, words: "Odwołanie skanowane")
    assert pdf_text.read_pages("test.pdf") == ["Odwołanie skanowane"]


def test_transfer_accounts_on_one_line_follow_explicit_roles():
    sender, recipient = "4" * 26, "5" * 26
    result = bank_transfer.extract(f"Na rachunek: {recipient}  Z rachunku: {sender}")["przelew_bankowy"]
    assert (result["z_rachunku"], result["na_rachunek"]) == (sender, recipient)


@pytest.mark.parametrize("separator", ["\n", "  "])
def test_empty_transfer_fields_do_not_consume_another_field(separator):
    text = separator.join(
        [
            "Kwota przelewu: brak",
            "Opłata: 1,50 PLN",
            "Data operacji: brak",
            "Data wydruku: 12.05.2026",
            "Tytuł:",
            "Numer transakcji: XZ123456",
        ]
    )
    result = bank_transfer.extract(text)["przelew_bankowy"]
    assert [result[k] for k in ("kwota", "data_operacji", "tytul", "numer_transakcji")] == [
        None,
        None,
        None,
        "XZ123456",
    ]


def test_transfer_requires_evidence_of_confirmation():
    accounts = "4" * 26 + "\n" + "5" * 26
    for header in ("Faktura VAT\nProsimy o przelew", "Wezwanie do zapłaty przelewem"):
        assert classify([header + "\n" + accounts]) is None
    assert classify(["Potwierdzenie wykonania przelewu\nData realizacji: 10.01.2026\n" + accounts]) == "bank_transfer"


def test_judgment_citation_in_appeal_body():
    citation = "W uzasadnieniu przywołuję orzeczenie Sygn. akt KIO 81/26."
    assert classify([APPEAL + citation]) == "appeal"
    assert classify(["Sygn. akt KIO 81/26\nWYROK\nODWOŁANIE\nOdwołujący: Firma Fikcyjna"]) is None


@pytest.mark.parametrize(
    ("body", "day"),
    [
        (
            "Zamawiający w dniu 1 marca 2026 opublikował SWZ. Zarzut nr 1 – odrzucenie oferty w dniu 8 marca 2026.",
            "2026-03-08",
        ),
        ("Zarzut nr 1 – odrzucenie oferty. Odwołanie wniesiono 15.05.2026.", None),
        ("Zarzut nr 1 – odrzucenie oferty. Zamawiający w dniu 8 marca 2026 zmienił treść SWZ.", None),
    ],
)
def test_first_charge_binds_action_and_date(body, day):
    result = appeal.extract(body)["OdwolanieKIO"]
    assert (result["czynnosc_powod_id"], result["czynnosc_dzien"]) == (1, day)


def test_representative_stays_with_contracting_authority():
    result = appeal.extract(
        "Zamawiający: Gmina Fikcyjna\nul. Testowa 3\nreprezentowana przez: adw. Iga Wymyślna\n"
        "Odwołujący: Fikcyjna Dostawa\nul. Próbna 5\nODWOŁANIE"
    )
    party = result["Odwolujacy"][0]
    assert party["przez-pelnomocnika"] == 0
    assert all(value is None for value in party["pelnomocnik"].values())


def test_name_only_parties_survive_section_changes_and_eof():
    result = appeal.extract("ODWOŁANIE\nOdwołujący: Fikcyjna Dostawa\nZamawiający:\nGmina Fikcyjna")
    for role, name in [("Odwolujacy", "Fikcyjna Dostawa"), ("Zamawiajacy", "Gmina Fikcyjna")]:
        (party,) = result[role]
        assert party["nazwa"] == name
        assert party["krs"] is party["nip"] is party["regon"] is None


def test_first_signature_heading_can_name_second_principal():
    text = """PEŁNOMOCNICTWO
Alfa Wymyślna sp. z o.o., KRS 9990000841 oraz Beta Fikcyjna sp. z o.o., KRS 9990000842 udzielają pełnomocnictwa.
W imieniu Beta Fikcyjna sp. z o.o.:
......................
Ewa Próbna
W imieniu Alfa Wymyślna sp. z o.o.:
......................
Iga Wymyślna"""
    principals = power_of_attorney.extract(text)["mocodawca"]
    assert [[s["imie_nazwisko"] for s in p["podpisujacy"]] for p in principals] == [["Iga Wymyślna"], ["Ewa Próbna"]]


@pytest.mark.parametrize("ids", ["", ", KRS 9990000841"])
def test_only_the_grantor_is_a_principal_even_without_ids(ids):
    text = (
        f"PEŁNOMOCNICTWO\nAlfa Wymyślna sp. z o.o.{ids} udziela pełnomocnictwa adw. Iga Wymyślna. "
        "Postępowanie prowadzi Beta Fikcyjna sp. z o.o., KRS 9990000842."
    )
    (principal,) = power_of_attorney.extract(text)["mocodawca"]
    assert principal["data"]["nazwa"] == "Alfa Wymyślna sp. z o.o."
    assert principal["data"]["krs"] == ("9990000841" if ids else None)
    assert principal["data"]["nip"] is None


def test_authority_can_be_named_before_the_grant():
    authority = "Beta Fikcyjna sp. z o.o., KRS 9990000842"
    for text in (
        f"Zamawiający: {authority}\nMocodawca: Alfa Wymyślna sp. z o.o.\nudziela pełnomocnictwa",
        f"Alfa Wymyślna sp. z o.o., w postępowaniu prowadzonym przez {authority}, udziela pełnomocnictwa",
    ):
        (principal,) = power_of_attorney.extract(text)["mocodawca"]
        assert principal["data"]["nazwa"] == "Alfa Wymyślna sp. z o.o."
        assert principal["data"]["krs"] is None


def test_blank_title_followed_by_fee_and_multiline_payment_title():
    assert bank_transfer.extract("Tytuł:\nOpłata: 12,00 PLN")["przelew_bankowy"]["tytul"] is None
    assert (
        bank_transfer.extract("Tytuł:\nopłata skarbowa za odbiór")["przelew_bankowy"]["tytul"]
        == "opłata skarbowa za odbiór"
    )


def test_fee_and_printed_on_prose_do_not_supply_transaction_values():
    result = bank_transfer.extract(
        "Opłata w kwocie 8,00 PLN\nWydrukowano w dniu 18.09.2026\nTytuł:\nProwizja: 8,00 PLN"
    )
    transfer = result["przelew_bankowy"]
    assert transfer["kwota"] is transfer["data_operacji"] is transfer["tytul"] is None


def test_invoice_requesting_confirmation_is_still_a_negative():
    text = "FAKTURA VAT\nProsimy o potwierdzenie przelewu na jeden z rachunków.\n" + "4" * 26 + "\n" + "5" * 26
    assert classify([text]) is None


def test_reference_dates_do_not_date_an_undated_charge():
    for text in (
        "Zarzut nr 1 – odrzucenie oferty. odwołanie wniesiono 11.04.2026.",
        "Zarzut nr 1 – odrzucenie oferty z naruszeniem ustawy z dnia 11.04.2026.",
    ):
        action = appeal.extract(text)["OdwolanieKIO"]
        assert action["czynnosc_powod_id"] == 1
        assert action["czynnosc_dzien"] is None
