"""Facts of one appeal case: the organizer's training references plus invented details, and the gold JSON built from them.

Every renderer prints only what its facts hold, and the gold is built from the same facts, so a reference can never
disagree with its PDF. Optional facts (KRS, BZP and TED numbers, e-mails, the header date) are dropped or added per
variant; names can be swapped for invented ones that look like real registry entries.
"""

import json
import random
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from stdnum import iban as stdnum_iban
from stdnum.pl import nip as stdnum_nip
from stdnum.pl import pesel as stdnum_pesel
from stdnum.pl import regon as stdnum_regon

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "uzp"
UZP = {"name": "Urząd Zamówień Publicznych", "street": "ul. Postępu 17A", "postcode": "02-676", "city": "Warszawa"}

CITIES = [
    ("Gdańsk", "80"), ("Gdynia", "81"), ("Warszawa", "00"), ("Kraków", "30"), ("Wrocław", "50"), ("Poznań", "60"),
    ("Łódź", "90"), ("Lublin", "20"), ("Katowice", "40"), ("Szczecin", "70"), ("Bydgoszcz", "85"), ("Białystok", "15"),
    ("Rzeszów", "35"), ("Kielce", "25"), ("Olsztyn", "10"), ("Opole", "45"), ("Toruń", "87"), ("Zielona Góra", "65"),
    ("Radom", "26"), ("Płock", "09"), ("Elbląg", "82"), ("Tarnów", "33"), ("Koszalin", "75"), ("Gliwice", "44"),
]  # fmt: skip
TOWNS = [
    "Olszanów", "Brzozowiec", "Dębnica Górna", "Zielonków", "Sosnowa Wola", "Modrzewo", "Wrzosowo", "Jarzębina",
    "Lipiny Małe", "Kalinów", "Ostrówek", "Rudziniec", "Borówno", "Czarnowo", "Jaworzyna", "Wierzbice", "Mirosławiec",
]  # fmt: skip
STREETS = [
    "ul. Długa", "ul. Krótka", "ul. Polna", "ul. Leśna", "al. Niepodległości", "ul. Mickiewicza", "ul. Słowackiego",
    "ul. Kościuszki", "ul. Piłsudskiego", "ul. Sienkiewicza", "pl. Wolności", "ul. Przemysłowa", "ul. Szkolna",
    "ul. Ogrodowa", "ul. Kolejowa", "ul. Jana Pawła II", "ul. Reymonta", "ul. Marszałkowska", "ul. Dworcowa",
]  # fmt: skip
BRANDS = [
    "Kolbud", "Energotech", "Hydrotrans", "Infrasystem", "Mostex", "Drogomax", "Zielpark", "Termoserwis", "Elektrobud",
    "Agrotrans", "Medsystem", "Optimed", "Sanikom", "Ekoplan", "Wodtech", "Cargoline", "Ambit", "Komtel", "Datanet",
    "Trasbud", "Inżpol", "Gastromax", "Lumina", "Aquaterra", "Novatech", "Technoserwis",
]  # fmt: skip
FORMS = [
    "Sp. z o.o.",
    "sp. z o.o.",
    "S.A.",
    "sp. j.",
    "sp. k.",
    "Sp. z o.o. sp. k.",
    "spółka z ograniczoną odpowiedzialnością",
]
PATRONS = ["Marii Konopnickiej", "Jana Pawła II", "Tadeusza Kościuszki", "Mikołaja Kopernika", "Henryka Sienkiewicza"]
PUBLIC = [
    "Gmina {town}", "Miasto {town}", "Urząd Miasta {town}", "Starostwo Powiatowe w {town}", "Zarząd Dróg Miejskich w {town}",
    "Zespół Szkół Technicznych im. {patron} w {town}", "Szkoła Podstawowa nr {n} im. {patron} w {town}",
    "Szpital Powiatowy w {town}", "Miejski Ośrodek Sportu i Rekreacji w {town}", "Muzeum Regionalne w {town}",
    "Zakład Gospodarki Komunalnej w {town} Sp. z o.o.", "Wojewódzki Szpital Specjalistyczny im. {patron} w {town}",
]  # fmt: skip
FIRST = ["Anna", "Piotr", "Katarzyna", "Marek", "Magdalena", "Tomasz", "Joanna", "Krzysztof", "Agnieszka", "Paweł"]
LAST = ["Nowak", "Wiśniewski", "Wójcik", "Kamiński", "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski"]
ROLES = ["Prezes Zarządu", "Członek Zarządu", "Wiceprezes Zarządu", "Prokurent"]
BANKS = ["Bank Nadwiślański", "Kredyt Północny", "Bank Wielkopolski i Pomorza", "Nova Bank Polska", "Credit Meridian"]


