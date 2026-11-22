import pytest

from kio2json.ocr_extract import extract_power_of_attorney
from kio2json.power_of_attorney import extract

TITLE = "PEŁNOMOCNICTWO"
GRANT = "Udzielam pełnomocnictwa Adamowi Nowakowi do reprezentowania mnie w postępowaniu odwoławczym."


def card(person: str, firm: str, nip: str, header: str = "Dane wykonawcy (CEIDG):") -> str:
    return f"{header}\nImię i nazwisko: {person}\nFirma: {firm}\nNIP: {nip}"


def principal(text: str) -> tuple[dict, list[str]]:
    for result in [extract(text), extract_power_of_attorney([text], {1})]:
        (row,) = result["mocodawca"]
    return row["data"], [p["imie_nazwisko"] for p in row["podpisujacy"]]


@pytest.mark.parametrize(
    ("text", "person", "firm", "nip", "signers"),
    [
        (
            f"{TITLE}\n{card('Jan Sowa', 'Zakład Stolarski Jan Sowa', '5260000017')}\n{GRANT}\nPodpis mocodawcy: Jan Sowa",
            "Jan Sowa",
            "Zakład Stolarski Jan Sowa",
            "5260000017",
            ["Jan Sowa"],
        ),
        (
            f"{card('Marek Wrona', 'PHU Wrona', '526-000-00-33')}\n{TITLE}\n{GRANT}\nPodpis przedsiębiorcy: Marek Wrona",
            "Marek Wrona",
            "PHU Wrona",
            "5260000033",
            ["Marek Wrona"],
        ),
        (
            (
                f"{TITLE}\n{card('Ewa Kruk', 'Biuro Rachunkowe Ewa Kruk', '5260000058')}\n"
                "Przedsiębiorca o numerze NIP 5260000058 udziela pełnomocnictwa Adamowi Nowakowi.\nPodpis mocodawcy\nEwa Kruk"
            ),
            "Ewa Kruk",
            "Biuro Rachunkowe Ewa Kruk",
            "5260000058",
            ["Ewa Kruk"],
        ),
        (
            (
                f"{TITLE}\nDane przedsiębiorcy:\nFirma: Usługi Transportowe Krzysztof Zając\nWłaściciel: Krzysztof Zając\n"
                f"NIP: 5260000041\n{GRANT}\nPodpis: Krzysztof Zając"
            ),
            "Krzysztof Zając",
            "Usługi Transportowe Krzysztof Zając",
            "5260000041",
            ["Krzysztof Zając"],
        ),
        (
            f"{TITLE}\n{card('Iwona Bury', 'Atelier "Iga"', '5260000074')}\n{GRANT}\nPodpis mocodawcy: Iwona Bury",
            "Iwona Bury",
            'Atelier "Iga"',
            "5260000074",
            ["Iwona Bury"],
        ),
        (
            # A distinct proxy signer is allowed when the caption ties it to the proprietor.
            (
                f"{TITLE}\n{card('Tomasz Kret', 'Serwis Kret', '5260000082')}\n{GRANT}\n"
                "z upoważnienia mocodawcy podpisał Roman Wilk"
            ),
            "Tomasz Kret",
            "Serwis Kret",
            "5260000082",
            ["Roman Wilk"],
        ),
        (
            f"{TITLE}\n{card('Hanna Gil', 'Hanna Gil Usługi Szklarskie', '5260000090')}\n{GRANT}",
            "Hanna Gil",
            "Hanna Gil Usługi Szklarskie",
            "5260000090",
            [],
        ),
        (
            (
                f"{TITLE}\n{card('Olga Rak', 'Studio Rak', '5260000108')}\nUstanawiam pełnomocnikiem Adama Nowaka.\n"
                "Podpis mocodawcy: Olga Rak"
            ),
            "Olga Rak",
            "Studio Rak",
            "5260000108",
            ["Olga Rak"],
        ),
    ],
)
def test_identity_card_gives_the_missing_trader(text, person, firm, nip, signers):
    data, signed = principal(text)
    assert data == {"imie_nazwisko": person, "krs": None, "nazwa": firm, "nip": nip, "typ": "osoba_fizyczna"}
    assert signed == signers


