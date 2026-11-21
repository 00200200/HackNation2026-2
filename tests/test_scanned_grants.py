from kio2json.ocr_extract import extract_power_of_attorney


def test_officers_and_listed_attorneys_bind_to_their_own_entries():
    page = """PEŁNOMOCNICTWO
1) Ogród i Sad sp. k. z siedzibą w Lesie, KRS: 0000000131,
reprezentowana przez: Iga
Wysoka — Prezes Zarządu, Adam Smukły — Prokurent,
2) Zegar S.A. z siedzibą w Porcie, KRS: 0000000142,
reprezentowana przez: Ewa Nowa — Prezes Zarządu
(dalej łącznie Mocodawca), udzielają pełnomocnictwa:
1. Jan Wesoły — adwokat, nr wpisu AX-313,
2. maria Bylicka (pracownik, PESEL: 08020144444) oraz
Eryk Polny (pracownik, PESEL: 09300433333),
do reprezentowania przed sądem.
Kancelaria Radcy Prawnego Marek Cichy"""
    result = extract_power_of_attorney([page], [1])
    assert [(p["data"]["nazwa"], p["podpisujacy"]) for p in result["mocodawca"]] == [
        ("Ogród i Sad sp. k.", [{"imie_nazwisko": "Iga Wysoka"}, {"imie_nazwisko": "Adam Smukły"}]),
        ("Zegar S.A.", [{"imie_nazwisko": "Ewa Nowa"}]),
    ]
    assert result["pelnomocnicy"] == [
        {"imie_nazwisko": "Jan Wesoły", "pesel": None},
        {"imie_nazwisko": "Maria Bylicka", "pesel": "08020144444"},
        {"imie_nazwisko": "Eryk Polny", "pesel": "09300433333"},
    ]


def test_signed_natural_person_grants_in_own_name():
    page = """PEŁNOMOCNICTWO
Ja, niżej podpisany/a Leon Polny, prowadzący/a działalność gospodarczą pod firmą Zegary,
NIP: 111-222-33-44, niniejszym udzielam pełnomocnictwa:
Urszula Wysoka
do reprezentowania przed sądem."""
    (principal,) = extract_power_of_attorney([page], [1])["mocodawca"]
    assert principal == {
        "data": {
            "imie_nazwisko": "Leon Polny",
            "krs": None,
            "nazwa": None,
            "nip": "1112223344",
            "typ": "osoba_fizyczna",
        },
        "podpisujacy": [{"imie_nazwisko": "Leon Polny"}],
    }


def test_morphology_requires_one_personal_reading_and_preserves_middle_names_in_certificates(monkeypatch):
    from pathlib import Path

    from kio2json import grant_certificates
    from kio2json.personal_names import nominative
    from kio2json.power_of_attorney import extract

    assert nominative("Brygidzie Laskowskiej", "dat") == "Brygida Laskowska"
    # The same spelling has multiple male accusative first-name lemmas.
    assert nominative("Roberta Polnego", "acc") is None
    text = """Pełnomocnictwo
My, niżej podpisane, Iga Morska i Ewa Bystra, wspólnicy
spółki cywilnej Zefir s.c. z siedzibą w Porcie, upoważniamy
radcę prawnego Eryka Polnego do działania."""
    result = extract(text)
    monkeypatch.setattr(grant_certificates, "signed_names", lambda _: ["Ewa Wanda Bystra", "Eryk Polny", "Jan Polny"])
    grant_certificates.add_certificate_signers(Path("invented.pdf"), result, text)
    assert [p["podpisujacy"] for p in result["mocodawca"]] == [
        [{"imie_nazwisko": "Iga Morska"}],
        [{"imie_nazwisko": "Ewa Wanda Bystra"}],
    ]


def test_embedded_signature_uses_the_personal_signing_certificate():
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.x509.oid import NameOID

    from kio2json.grant_certificates import _certificate_names

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Aldona Rita Polna"),
            x509.NameAttribute(NameOID.GIVEN_NAME, "Aldona"),
            x509.NameAttribute(NameOID.SURNAME, "Polna"),
        ]
    )
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(41)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    payload = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(b"example")
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    assert _certificate_names(payload) == ["Aldona Rita Polna"]


def test_alphanumeric_grant_number_requires_operative_language():
    from kio2json.classify import classify

    heading = "PEŁNOMOCNICTWO Nr AX/17/2031"
    assert classify([heading + "\nMocodawca udziela pełnomocnictwa."]) == "power_of_attorney"
    assert classify([heading + "\nSpis załączników"]) is None


