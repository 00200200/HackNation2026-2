"""Invent linked case records without sampling case values from any corpus."""

import random
from datetime import date, timedelta
from pathlib import Path

from stdnum.pl import nip, regon

ACTION_DICTIONARY = Path(__file__).resolve().parents[1] / "data/uzp/oczekiwane-json/czynnosc_powod_id_dict.md"

# Independently worded allegations for the reserved long pleading family.
CHALLENGES = (
    "odrzucenie złożonej przez nas oferty mimo wykazania jej zgodności z warunkami",
    "podanie do wiadomości wyboru oferty innego wykonawcy jako najkorzystniejszej",
    "wykluczenie naszej firmy z udziału w przetargu bez dostatecznej podstawy",
    "udostępnienie specyfikacji warunków zamówienia dyskryminującej część wykonawców",
    "zmianę postanowień SWZ po rozpoczęciu biegu terminu składania ofert",
    "udzielenie niejednoznacznych wyjaśnień na pytania dotyczące SWZ",
    "pozostawienie w postępowaniu oferty, która powinna była zostać odrzucona",
    "zaniechanie wykluczenia wykonawcy objętego podstawą wykluczenia",
    "unieważnienie przetargu pomimo braku wskazanej przez zamawiającego przesłanki",
    "dalsze prowadzenie postępowania pomimo obowiązku jego unieważnienia",
    "określenie przedmiotu zamówienia przez parametry właściwe jednemu rozwiązaniu",
    "wprowadzenie do projektu umowy jednostronnego uprawnienia do zmiany terminu odbioru",
)
FIRST = ("Alina", "Wanda", "Laura", "Ewa", "Tomasz", "Filip", "Adam", "Kamil", "Zofia", "Leon")
LAST = ("Czajka", "Sowa", "Kłos", "Krupa", "Sikora", "Kania", "Jarosz", "Mazur", "Kruk", "Kurek")
BRANDS = ("Turkus", "Cedr", "Lazuryt", "Wrzos", "Topaz", "Jarzębina", "Korund", "Jawor")
TOWNS = ("Lublin", "Opole", "Kalisz", "Tarnów", "Krosno", "Radom")
PROJECTS = (
    "Modernizacja układu zasilania i oświetlenia w budynku archiwum miejskiego",
    "Zakup stanowisk pomiarowych wraz z przeszkoleniem pracowników laboratorium",
    "Dostawa regałów magazynowych z montażem i inwentaryzacją wyposażenia",
    "Przebudowa instalacji wodnej na terenie zespołu obiektów sportowych",
    "Opracowanie dokumentacji modernizacji systemu wentylacji w bibliotece",
    "Wymiana urządzeń sterujących w stacji uzdatniania wody",
)


def tax_id(rng):
    while True:
        body = f"999{rng.randrange(10**6):06d}"
        digit = nip.checksum(body)
        if digit < 10:
            return body + str(digit)


def registry_id(rng):
    body = f"999{rng.randrange(10**5):05d}"
    return body + regon.calc_check_digit(body)


def account(rng, prefix):
    # Two check digits, 24 domestic digits; PL is preserved only where printed.
    body = f"{rng.randrange(10**24):024d}"
    return ("PL" if prefix else "") + f"{98 - int(body + '252100') % 97:02d}{body}"