def test_letterhead_nip_completes_the_stated_trader():
    text = (
        "Pracownia Szkła Barbara Lis\nNIP 5260000025\nul. Długa 1, Warszawa\n"
        f"{TITLE}\nJa, Barbara Lis, prowadząca działalność gospodarczą pod firmą Pracownia Szkła Barbara Lis, "
        "udzielam pełnomocnictwa Adamowi Nowakowi.\nPodpis mocodawcy\nBarbara Lis"
    )
    data, signed = principal(text)
    assert (data["nazwa"], data["nip"], signed) == ("Pracownia Szkła Barbara Lis", "5260000025", ["Barbara Lis"])


def test_printed_values_are_never_replaced():
    text = (
        f"{TITLE}\n{card('Piotr Gawron', 'Gawron Hurt', '5260000066')}\n"
        "Działając w imieniu Piotra Gawrona, prowadzącego działalność gospodarczą pod firmą Gawron Serwis, "
        "NIP 5260000099, udzielam pełnomocnictwa Adamowi Nowakowi."
    )
    data, _ = principal(text)
    assert (data["nazwa"], data["nip"]) == ("Gawron Serwis", "5260000099")


@pytest.mark.parametrize(
    "text",
    [
        # a company with a trade-like name
        f"{TITLE}\n{card('Jan Sowa', 'Zakład Stolarski Sowa sp. z o.o.', '5260000017')}\n{GRANT}\nPodpis mocodawcy: Jan Sowa",
        # a registered company card
        f"{TITLE}\nImię i nazwisko: Jan Sowa\nFirma: Sowa\nNIP: 5260000017\nKRS: 0000123456\n{GRANT}",
        # a private person without a firm
        f"{TITLE}\nImię i nazwisko: Jan Sowa\nPESEL: 80010112345\nNIP: 5260000017\n{GRANT}\nPodpis: Jan Sowa",
        # the recipient's stamp and attorney card
        f"{TITLE}\n{card('Jan Sowa', 'Kancelaria Sowa', '5260000017', 'Dane pełnomocnika:')}\n{GRANT}",
        f"{TITLE}\n{card('Jan Sowa', 'Kancelaria Sowa', '5260000017', 'Zamawiający:')}\n{GRANT}",
        # the attorney is the card's person
        f"{TITLE}\n{card('Adam Nowak', 'Kancelaria Nowak', '5260000017')}\n{GRANT}\nPodpis mocodawcy: Adam Nowak",
        # two different cards: no unique issuer
        f"{TITLE}\n{card('Jan Sowa', 'Sowa', '5260000017')}\n\n{card('Ewa Kruk', 'Kruk', '5260000058')}\n{GRANT}",
        # no first-person grant and no NIP in the sentence
        f"{TITLE}\n{card('Jan Sowa', 'Sowa', '5260000017')}\nZamawiający udziela pełnomocnictwa Adamowi Nowakowi.",
    ],
)
def test_no_trader_without_business_evidence(text):
    rows = extract(text)["mocodawca"]
    assert not any(r["data"]["typ"] == "osoba_fizyczna" and r["data"]["nazwa"] for r in rows)


def test_attorney_sharing_first_name_is_neither_principal_nor_signer():
    text = (
        f"{TITLE}\n{card('Adam Sowa', 'Sowa Usługi', '5260000017')}\n{GRANT}\n"
        "Podpis mocodawcy: Adam Sowa\nPełnomocnictwo przyjmuję: Adam Nowak"
    )
    data, signed = principal(text)
    assert data["imie_nazwisko"] == "Adam Sowa"
    assert "Adam Nowak" not in signed


def test_unsigned_grant_keeps_signers_empty():
    text = f"{TITLE}\n{card('Jan Sowa', 'Sowa', '5260000017')}\n{GRANT}\nPełnomocnictwo przyjmuję: Adam Nowak"
    _, signed = principal(text)
    assert signed == []