def test_split_signature_requires_the_same_given_name():
    from kio2json.ocr_signatures import confirmed_scan_signer

    text = """Udzielam pełnomocnictwa.
Elektronicznie
Leon podpisany przez
Leon Portowy
Data: 15.07.2030"""
    for page, expected in ((text, ["Leon Portowy"]), (text.replace("Leon podpisany", "Jan podpisany"), [])):
        record = {"mocodawca": [{"podpisujacy": []}], "pelnomocnicy": []}
        confirmed_scan_signer(page, record)
        assert [s["imie_nazwisko"] for s in record["mocodawca"][0]["podpisujacy"]] == expected


def test_declaration_retains_attested_form_and_identifiers_from_matching_rows():
    page = """PEŁNOMOCNICTWO
Kuźnia S.A. z siedzibą w Porcie, reprezentowana przez Leon Smukły — Prezes Zarządu,
udziela pełnomocnictwa:
Adamowi Polnemu
do reprezentowania Spółki.
Pełnomocnik: Adam Polny, PESEL: 07123456789
Kuźnia S.A., NIP: 525-00-07-738"""
    record = extract_power_of_attorney([page], [1])
    assert record["pelnomocnicy"] == [{"imie_nazwisko": "Adam Polny", "pesel": "07123456789"}]
    assert record["mocodawca"][0]["data"]["nip"] == "5250007738"


def test_company_signature_is_not_attorney_attestation():
    from kio2json.power_of_attorney import extract

    text = """PEŁNOMOCNICTWO
Kuźnia S.A. udziela pełnomocnictwa:
adw. Bogdana Nowak
do reprezentowania Spółki.
Za Kuźnia S.A.
Podpisano przez: Bogdan Nowak"""
    record = extract(text)
    assert record["pelnomocnicy"][0]["imie_nazwisko"] == "Bogdana Nowak"
    assert record["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Bogdan Nowak"}]


def test_board_stamp_binds_a_name_to_the_role_below_the_finished_grant():
    from kio2json.ocr_signatures import board_stamp_names
    from kio2json.pdf_text import WordBox

    def line(text, x, y, width=90):
        return WordBox(1, text, x, y, x + width, y + 12)

    rows = [
        line("Kuźnia Żagli S.A. udziela pełnomocnictwa", 25, 60),
        line("Prezes Zarządu", 50, 110),
        line("Mira Portowa", 50, 130),
        line("do reprezentowania w postępowaniu odwoławczym.", 25, 280),
        line("Wiceprezes Zarządu", 50, 345),
        line("Wiceprezes Zarzadu", 280, 345),
        line("LEON/SZPAK", 50, 374),
        line("Biuro Prasowe", 280, 374),
        line("Osoba do kontaktu:", 50, 395),
        line("Prezes Zarządu", 50, 410),
        line("Roman Kot", 50, 432),
    ]
    assert board_stamp_names(rows, set(), "Kuźnia Żagli S.A.") == ["Leon Szpak"]
    assert board_stamp_names(rows, {"Leon Szpak"}, "Kuźnia Żagli S.A.") == []
    assert board_stamp_names([*rows[:6], line("Leon Szpak", 170, 374)], set(), "Kuźnia Żagli S.A.") == []
    assert (
        board_stamp_names([*rows[:4], line("Za zgodność z oryginałem", 50, 302), *rows[4:]], set(), "Kuźnia Żagli S.A.")
        == []
    )


def test_initial_glyph_in_a_titled_appointment_list_uses_its_governing_case():
    page = """PEŁNOMOCNICTWO
Mocodawca: Wędrowny Żagiel S.A.
Niniejszym ustanawiam:
r. pr. Tymona Szpaka
adw. lgor Boreckiego
do reprezentowania w postępowaniu."""
    result = extract_power_of_attorney([page], [1])
    assert result["pelnomocnicy"][-1] == {"imie_nazwisko": "Igor Borecki", "pesel": None}
    assert len(result["pelnomocnicy"]) == 2
    for pages, scanned in [([page, "Załącznik"], [2]), ([page.replace("lgor", "lxxz")], [1])]:
        assert len(extract_power_of_attorney(pages, scanned)["pelnomocnicy"]) == 1