def read_reasons() -> dict[int, str]:
    text = (DATA / "oczekiwane-json" / "czynnosc_powod_id_dict.md").read_text(encoding="utf-8")
    return {int(n): label.strip() for n, label in re.findall(r"^(\d+)=(.+)$", text, re.MULTILINE)}


@dataclass(frozen=True)
class Org:
    name: str
    street: str
    postcode: str
    city: str
    krs: str | None = None
    nip: str | None = None
    regon: str | None = None
    email: str | None = None

    @property
    def address(self) -> str:
        return f"{self.street}, {self.postcode} {self.city}"


@dataclass(frozen=True)
class Person:
    name: str
    title: str = ""  # "r. pr.", "adw."
    pesel: str | None = None
    bar_no: str | None = None
    role: str = ""  # "Prezes Zarządu"

    @property
    def titled(self) -> str:
        return f"{self.title} {self.name}".strip()


@dataclass(frozen=True)
class Grantor:
    org: Org  # the legal entity, or the sole trader's business
    person: Person | None  # the sole trader as a natural person; None for a legal entity
    signers: tuple[Person, ...]


@dataclass(frozen=True)
class Procurement:
    title: str
    number: str  # internal reference number
    bzp: str | None  # JSON form YYYY/BZP########
    ted: str | None  # JSON form NNNNNN-YYYY
    mode: str = "przetargu nieograniczonego"


@dataclass(frozen=True)
class Transfer:
    date: date
    amount: float
    payer: Org
    payee: Org
    payer_account: str  # country code + digits
    payee_account: str
    ref: str | None
    title: str
    bank: str


@dataclass(frozen=True)
class Case:
    key: str
    source: str
    appellant: Org
    authorities: tuple[Org, ...]
    attorneys: tuple[Person, ...]
    firm: Org  # the attorneys' office: name and e-mail are in the reference, the rest is invented
    phone: str
    procurement: Procurement
    reason: int
    act_date: date
    other_bidder: str
    appeal_date: date
    place: str
    header: bool  # the appeal prints "place, date" at the top
    grantors: tuple[Grantor, ...]
    poa_date: date
    transfer: Transfer
    lead: int | None = None  # index of the authority that runs a joint procedure; None with a single authority
    tags: dict[str, str] = field(default_factory=dict)


# --- invented values -----------------------------------------------------------------------------------------


def nip(rng: random.Random) -> str:
    while True:
        head = f"{rng.randint(1, 9)}{rng.randrange(10**8):08d}"
        check = stdnum_nip.checksum(head + "0")  # the sum modulo 11 of the first nine digits is the check digit
        if check != 10:  # such a head has no valid NIP
            return f"{head}{check}"


def regon(rng: random.Random) -> str:
    head = f"{rng.randrange(10**8):08d}"
    return head + stdnum_regon.calc_check_digit(head)


def krs(rng: random.Random) -> str:
    return f"{rng.randint(1, 999999):010d}"


def pesel(rng: random.Random) -> str:
    born = date(1960, 1, 1) + timedelta(days=rng.randint(0, 12000))
    head = f"{born:%y}{born.month + 20 * (born.year >= 2000):02d}{born:%d}{rng.randint(0, 9999):04d}"
    return head + stdnum_pesel.calc_check_digit(head)


def iban(rng: random.Random, country: str = "PL") -> str:
    length = {"PL": 28, "DE": 22, "CZ": 24, "LT": 20}[country]
    bban = "".join(rng.choice("0123456789") for _ in range(length - 4))
    return f"{country}{stdnum_iban.calc_check_digits(country + '00' + bban)}{bban}"


