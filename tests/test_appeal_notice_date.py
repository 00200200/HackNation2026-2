"""Invented passages for the dated notice of the first challenged act."""

import pytest

from kio2json.appeal_charges import notice_date

POSITIVES = [
    ("Zamawiający poinformował Odwołującego o odrzuceniu oferty w dniu 03.06.2025 r.", 1, "2025-06-03"),
    ("Zawiadomienie o wyborze najkorzystniejszej oferty doręczono 12 maja 2025 roku.", 2, "2025-05-12"),
    ("Odwołujący został zawiadomiony o wykluczeniu wykonawcy dnia 2025-04-07.", 3, "2025-04-07"),
    ("Treść specyfikacji opublikowano na platformie dnia 15.01.2025.", 4, "2025-01-15"),
    ("Informację o unieważnieniu postępowania otrzymaliśmy 21.02.2025.", 9, "2025-02-21"),
    ("Wyjaśnienia treści SWZ udostępniono 8 marca 2025.\nOdwołanie dotyczy opisu przedmiotu.", 6, "2025-03-08"),
    (
        "Zawiadomienie o wyborze oferty doręczono 12.05.2025. Ten sam wybór oferty opublikowano 12.05.2025.",
        2,
        "2025-05-12",
    ),
]

ABSTAIN = [
    # Another proceeding's award.
    ("W poprzednim postępowaniu zawiadomiono o wyborze oferty dnia 01.03.2024.", 2),
    # A remedy that has not happened yet.
    ("Zamawiający poinformuje o wyborze oferty, odwołanie można wnieść do 20.06.2025.", 2),
    # A statute on the adjacent line.
    ("Poinformowano o odrzuceniu oferty zgodnie z ustawą\nz dnia 11.09.2019 Prawo zamówień publicznych.", 1),
    # The date of preparing a copy.
    ("Kopię zawiadomienia o odrzuceniu oferty sporządzono 30.06.2025.", 1),
    # Two dates leave the trigger ambiguous.
    ("Poinformowano o odrzuceniu oferty 03.06.2025, a ponownie 10.06.2025.", 1),
    # A different act type than the resolved reason.
    ("Zamawiający poinformował o wyborze oferty w dniu 03.06.2025.", 1),
    # Two notices of one act type with different dates.
    ("Zawiadomiono o odrzuceniu oferty 03.06.2025. Zawiadomiono o odrzuceniu oferty 05.06.2025.", 1),
]


@pytest.mark.parametrize(("text", "reason", "day"), POSITIVES)
def test_dated_notice_of_the_resolved_act(text, reason, day):
    assert notice_date(text, reason) == day


@pytest.mark.parametrize(("text", "reason"), ABSTAIN)
def test_abstains_without_one_completed_notice(text, reason):
    assert notice_date(text, reason) is None