def test_header_registry_rows_bind_by_the_krs_repeated_in_the_declaration():
    page = """Biuro spółki:
ul. Łagodna 5
NIP: 525-00-07-738  REGON: nieczytelny
KRS: 0000812656
PEŁNOMOCNICTWO
Mocodawca: Ciepły Żagiel S.A., KRS 0000812656, udziela pełnomocnictwa."""

    def number(text):
        return extract_power_of_attorney([text], [1])["mocodawca"][0]["data"]["nip"]

    assert number(page) == "5250007738"
    assert number(page.replace("KRS: 0000812656", "KRS: 0000812655")) is None
    assert number(page.replace("Biuro spółki:", "Zamawiający: Próbny Most S.A.")) is None


def test_representation_clause_restores_the_full_registered_company_name():
    page = """PEŁNOMOCNICTWO
Jako prokurent uprawniony do reprezentacji Zakładu Pomiarów Leśno — Wodnych Sp. z o.o. z siedzibą
w Porcie, KRS 0000812656, ustanawiam pełnomocnika."""

    def company(text, scanned):
        return extract_power_of_attorney([text, "Koniec"], scanned)["mocodawca"][0]["data"]["nazwa"]

    assert company(page, [1]) == "Zakład Pomiarów Leśno – Wodnych Sp. z o.o."
    assert company(page, [2]) == "Wodnych Sp. z o.o."
    assert company(page.replace("Zakładu Pomiarów", "Działającego Zespołu"), [1]) == "Wodnych Sp. z o.o."


def test_other_organization_heading_cannot_supply_a_board_stamp():
    from kio2json.ocr_signatures import board_stamp_names
    from kio2json.pdf_text import WordBox

    def line(text, y):
        return WordBox(1, text, 55, y, 142, y + 12)

    region = [
        line("Ciepły Żagiel S.A. udziela pełnomocnictwa.", 90),
        line("Do reprezentacji w postępowaniu.", 220),
        line("W imieniu Obca Przystań S.A.:", 238),
        line("Prezes Zarządu", 254),
        line("Jan Rydz", 276),
    ]
    assert board_stamp_names(region, set(), "Ciepły Żagiel S.A.") == []


def test_another_principals_krs_cannot_complete_a_represented_company():
    page = """PEŁNOMOCNICTWO
Przywołano prawo do reprezentacji Zakładu Pomiarów Leśno — Wodnych Sp. z o.o. z siedzibą w Porcie.
Mocodawca: Wodnych Sp. z o.o., KRS 0000812656, ustanawia pełnomocnika."""
    assert extract_power_of_attorney([page], [1])["mocodawca"][0]["data"]["nazwa"] == "Wodnych Sp. z o.o."


def test_power_to_certify_copies_allows_an_officer_stamp(monkeypatch, tmp_path):
    from kio2json import rapid_worker
    from kio2json.ocr_signatures import recover_board_stamp

    page = (
        "Ciepły Żagiel S.A. udziela pełnomocnictwa.\n"
        "Do poświadczania kopii za zgodność z oryginałem i reprezentowania w postępowaniu."
    )
    rows = [
        (1, text, 50, y, 140, y + 12)
        for text, y in zip([*page.splitlines(), "Prezes Zarządu", "Jan Rydz"], [50, 120, 150, 168], strict=True)
    ]
    monkeypatch.setattr(rapid_worker, "recognize", lambda *args, **kwargs: ("", rows))
    for ending, expected in [("", [{"imie_nazwisko": "Jan Rydz"}]), ("\nZa zgodność z oryginałem pełnomocnictwa.", [])]:
        record = extract_power_of_attorney([page], [1])
        recover_board_stamp(tmp_path / "doc.pdf", record, page + ending)
        assert record["mocodawca"][0]["podpisujacy"] == expected


def test_repeated_mandate_word_in_certification_is_not_the_end_of_the_grant():
    from kio2json.ocr_signatures import board_stamp_names
    from kio2json.pdf_text import WordBox

    lines = [
        "Spółka udziela pełnomocnictwa.",
        "Do reprezentowania w postępowaniu.",
        "Za zgodność z oryginałem pełnomocnictwa.",
        "Prezes Zarządu",
        "Jan Rydz",
    ]
    boxes = [WordBox(1, line, 50, i * 20, 120, i * 20 + 12) for i, line in enumerate(lines)]
    assert board_stamp_names(boxes, set(), "Ciepły Żagiel S.A.") == []
