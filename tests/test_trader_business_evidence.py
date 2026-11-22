import pytest

from kio2json.ocr_extract import extract_power_of_attorney
from kio2json.power_of_attorney import extract

ISSUER = "Mocodawca: Irena Król, przedsiębiorca wpisana do CEIDG, NIP 0000000127."
GRANT = "Udzielam pełnomocnictwa do odbioru dokumentacji."
TITLE = "PEŁNOMOCNICTWO"


@pytest.mark.parametrize(
    ("prefix", "issuer", "closing", "expected"),
    [
        (
            "",
            "Mocodawca: Irena Król, właścicielka firmy Pracownia Cichego Papieru, NIP 0000000127.",
            "",
            "Pracownia Cichego Papieru",
        ),
        (
            "",
            ISSUER + "\nPełna nazwa przedsiębiorcy wg CEIDG: Warsztat Opraw Irena Król",
            "",
            "Warsztat Opraw Irena Król",
        ),
        ("Introligatornia Irena Król\nNIP: 0000000127", ISSUER, "", "Introligatornia Irena Król"),
        ("", ISSUER, "Pieczęć firmowa:\nPracownia Oczko\nNIP: 0000000127", "Pracownia Oczko"),
        ("Drukarnia Trzcinowa\nIrena Król\nNIP: 0000000127", ISSUER, "", "Drukarnia Trzcinowa"),
        ("Biuro Koral Irena Król\nNIP: 0000000999", ISSUER, "", None),
        ("", ISSUER, "Pełnomocnik: Zofia Lis\nPieczęć firmowa:\nAgencja Lemiesz\nNIP: 0000000666", None),
        ("", ISSUER, "Pieczęć przedsiębiorcy: [nieczytelna]", None),
        ("", ISSUER + "\nFirma przedsiębiorcy: ................", "", None),
        (
            "",
            ISSUER,
            "Pieczęć firmowa:\nArchiwum Jodła\nNIP: 0000000127\nPieczęć firmowa:\nDrukarnia Brzoza\nNIP: 0000000127",
            None,
        ),
    ],
)
def test_registered_business_stays_with_its_owner(prefix, issuer, closing, expected):
    text = f"{prefix}\n{TITLE}\n{issuer}\n{GRANT}\n{closing}"
    for result in [extract(text), extract_power_of_attorney([text], {1})]:
        (row,) = result["mocodawca"]
        assert row["data"]["imie_nazwisko"] == "Irena Król"
        assert row["data"]["nip"] == "0000000127"
        assert row["data"]["nazwa"] == expected


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("Pieczęć firmowa mocodawcy: nieczytelny odcisk pieczęci", None),
        ("Pieczęć firmowa mocodawcy:\nFirma: Atelier Pokrętło\nImię i nazwisko przedsiębiorcy: Piotr Kosa", None),
        ("Pieczęć mocodawcy:\nNIP 0000000127", None),
        ("Pieczęć firmowa przedsiębiorcy: Oficyna Rekwizytów", "Oficyna Rekwizytów"),
    ],
)
def test_stamp_legend_has_to_be_a_business_of_this_grantor(extra, expected):
    result = extract(f"{TITLE}\n{ISSUER}\n{GRANT}\n{extra}")
    assert result["mocodawca"][0]["data"]["nazwa"] == expected


def test_description_of_an_unnamed_business_is_not_its_name():
    result = extract(f"{TITLE}\nMocodawca: Irena Król, właścicielka firmy rodzinnej, NIP 0000000127.\n{GRANT}")
    assert result["mocodawca"][0]["data"]["nazwa"] is None


def test_stationery_below_document_title_can_print_the_owner_first():
    card = "Irena Król\nZakład Renowacji Wag\nNIP: 0000000127"
    data = extract(f"{TITLE}\n{card}\n{ISSUER}\n{GRANT}")["mocodawca"][0]["data"]
    assert data["nazwa"] == "Zakład Renowacji Wag"


def test_labelled_trade_name_in_grantor_card():
    card = ISSUER + "\nNazwa handlowa: Skład Papierów Czerpanych"
    assert extract(f"{TITLE}\n{card}\n{GRANT}")["mocodawca"][0]["data"]["nazwa"] == "Skład Papierów Czerpanych"


@pytest.mark.parametrize("intro", ["Opracowała Irena Król", "Adres strony\nIrena Król"])
def test_personal_address_or_preparer_line_does_not_name_the_firm(intro):
    data = extract(f"{intro}\n{TITLE}\n{ISSUER}\n{GRANT}")["mocodawca"][0]["data"]
    assert data["nazwa"] is None


def test_printed_signature_cannot_turn_an_illegible_firm_into_a_business_name():
    text = f"{TITLE}\nMocodawca: firma [nieczytelne]\n{GRANT}\nPodpis właścicielki: Irena Król"
    (row,) = extract(text)["mocodawca"]
    assert row["data"]["imie_nazwisko"] == "Irena Król"
    assert row["data"]["nazwa"] is None


def test_named_stamp_with_two_incompatible_trade_fields_abstains():
    block = "Pieczęć mocodawcy:\nFirma: Zakład Ścieg\nFirma: Zakład Nitka"
    assert extract(f"{TITLE}\n{ISSUER}\n{GRANT}\n{block}")["mocodawca"][0]["data"]["nazwa"] is None


def test_blank_firm_box_does_not_take_the_next_registry_line():
    text = f"{TITLE}\n{ISSUER}\nFirma przedsiębiorcy:\nNIP 0000000127\n{GRANT}"
    assert extract(text)["mocodawca"][0]["data"]["nazwa"] is None


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("\nDane kontrahenta:\nNazwa handlowa: Warsztat Miedziany", ""),
        ("\nDane kontrahenta:\nNazwa firmy: Warsztat Miedziany", ""),
        ("", "\nPieczęć mocodawcy:\nDane kontrahenta:\nNazwa firmy: Warsztat Miedziany"),
    ],
)
def test_customer_block_cannot_fill_grantor_business(before, after):
    text = f"{TITLE}\n{ISSUER}{before}\n{GRANT}{after}"
    for record in [extract(text), extract_power_of_attorney([text], {1})]:
        assert record["mocodawca"][0]["data"]["nazwa"] is None


@pytest.mark.parametrize("next_field", ["Siedziba: Warszawa", "Numer NIP: 0000000127", "Telefon biura: 500 000 000"])
@pytest.mark.parametrize("location", ["declaration", "stamp"])
@pytest.mark.parametrize("label", ["Nazwa handlowa", "Firma przedsiębiorcy"])
def test_missing_firm_cannot_take_an_adjacent_labelled_value(next_field, location, label):
    blank = f"{label}:\n{next_field}"
    declaration = f"{TITLE}\n{ISSUER}\n{blank}\n{GRANT}"
    stamp = f"{TITLE}\n{ISSUER}\n{GRANT}\nPieczęć mocodawcy:\n{blank}"
    text = declaration if location == "declaration" else stamp
    for result in [extract(text), extract_power_of_attorney([text], {1})]:
        assert result["mocodawca"][0]["data"]["nazwa"] is None


@pytest.mark.parametrize("label", ["Dane kontaktowe", "Osoba kontaktowa", "Kontakt do korespondencji"])
def test_contact_card_cannot_supply_the_issuer_firm(label):
    text = f"{TITLE}\n{ISSUER}\n{label}:\nNazwa firmy: Warsztat Miedziany\n{GRANT}"
    for result in [extract(text), extract_power_of_attorney([text], {1})]:
        assert result["mocodawca"][0]["data"]["nazwa"] is None