def address(rng: random.Random, city: tuple[str, str] | None = None) -> tuple[str, str, str]:
    name, prefix = city or rng.choice(CITIES)
    return f"{rng.choice(STREETS)} {rng.randint(1, 150)}", f"{prefix}-{rng.randint(100, 999)}", name


def company_name(rng: random.Random) -> str:
    brand, form = rng.choice(BRANDS), rng.choice(FORMS)
    return rng.choice(
        [
            f"{brand} {form}",
            f"{brand.upper()} {form}",
            f"Przedsiębiorstwo Budowlane „{brand}” {form}",
            f"{brand}-{rng.choice(BRANDS)} {form}",
        ]
    )


def authority_name(rng: random.Random) -> str:
    return rng.choice(PUBLIC).format(town=rng.choice(TOWNS), patron=rng.choice(PATRONS), n=rng.randint(1, 20))


def person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def make_org(
    rng: random.Random,
    name: str,
    *,
    krs_id: str | None,
    nip_id: str | None,
    regon_id: str | None,
    email: str | None = None,
) -> Org:
    street, postcode, city = address(rng)
    return Org(name, street, postcode, city, krs_id, nip_id, regon_id, email)


def invent_org(rng: random.Random, *, public: bool) -> Org:
    name = authority_name(rng) if public else company_name(rng)
    org = make_org(rng, name, krs_id=None if public else krs(rng), nip_id=nip(rng), regon_id=regon(rng))
    return replace(org, email=f"kontakt@{re.sub(r'[^a-z]', '', name.lower())[:12] or 'firma'}.example")


# --- from the training references ------------------------------------------------------------------------------


def load_gold(source: str) -> tuple[dict, dict, dict]:
    folder = DATA / "dane" / source
    return tuple(  # type: ignore[return-value]
        json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("odwolanie", "pelnomocnictwo", "przelew")
    )


def org_from(rng: random.Random, item: dict, email: str | None = None) -> Org:
    return make_org(
        rng, item["nazwa"], krs_id=item.get("krs"), nip_id=item.get("nip"), regon_id=item.get("regon"), email=email
    )


def from_training(source: str, rng: random.Random, variant: int) -> Case:
    appeal, poa, transfer = load_gold(source)
    head, od = appeal["OdwolanieKIO"], appeal["Odwolujacy"][0]
    pm = od["pelnomocnik"]
    titles = rng.choice([("r. pr.", "adw."), ("radca prawny", "adwokat"), ("adw.", "adw.")])
    attorneys = tuple(
        Person(p["imie_nazwisko"], titles[i % 2], p.get("pesel") and str(p["pesel"]), f"WA-{rng.randint(1000, 99999)}")
        for i, p in enumerate(poa["pelnomocnicy"])
    )
    authorities = tuple(
        org_from(rng, z, f"zamowienia@{re.sub(r'[^a-z]', '', z['nazwa'].lower())[:10]}.example")
        for z in appeal["Zamawiajacy"]
    )
    appellant = org_from(rng, od)
    act = date.fromisoformat(head["czynnosc_dzien"])
    appeal_date = date.fromisoformat(head["data"]) if head["data"] else act + timedelta(days=rng.randint(3, 9))
    place = head["miejscowosc"] or appellant.city
    firm = make_org(rng, pm["nazwa"], krs_id=None, nip_id=None, regon_id=None, email=pm["mail"])
    grantors = tuple(
        Grantor(
            appellant if i == 0 else org_from(rng, m["data"]),  # the first grantor is the appellant
            Person(m["data"]["imie_nazwisko"]) if m["data"]["typ"] == "osoba_fizyczna" else None,
            tuple(Person(s["imie_nazwisko"], role=rng.choice(ROLES)) for s in m["podpisujacy"]),
        )
        for i, m in enumerate(poa["mocodawca"])
    )
    t = transfer["przelew_bankowy"]
    pay = Transfer(
        date.fromisoformat(t["data_operacji"]),
        t["kwota"],
        appellant,
        authorities[0],
        "PL" + t["z_rachunku"],
        "PL" + t["na_rachunek"],
        t["numer_transakcji"],
        t["tytul"],
        rng.choice(BANKS),
    )
    pz = appeal["ZamowieniePubliczne"]
    lead = next((i for i, z in enumerate(appeal["Zamawiajacy"]) if z["prowadzacy_postepowanie"] == 1), None)
    return Case(
        f"{source}-v{variant}",
        source,
        appellant,
        authorities,
        attorneys,
        firm,
        f"{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
        Procurement(pz["tytul"], pz["numer_postepowania"], pz["numer_bzp"], pz["numer_ted"]),
        head["czynnosc_powod_id"],
        act,
        company_name(rng),
        appeal_date,
        place,
        head["data"] is not None,
        grantors,
        appeal_date - timedelta(days=rng.randint(0, 6)),
        pay,
        lead,
    )


