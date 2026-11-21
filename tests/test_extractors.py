"""Extractors and classifier on small synthetic texts (no organizer data needed)."""

from kio2json import appeal, bank_transfer, power_of_attorney
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
        classify(["Potwierdzenie przelewu\n11 1111 1111 1111 1111 1111 1111\n22 2222 2222 2222 2222 2222 2222"])
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
    for name in ("STRABAG Sp. z o.o.", "Budimex Spółka Akcyjna", "Polbud SP. Z O.O."):
        text = f"PEŁNOMOCNICTWO\n{name}, KRS 0000054588, NIP 1234567890\nudziela pełnomocnictwa adw. Jan Kowalski"
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
    assert registry_ids("KRS: 0000054588, NIP: 526-104-08-28, REGON 012345678") == {
        "krs": "0000054588",
        "nip": "5261040828",
        "regon": "012345678",
    }
    assert registry_ids("NIP: 526 104 08 28")["nip"] == "5261040828"
    assert registry_ids("NIP PL5261040828")["nip"] == "5261040828"
    assert registry_ids("brak numerów") == {"krs": None, "nip": None, "regon": None}
    assert [to_iso(d) for d in ("2026-03-21", "21.03.2026", "21-03-2026", "21 marca 2026")] == ["2026-03-21"] * 4
    assert to_iso("31.02.2026") is None
