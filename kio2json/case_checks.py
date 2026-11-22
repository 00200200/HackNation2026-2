"""Compare facts printed in sibling documents for review in the viewer or trace."""

import json
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from .batch import Result
from .case_repair import procedure_references
from .personal_names import compatible_names


@dataclass(frozen=True)
class CaseWarning:
    code: str
    documents: tuple[Path, ...]
    message: str


type Record = tuple[Path, dict]


def _name(value: str) -> str:
    words = (
        value.casefold().replace("spółka akcyjna", "sa").replace("spółka z ograniczoną odpowiedzialnością", "sp zoo")
    )
    return "".join(re.findall(r"\w", words))


def _different_parties(appellant: dict, grantor: dict) -> bool:
    # A common identifier can confirm a differently printed name. A conflicting one merits review.
    identifiers = [appellant[key] == grantor[key] for key in ("nip", "krs") if appellant.get(key) and grantor.get(key)]
    if identifiers:
        return not all(identifiers)
    name = appellant.get("nazwa")
    names = [grantor[key] for key in ("nazwa", "imie_nazwisko") if grantor.get(key)]
    return bool(name and names and all(_name(name) != _name(other) for other in names))


def _different_people(first: str | None, second: str | None) -> bool:
    if not first or not second or _name(first) == _name(second):
        return False
    if len(first.split()) == len(second.split()):
        return not (compatible_names(first, second) or compatible_names(second, first))
    return True


def _grant_warnings(appeal: Record, grants: list[Record]) -> Iterator[CaseWarning]:
    appellants = appeal[1].get("Odwolujacy") or []
    if not grants or not appellants:
        return
    names = (appeal[0], *(name for name, _ in grants))
    # Multiple grants and consortium members can supply alternative matches. An empty
    # row leaves the comparison unresolved, just like an absent list in one grant.
    grantors = [(row.get("data") or {}) for _, data in grants for row in (data.get("mocodawca") or [{}])]
    if all(_different_parties(party, grantor) for party in appellants for grantor in grantors):
        yield CaseWarning("grantor", names, "Dane odwołującego i mocodawcy różnią się. Sprawdź nazwę, NIP i KRS.")
    counsel = [(party.get("pelnomocnik") or {}).get("imie_nazwisko") for party in appellants]
    authorized = [row.get("imie_nazwisko") for _, data in grants for row in (data.get("pelnomocnicy") or [{}])]
    if all(_different_people(person, other) for person in counsel for other in authorized):
        yield CaseWarning("attorney", names, "Dane pełnomocnika w odwołaniu różnią się od danych osób umocowanych.")


# UZP, https://www.gov.pl/web/uzp/5-wpis-od-odwolania. Without a threshold field,
# both statutory rates for the category are possible. Only read a clearly named subject.
_WORKS = re.compile(r"(?:roboty budowlane|wykonanie robót budowlanych)\b", re.IGNORECASE)
_GOODS_SERVICES = re.compile(r"(?:dostaw[ay]|usług[ai]|świadczenie usług|konkurs)\b", re.IGNORECASE)
_APPEAL_FEE = re.compile(r"\b(?:wpis|opłata)\s+(?:(?:od|za)\s+odwołani[ae]|kio)\b", re.IGNORECASE)
_OTHER_PAYMENT = re.compile(
    r"\b(?:skarbow\w*|wadium|częściow\w*|część\s+(?:wpłaty|wpisu)|dopłat\w*|zwrot\w*)\b", re.IGNORECASE
)


def _transfer_warnings(appeal: Record, receipt: Record) -> Iterator[CaseWarning]:
    procurement = appeal[1].get("ZamowieniePubliczne") or {}
    transfer = receipt[1].get("przelew_bankowy") or {}
    names = (appeal[0], receipt[0])
    title = transfer.get("tytul") or ""
    reference = procurement.get("numer_postepowania")
    references = {m[1].casefold(): m[1] for m in procedure_references(title)}
    if reference and len(references) == 1 and reference.casefold() not in references:
        other = next(iter(references.values()))
        yield CaseWarning(
            "procedure",
            names,
            f"Numer postępowania w odwołaniu ({reference}) różni się od numeru w tytule przelewu ({other}).",
        )
    amount = transfer.get("kwota")
    if type(amount) not in (int, float) or not _APPEAL_FEE.search(title) or _OTHER_PAYMENT.search(title):
        return
    subject = (procurement.get("tytul") or "").strip()
    if _WORKS.match(subject):
        rates = (10000, 20000)
    elif _GOODS_SERVICES.match(subject):
        rates = (7500, 15000)
    else:
        return
    if abs(amount) not in rates:
        low, high = (f"{rate:,}".replace(",", " ") for rate in rates)
        yield CaseWarning(
            "fee",
            names,
            f"Kwota przelewu ({amount:g}) odbiega od stawek wpisu dla zamówienia "
            f"„{subject}” ({low} lub {high} zł). Sprawdź kwotę i walutę wpłaty.",
        )


def case_warnings(names: Sequence[Path], results: Sequence[Result]) -> list[CaseWarning]:
    """Return independent review findings for each folder with one identifiable appeal."""
    cases = defaultdict(lambda: defaultdict(list))
    for name, result in zip(names, results, strict=True):
        if (
            not result.custom_schema
            and result.label in {"appeal", "power_of_attorney", "bank_transfer"}
            and result.text
            and not result.error
        ):
            cases[name.parent][result.label].append((name, json.loads(result.text)))
    warnings = []
    for documents in cases.values():
        # The schema has no link telling us which appeal a grant or receipt belongs to.
        if len(documents["appeal"]) == 1:
            appeal = documents["appeal"][0]
            warnings.extend(_grant_warnings(appeal, documents["power_of_attorney"]))
            for receipt in documents["bank_transfer"]:
                warnings.extend(_transfer_warnings(appeal, receipt))
    return warnings