# --- variation of the facts ----------------------------------------------------------------------------------------


def drop(value, rng: random.Random, p: float):
    return None if rng.random() < p else value


def vary_org(org: Org, rng: random.Random, tags: dict[str, str], who: str, *, public: bool, swap: bool = True) -> Org:
    """Maybe swap the name for an invented realistic one; drop or add registry numbers."""
    if swap and rng.random() < 0.35:
        fresh = invent_org(rng, public=public)
        org = replace(fresh, street=org.street, postcode=org.postcode, city=org.city)
        tags[f"{who}_name"] = "invented"
    else:
        tags[f"{who}_name"] = "training"
    krs_id = org.krs
    if krs_id is None and not public and swap and rng.random() < 0.3:  # a sole trader has no KRS entry
        krs_id = krs(rng)
    return replace(org, krs=drop(krs_id, rng, 0.2), nip=drop(org.nip, rng, 0.08), regon=drop(org.regon, rng, 0.08))


def vary(case: Case, rng: random.Random) -> Case:
    """Apply the per-variant changes to the facts. The tags say what changed."""
    tags: dict[str, str] = {}
    sole_trader = case.grantors[0].person is not None
    appellant = vary_org(case.appellant, rng, tags, "appellant", public=False, swap=not sole_trader)
    authorities = tuple(vary_org(a, rng, tags, f"authority{i}", public=True) for i, a in enumerate(case.authorities))
    grantors = (replace(case.grantors[0], org=appellant),) + tuple(
        replace(g, org=vary_org(g.org, rng, tags, f"grantor{i}", public=False))
        for i, g in enumerate(case.grantors[1:], 1)
    )
    proc = case.procurement
    bzp = proc.bzp
    if bzp is None and rng.random() < 0.3:
        bzp = f"{case.appeal_date.year}/BZP{rng.randint(100000, 999999):08d}" + ("/01" if rng.random() < 0.3 else "")
    ted = proc.ted
    if ted is None and rng.random() < 0.3:
        ted = f"{rng.randint(100000, 999999):06d}-{case.appeal_date.year}"
    proc = replace(proc, bzp=drop(bzp, rng, 0.15), ted=drop(ted, rng, 0.15))
    firm = replace(case.firm, email=drop(case.firm.email, rng, 0.08))
    attorneys = case.attorneys
    if attorneys[0].pesel is None and rng.random() < 0.1:
        attorneys = (replace(attorneys[0], pesel=pesel(rng)), *attorneys[1:])
        tags["attorney_pesel"] = "yes"
    header = rng.random() < 0.75
    tags["header"] = "date" if header else "none"
    transfer = replace(
        case.transfer,
        payer=replace(case.transfer.payer, name=appellant.name),
        payee=replace(case.transfer.payee, name=authorities[0].name),
    )
    return replace(
        case,
        appellant=appellant,
        authorities=authorities,
        attorneys=attorneys,
        grantors=grantors,
        procurement=proc,
        firm=firm,
        header=header,
        transfer=transfer,
        tags={**case.tags, **tags},
    )


def build_case(source: str, rng: random.Random, variant: int) -> Case:
    return vary(from_training(source, rng, variant), rng)