def make_case(seed, index, mandate_family):
    rng = random.Random(f"{seed}/facts/{index}")
    people = rng.sample([f"{first} {last}" for first in FIRST for last in LAST], 6)
    brands = rng.sample(BRANDS, 3)
    towns = rng.sample(TOWNS, 2)
    issue = date(2026, 2, 1) + timedelta(days=rng.randrange(265))
    action_date = issue - timedelta(days=rng.randrange(3, 9))
    payment_date = issue - timedelta(days=rng.randrange(2))
    reasons = dict(line.split("=", 1) for line in ACTION_DICTIONARY.read_text(encoding="utf-8").splitlines() if line)
    # Each consecutive block of twelve includes every first action, independently of layout.
    action = (index + seed) % 12 + 1
    proc = f"DZP.{rng.randrange(100, 900)}.{index + 1}.2026"
    plan = {
        "numer_bzp": None if rng.randrange(3) == 0 else f"2026/BZP{rng.randrange(10**8):08d}",
        "numer_postepowania": proc,
        "numer_ted": None if rng.randrange(3) == 0 else f"{rng.randrange(100000, 1000000)}-2026",
        "tytul": rng.choice(PROJECTS),
    }
    principals = []
    for i in range(2 if mandate_family == "late-consortium" else 1):
        person = people[i] if mandate_family == "late-trader" else None
        party = {
            "typ": "osoba_fizyczna" if person else "osoba_prawna",
            "imie_nazwisko": person,
            "nazwa": f"{brands[i]} Serwis {person or 'sp. z o.o.'}",
            "nip": tax_id(rng),
            "krs": None if person else f"000{rng.randrange(10**7):07d}",
        }
        signers = [people[i]]
        if not person and rng.randrange(3) == 0:
            signers.append(people[i + 2])
        principals.append({"data": party, "podpisujacy": [{"imie_nazwisko": name} for name in signers]})
    attorneys = [{"imie_nazwisko": name, "pesel": None} for name in people[4 : rng.choice([5, 6])]]
    mandate = {"mocodawca": principals, "pelnomocnicy": attorneys}
    lead = principals[0]["data"]
    appellant = {key: lead[key] for key in ("nazwa", "nip", "krs")}
    appellant.update(
        regon=registry_id(rng),
        pelnomocnik={
            "imie_nazwisko": people[4],
            "nazwa": f"Kancelaria Radców Prawnych {brands[2]}",
            "mail": f"biuro{index + 1}@radcy.example",
        },
    )
    appellant["przez-pelnomocnika"] = 1
    filed = index % 5 != 0
    appeal = {
        "OdwolanieKIO": {
            "data": issue.isoformat() if filed else None,
            "miejscowosc": towns[0] if filed else None,
            "czynnosc_dzien": action_date.isoformat() if index % 7 != 2 else None,
            "czynnosc_powod_id": action,
            "czynnosc_opis": reasons[str(action)].strip(),
        },
        "Odwolujacy": [appellant],
        "Zamawiajacy": [
            {
                "nazwa": f"Miejski Zakład Usług Technicznych {towns[1]}",
                "krs": None,
                "nip": tax_id(rng),
                "regon": registry_id(rng),
                "prowadzacy_postepowanie": None,
            }
        ],
        "ZamowieniePubliczne": plan,
    }
    is_grant_fee = rng.choice((True, False))
    ref = None if rng.randrange(3) == 0 else f"OP{rng.randrange(10**12):012d}"
    title = ("Opłata skarbowa za pełnomocnictwo" if is_grant_fee else "Wpis od odwołania do KIO") + f" w sprawie {proc}"
    if ref:
        title += " " + ref
    receipt = {
        "przelew_bankowy": {
            "data_operacji": payment_date.isoformat(),
            "kwota": 17.0 * len(attorneys) if is_grant_fee else rng.choice([7500.0, 10000.0]),
            "na_rachunek": account(rng, rng.choice([True, False])),
            "z_rachunku": account(rng, rng.choice([True, False])),
            "numer_transakcji": ref,
            "tytul": title,
        }
    }
    return {
        "appeal": appeal,
        "mandate": mandate,
        "receipt": receipt,
        "index": index,
        "issue_date": issue.isoformat(),
        "payment_purpose": "mandate" if is_grant_fee else "appeal",
        "payer": lead["nazwa"],
        "payee": f"Urząd Miasta {towns[1]}" if is_grant_fee else "Urząd Zamówień Publicznych",
        "challenge_text": CHALLENGES[action - 1],
    }
