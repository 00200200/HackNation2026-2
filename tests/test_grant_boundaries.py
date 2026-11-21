"""Grantor, appointee and signature ownership."""

import pytest

from kio2json import power_of_attorney

GRANTOR = "Wrzosik sp. z o.o."
AUTHORITY = "Porcelanka S.A."


@pytest.mark.parametrize(
    "declaration",
    [
        f"Mocodawca: {GRANTOR}, w postępowaniu, którego zamawiającym jest {AUTHORITY}, KRS 9876543222, udziela pełnomocnictwa.",
        f"W postępowaniu prowadzonym przez {AUTHORITY}, KRS 9876543222,\nMocodawca: {GRANTOR}\nudziela pełnomocnictwa.",
        f"Zamawiający: {AUTHORITY}\nDziałając w imieniu {GRANTOR}, udzielam pełnomocnictwa.",
        f"Postępowanie prowadzi {AUTHORITY}.\n{GRANTOR} udziela pełnomocnictwa.",
        f"{GRANTOR} udziela pełnomocnictwa. Zamawiającym jest {AUTHORITY}.",
        f"Mocodawca: {GRANTOR}\nUczestnik: {AUTHORITY}\nudziela pełnomocnictwa.",
        f"Organ prowadzący: {AUTHORITY}\nMocodawcą jest {GRANTOR}.",
        f"{GRANTOR}, w postępowaniu prowadzonym przez {AUTHORITY}, udziela pełnomocnictwa.",
    ],
)
def test_principal_is_the_grantor(declaration):
    (principal,) = power_of_attorney.extract("PEŁNOMOCNICTWO\n" + declaration)["mocodawca"]
    assert (principal["data"]["nazwa"], principal["data"]["krs"]) == (GRANTOR, None)


@pytest.mark.parametrize("qualifier", [" (partner konsorcjum)", " – wspólnik", "\n(drugi mocodawca)"])
def test_signature_heading_owns_the_signer(qualifier):
    text = f"PEŁNOMOCNICTWO\n{GRANTOR} i {AUTHORITY} udzielają pełnomocnictwa.\nZa {AUTHORITY}{qualifier}:\n..................\nMira Letnia\nW imieniu {GRANTOR}:\n..................\nEwa Cicha"
    principals = power_of_attorney.extract(text)["mocodawca"]
    assert [[s["imie_nazwisko"] for s in p["podpisujacy"]] for p in principals] == [["Ewa Cicha"], ["Mira Letnia"]]


@pytest.mark.parametrize("declaration", [f"Informacja o {AUTHORITY}, KRS 9876543222.", f"Zamawiający: {AUTHORITY}"])
def test_unrelated_company_is_not_a_grantor(declaration):
    assert power_of_attorney.extract("PEŁNOMOCNICTWO\n" + declaration)["mocodawca"] == []


def test_prior_company_mention_does_not_share_a_later_grant():
    text = f"Sprawa dotyczy {AUTHORITY}, KRS 9876543212.\n{GRANTOR} udziela pełnomocnictwa."
    assert [p["data"]["nazwa"] for p in power_of_attorney.extract(text)["mocodawca"]] == [GRANTOR]


def test_attorney_in_foreign_section_is_not_an_appointee():
    text = f"Mocodawca: {GRANTOR} udziela pełnomocnictwa adw. Iga Daleka.\nUczestnik: {AUTHORITY}\nreprezentowany przez adw. Mira Letnia"
    assert [p["imie_nazwisko"] for p in power_of_attorney.extract(text)["pelnomocnicy"]] == ["Iga Daleka"]


def test_signature_qualifier_is_not_a_signer():
    text = f"{GRANTOR} udziela pełnomocnictwa.\nZa {GRANTOR}\n(Partner Regionalny):\n..................\nEwa Cicha"
    assert power_of_attorney.extract(text)["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Ewa Cicha"}]


def test_numbered_consortium_and_wrapped_attorney_registration():
    text = (
        f"Wykonawcy wspólnie występujący (Konsorcjum): 1) {GRANTOR}, KRS 9912345678; 2)\n"
        f"{AUTHORITY} (dalej łącznie: „Mocodawca”) udzielają pełnomocnictwa: adw. Olga\n"
        "Wrzosowa (nr wpisu na listę: ZZ/123), r. pr. Mira\nStalowa."
    )
    result = power_of_attorney.extract(text)
    assert [p["data"]["nazwa"] for p in result["mocodawca"]] == [GRANTOR, AUTHORITY]
    assert [p["imie_nazwisko"] for p in result["pelnomocnicy"]] == ["Olga Wrzosowa", "Mira Stalowa"]
