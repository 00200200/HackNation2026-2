from kio2json import appeal
from kio2json.appeal_scan_parties import apply_parties
from kio2json.pdf_text import join_pages


def extract(pages, scanned):
    record = appeal.extract(join_pages(pages))
    apply_parties(record, pages, scanned)
    return record


def test_scanned_letter_uses_the_first_lawyer_and_their_contact():
    page = """„Odwolujacy: Konsorcjum wykonawców:
1) Polne Szkło sp. k. (Partner Konsorcjum)
ul. Rolna 3
NIP: 111-222-33-44
2) Jesienny Wiatr sp. k. (Lider Konsorcjum)
ul. Rolna 9
NIP: 555-888-77-66
reprezentowany przez pełnomocnika:
adw. Róża Śliwa
adw. Agata Latko
adres do korespondencji:
. Szron i Partnerzy Kancelaria Prawna
ul. Długa 12
e-mail: r.sliwaQfrost.example
Zamawiający: Instytut Badań Barw
'ul. Wodna 8
NIP: 5556667711
e-mail: biuro@instytut.example
Dotyczy: postępowania"""
    record = extract([page], {1})
    party = record["Odwolujacy"][0]
    assert (party["nazwa"], party["nip"]) == ("Jesienny Wiatr sp. k.", "5558887766")
    assert party["pelnomocnik"] == {
        "imie_nazwisko": "Róża Śliwa",
        "nazwa": "Szron i Partnerzy Kancelaria Prawna",
        "mail": "r.sliwa@frost.example",
    }
    assert record["Zamawiajacy"][0]["nazwa"] == "Instytut Badań Barw"


def test_native_header_with_scanned_annex_preserves_parties():
    pages = [
        """Odwołujący: Mosty sp. k.
ul. Letnia 4
Zamawiający: Biblioteka
ul. Jasna 3""",
        """„Odwołujący: Inna Firma
ul. Polna 2
reprezentowany przez pełnomocnika:
adw. Ula Tulipan""",
    ]
    assert extract(pages, {2}) == appeal.extract(join_pages(pages))


def test_name_in_nominative_requires_signature_for_same_attorney():
    page = """Odwołujący: Witraż sp. k.
ul. Kocia 2
reprezentowany przez pełnomocnika:
adwokata Piotra Rudego
adres do korespondencji:
Kancelaria Prawna
e-mail: biuro@witraze.example
Zamawiający: Biblioteka Publiczna
ul. Ptasia 9
Dotyczy: zakupu
ODWOŁANIE"""
    signature = "podpisano elektronicznie\nadw. Piotr Rudy"
    assert extract([page, signature], {1, 2})["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"] == "Piotr Rudy"


def test_other_role_and_lawyer_named_only_in_correspondence_are_excluded():
    header = "Odwołujący: Szkliwo\nul. Rybna 3\n"
    for block in [
        "Uczestnik: Płótno\nreprezentowany przez: adw. Maja Maj",
        "reprezentowany przez:\nadres do korespondencji: Kancelaria adw. Maja Maj",
    ]:
        page = header + block
        party = extract([page], {1})["Odwolujacy"][0]
        assert party["pelnomocnik"]["imie_nazwisko"] is None


def test_native_continuation_of_entity_name_is_preserved():
    pages = ["Odwołujący: Pracownia", "Witrażu\nul. Rybna 2"]
    assert extract(pages, {1}) == appeal.extract(join_pages(pages))


def test_two_column_electronic_form_preserves_role_and_field_ownership():
    from kio2json.pdf_text import WordBox

    rows = [
        ("Odwołujący:", "nazwa firmy: Kuźnia Kształtów"),
        ("", "email: biuro@kuznia.example"),
        ("Przedstawiciel ustawowy/pełnomocnik:", "imię: Łucja"),
        ("", "nazwisko: Bystra"),
        ("", "email: l.bystra(Qpismo.example"),
        ("Zamawiający:", "nazwa: Instytut Kwarcu"),
        ("", "email: zamowienia@kwarc.example"),
    ]
    page = "\n".join([left for left, _ in rows if left] + [right for _, right in rows])
    words = []
    for i, (left, right) in enumerate(rows):
        for x, label in [(20, left), (300, right)]:
            if label:
                words.append(WordBox(1, label, x, i * 25, x + len(label) * 6, i * 25 + 10))
    record = appeal.extract(page)
    apply_parties(record, [page], {1}, words)
    party = record["Odwolujacy"][0]
    assert party["nazwa"] == "Kuźnia Kształtów"
    assert party["pelnomocnik"] == {"imie_nazwisko": "Łucja Bystra", "nazwa": None, "mail": "l.bystra@pismo.example"}
    assert record["Zamawiajacy"][0]["nazwa"] == "Instytut Kwarcu"


def test_unrelated_footer_number_stays_with_its_owner():
    page = """Odwołujący: Pracownia Wazonów sp. k.
ul. Niska 3
NIP 1233334445
Zamawiający: Muzeum Instrumentów
ul. Wodna 8
ODWOŁANIE
NIP 4322221119, KRS 0000033311"""
    assert extract([page], {1})["Odwolujacy"][0]["krs"] is None


def test_scanned_filing_cover_can_list_attachments_before_its_party_cards():
    page = (
        "Karta zgłoszenia\nZałączniki: 2\nOdpis formularza\nSkany podpisów\n"
        "Zamawiający: Muzeum Latawców\nNIP: 2345678901\n"
        "Odwołujący: Fabryka Wstęg sp. z o.o.\nNIP: 1234567890\nODWOŁANIE"
    )
    result = extract([page], {1})
    assert [(p["nazwa"], p["nip"]) for p in result["Zamawiajacy"]] == [("Muzeum Latawców", "2345678901")]


def test_attachment_after_the_filing_parties_cannot_add_an_authority():
    page = (
        "Odwołujący: Fabryka Wstęg sp. z o.o.\nNIP: 1234567890\nZałączniki:\n"
        "Zamawiający: Muzeum Latawców\nNIP: 2345678901"
    )
    assert extract([page], {1})["Zamawiajacy"] == []
