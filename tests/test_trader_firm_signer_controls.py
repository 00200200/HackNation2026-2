"""Invented development grants with independently specified issuer fields."""

from dataclasses import dataclass
from shutil import which

import pytest
from snapshots.generate_native import write_native_pdf

from kio2json.pipeline import process_pdf


@dataclass(frozen=True)
class Grant:
    text: str
    owner: str | None
    nip: str
    firm: str | None
    signers: tuple[str, ...]


ISSUE = "Udzielam pełnomocnictwa do odbioru protokołu."

GRANTS = {
    "ceidg": Grant(
        "Mocodawca (wpis do CEIDG)\nImię i nazwisko przedsiębiorcy: Olga Lisowska\n"
        "Firma przedsiębiorcy: Introligatornia Splot Olga Lisowska\nNIP: 0000001500\n"
        f"{ISSUE}\nPodpis mocodawcy: Olga Lisowska",
        "Olga Lisowska",
        "0000001500",
        "Introligatornia Splot Olga Lisowska",
        ("Olga Lisowska",),
    ),
    "narrative": Grant(
        "Przedsiębiorca Karol Witkowski (NIP 0000001501), prowadzący działalność\n"
        "pod nazwą „Serwis Drobnych Wag”, udziela pełnomocnictwa do złożenia oferty.\n"
        "Podpis przedsiębiorcy:\nKarol Witkowski",
        "Karol Witkowski",
        "0000001501",
        "Serwis Drobnych Wag",
        ("Karol Witkowski",),
    ),
    "stationery": Grant(
        "Papier firmowy mocodawcy\nNazwa firmy: Pracownia Modrych Szkieł\n"
        "Mocodawca: osoba fizyczna\nImię i nazwisko: Laura Banach\nNIP: 0000001502\n"
        f"{ISSUE}\nPodpis mocodawcy:\nLaura Banach",
        "Laura Banach",
        "0000001502",
        "Pracownia Modrych Szkieł",
        ("Laura Banach",),
    ),
    "stamp": Grant(
        "Mocodawca: osoba fizyczna\nImię i nazwisko: Hubert Bielski\nNIP: 0000001503\n"
        f"{ISSUE}\nPieczęć firmowa mocodawcy:\nNazwa firmy: Warsztat Rudych Zawiasów\n"
        "Podpis właściciela: Hubert Bielski",
        "Hubert Bielski",
        "0000001503",
        "Warsztat Rudych Zawiasów",
        ("Hubert Bielski",),
    ),
    "proxy": Grant(
        "Mocodawca: osoba fizyczna\nImię i nazwisko: Lena Lesicka\nNIP: 0000001504\n"
        "Nazwa firmy: Telefonika Jodłowa\nUdzielam pełnomocnictwa do wydania dokumentacji.\n"
        "W imieniu mocodawcy podpisał: Emil Wolski\nPełnomocnik udzielający dalszego pełnomocnictwa",
        "Lena Lesicka",
        "0000001504",
        "Telefonika Jodłowa",
        ("Emil Wolski",),
    ),
    "recipient": Grant(
        "Przedsiębiorca Konrad Rybicki (NIP 0000001505) udziela pełnomocnictwa do odbioru pism.\n"
        "Pełnomocnik: Tamara Kulesza\nFirma pełnomocnika: Kancelaria Nad Wieżą\n"
        "Przyjmuję pełnomocnictwo.\nPodpis pełnomocnika: Tamara Kulesza",
        "Konrad Rybicki",
        "0000001505",
        None,
        (),
    ),
    "witness": Grant(
        "Mocodawca: osoba fizyczna\nImię i nazwisko: Hanna Topolska\nNIP: 0000001506\n"
        "Firma przedsiębiorcy: Pralnia Blask\nUdzielam pełnomocnictwa do wniesienia odwołania.\n"
        "Podpis mocodawcy: [nieczytelny]\nPodpis świadka: Oskar Laskowski",
        "Hanna Topolska",
        "0000001506",
        "Pralnia Blask",
        (),
    ),
    "counterparty": Grant(
        "Mocodawca: osoba fizyczna\nImię i nazwisko: Nina Polkowska\nNIP: 0000001507\n"
        f"{ISSUE}\nPodpis mocodawcy: Nina Polkowska\nDane kontrahenta:\n"
        "Nazwa firmy: Manufaktura Krasna\nNIP: 0000001599",
        "Nina Polkowska",
        "0000001507",
        None,
        ("Nina Polkowska",),
    ),
    "company": Grant(
        "Mocodawca: Migawka S.A.\nNIP: 0000001508\n"
        "Spółka udziela pełnomocnictwa do odebrania akt.\n"
        "Świadek: przedsiębiorca Roman Kaliski\nNazwa firmy świadka: Zakład Klisz",
        None,
        "0000001508",
        "Migawka S.A.",
        (),
    ),
}


@pytest.fixture(params=[*GRANTS, "ceidg-ocr"])
def grant_pdf(request, tmp_path, monkeypatch):
    name = request.param
    force_ocr = name.endswith("-ocr")
    if force_ocr and which("tesseract") is None:
        pytest.skip("forced OCR needs the Tesseract binary")
    grant = GRANTS[name.removesuffix("-ocr")]
    path = tmp_path / "pismo.pdf"
    write_native_pdf(path, [f"PEŁNOMOCNICTWO\n{grant.text}"], size=(660, 350), font=12)
    monkeypatch.setenv("KIO_OCR_ENGINE", "tesseract")
    label, record = process_pdf(path, force_ocr=force_ocr)
    assert label == "power_of_attorney"
    return grant, record["mocodawca"]


def test_printed_grantor_fields(grant_pdf):
    grant, principals = grant_pdf
    assert len(principals) == 1
    principal = principals[0]
    data = principal["data"]
    assert (data["typ"], data["imie_nazwisko"], data["nip"]) == (
        "osoba_fizyczna" if grant.owner else "osoba_prawna",
        grant.owner,
        grant.nip,
    )
    assert (data["nazwa"], principal["podpisujacy"]) == (
        grant.firm,
        [{"imie_nazwisko": name} for name in grant.signers],
    )
