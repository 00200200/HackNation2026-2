"""Invented documents that are not one of the three target classes. The reference for each is `{}`.

Some are deliberately close to the targets (a KIO ruling, an answer to an appeal, a bank statement, a contract notice
with BZP and TED numbers): a classifier that keys on words alone will call them appeals or transfers.
"""

import random
from datetime import date, timedelta

from evals.variants.blocks import P, gap, grid, rule
from evals.variants.facts import Org, authority_name, iban, invent_org, nip, person_name, regon
from evals.variants.pdfkit import Look, Rendered, build_pdf
from evals.variants.vocab import Pick, fmt_account, fmt_amount, fmt_date, fmt_nip

TITLES = [
    "Dostawa materiałów biurowych dla jednostek miejskich",
    "Remont i przebudowa budynku szkoły wraz z infrastrukturą towarzyszącą",
    "Świadczenie usług utrzymania zieleni miejskiej w latach 2026–2028",
    "Zakup i dostawa sprzętu medycznego dla oddziału pediatrii",
    "Modernizacja oświetlenia ulicznego w technologii LED",
    "Odbiór i zagospodarowanie odpadów komunalnych z terenu gminy",
]
ITEMS = [
    ("Usługa serwisowa urządzeń", 1_200.0), ("Licencja na oprogramowanie (12 mies.)", 3_600.0),
    ("Materiały eksploatacyjne", 480.0), ("Transport i montaż", 950.0), ("Szkolenie pracowników", 2_100.0),
    ("Konserwacja instalacji", 760.0), ("Dostawa materiałów biurowych", 1_340.0), ("Przegląd okresowy", 540.0),
]  # fmt: skip
KINDS = [
    "invoice", "proforma", "payment_request", "notice", "ruling", "decision", "offer_opening", "statement", "response", "letter",
]  # fmt: skip
NEAR = {"ruling", "response", "statement", "notice"}  # close to a target class in vocabulary or layout


def stamp(rng: random.Random, year: int = 2026) -> date:
    return date(year, 1, 1) + timedelta(days=rng.randint(0, 330))


def bank_line(org: Org, rng: random.Random, pick: Pick) -> str:
    printed, _ = fmt_account(iban(rng), pick("neg_account", ["grouped", "code_grouped", "bare"]))
    return f"Nr rachunku: {printed}"


def invoice(rng: random.Random, pick: Pick, look: Look, *, proforma: bool) -> list:
    body, bold, small = look.style(), look.bold(), look.style("small", fontSize=look.size - 1.5)
    seller, buyer = invent_org(rng, public=False), invent_org(rng, public=rng.random() < 0.3)
    issued = stamp(rng)
    title = "Faktura pro forma" if proforma else "Faktura VAT"
    number = f"{'PF' if proforma else 'FV'}/{rng.randint(1, 400)}/{issued.month:02d}/{issued.year}"
    story = [
        P(f"{title} nr {number}", look.bold("h", fontSize=look.size + 4)),
        P(f"Data wystawienia: {fmt_date(issued, 'dot')}", body),
    ]
    story += [P(f"Termin płatności: {fmt_date(issued + timedelta(days=14), 'dot')}", body), gap(3)]
    for label, org in (("Sprzedawca", seller), ("Nabywca", buyer)):
        story += [
            P(label, bold),
            P(org.name, body),
            P(org.address, body),
            P(f"NIP: {fmt_nip(org.nip, 'dashed')}", body),
            gap(2),
        ]
    rows, total = [[P(h, small) for h in ("Lp.", "Nazwa towaru lub usługi", "Wartość netto", "VAT", "Brutto")]], 0.0
    for i, (name, net) in enumerate(rng.sample(ITEMS, rng.randint(2, 4)), 1):
        gross = round(net * 1.23, 2)
        total += gross
        rows.append(
            [
                P(str(i), body),
                P(name, body),
                P(fmt_amount(net, "space_comma_zl"), body),
                P("23%", body),
                P(fmt_amount(gross, "space_comma_zl"), body),
            ]
        )
    story += [grid(rows, [10, 80, 30, 15, 35], lines="grid"), gap(3)]
    story += [P(f"Do zapłaty: {fmt_amount(total, 'space_comma_zl')}", bold), P(bank_line(seller, rng, pick), body)]
    if proforma:
        story.append(P("Dokument nie stanowi faktury VAT. Płatność przed realizacją zamówienia.", small))
    return [*story, gap(8), P("Wystawił: " + person_name(rng), small)]


def payment_request(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    creditor, debtor = invent_org(rng, public=False), invent_org(rng, public=False)
    sent = stamp(rng)
    amount = fmt_amount(
        rng.randint(800, 40_000) + rng.random(), pick("neg_amount", ["space_comma_zl", "space_comma_pln"])
    )
    story = [P(f"{creditor.city}, {fmt_date(sent, 'long')}", look.style("r", alignment=2)), gap(2)]
    story += [
        P(creditor.name, bold),
        P(creditor.address, body),
        gap(2),
        P("Do:", body),
        P(debtor.name, bold),
        P(debtor.address, body),
        gap(4),
    ]
    story += [P("WEZWANIE DO ZAPŁATY", look.bold("h", fontSize=look.size + 3, alignment=1)), gap(2)]
    text = (
        f"W związku z nieuregulowaniem w terminie należności z faktury nr FV/{rng.randint(1, 300)}/{sent.year} wzywamy do "
        f"zapłaty kwoty {amount} w terminie 7 dni od dnia otrzymania niniejszego wezwania. Wpłaty należy dokonać na "
        f"rachunek bankowy {bank_line(creditor, rng, pick).removeprefix('Nr rachunku: ')}. Po upływie terminu sprawa "
        "zostanie skierowana na drogę postępowania sądowego."
    )
    return [*story, P(text, body), gap(8), P("Z poważaniem,", body), P(person_name(rng), bold)]


def notice(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    buyer, year = invent_org(rng, public=True), rng.choice([2025, 2026])
    bzp = f"{year}/BZP {rng.randint(100000, 999999):08d}/01"
    story = [
        P("Ogłoszenie o zamówieniu", look.bold("h", fontSize=look.size + 4)),
        P(f"Numer ogłoszenia: {bzp}", body),
        rule(),
    ]
    rows = [
        ("Nazwa zamawiającego", buyer.name), ("Adres", buyer.address), ("NIP", fmt_nip(nip(rng), "plain")), ("REGON", regon(rng)),
        ("Tytuł zamówienia", rng.choice(TITLES)), ("Tryb udzielenia zamówienia", "przetarg nieograniczony"),
        ("Numer referencyjny", f"ZP.{rng.randint(1, 300)}.{year}"), ("Termin składania ofert", fmt_date(stamp(rng, year), "dot")),
        ("Kod CPV", "30192000-1"), ("Szacunkowa wartość zamówienia", fmt_amount(rng.randint(200, 900) * 1000, "space_comma_zl")),
    ]  # fmt: skip
    return [*story, grid([[P(k, body), P(v, bold)] for k, v in rows], [60, 110], lines="under")]


def ruling(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    appellant, buyer = invent_org(rng, public=False), invent_org(rng, public=True)
    decided = stamp(rng)
    story = [
        P(f"Sygn. akt: KIO {rng.randint(100, 3999)}/{decided:%y}", body),
        P("WYROK", look.bold("h", fontSize=look.size + 5, alignment=1)),
    ]
    story += [P(f"z dnia {fmt_date(decided, 'long_r')}", look.style("c", alignment=1)), gap(2)]
    text = (
        f"Krajowa Izba Odwoławcza – w składzie: Przewodniczący: {person_name(rng)}, po rozpoznaniu na rozprawie w dniu "
        f"{fmt_date(decided, 'long_r')} w Warszawie odwołania wniesionego do Prezesa Krajowej Izby Odwoławczej przez "
        f"wykonawcę {appellant.name}, {appellant.address}, w postępowaniu prowadzonym przez zamawiającego {buyer.name}, "
        f"{buyer.address}, orzeka:"
    )
    story += [P(text, body), P("1. Oddala odwołanie.", bold)]
    fee = fmt_amount(rng.choice([7500, 10000, 15000]), "space_comma_zl")
    story += [
        P(
            f"2. Kosztami postępowania obciąża odwołującego i zalicza w poczet kosztów kwotę {fee} uiszczoną tytułem wpisu od odwołania.",
            body,
        )
    ]
    return [
        *story,
        gap(3),
        P("Uzasadnienie", bold),
        P(
            "Zamawiający prowadzi postępowanie o udzielenie zamówienia publicznego. Izba ustaliła, że zarzuty odwołania nie zasługują na uwzględnienie.",
            body,
        ),
    ]


def decision(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    issued = stamp(rng)
    story = [
        P("DECYZJA", look.bold("h", fontSize=look.size + 4, alignment=1)),
        P(f"Nr {rng.randint(1, 900)}/{issued.year}", look.style("c", alignment=1)),
    ]
    text = (
        f"Na podstawie art. 104 ustawy z dnia 14 czerwca 1960 r. – Kodeks postępowania administracyjnego, po rozpatrzeniu "
        f"wniosku {authority_name(rng)} z dnia {fmt_date(issued - timedelta(days=30), 'dot_r')}, orzekam o przyznaniu dofinansowania "
        f"w wysokości {fmt_amount(rng.randint(10, 400) * 1000, 'space_comma_zl')} na realizację zadania inwestycyjnego."
    )
    return [
        *story,
        gap(3),
        P(text, body),
        gap(3),
        P("Pouczenie", bold),
        P(
            "Od niniejszej decyzji służy odwołanie do organu wyższego stopnia w terminie 14 dni od dnia jej doręczenia.",
            body,
        ),
    ]


def offer_opening(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    buyer, opened = invent_org(rng, public=True), stamp(rng)
    story = [
        P("Informacja z otwarcia ofert", look.bold("h", fontSize=look.size + 3)),
        P(f"{buyer.name}, {fmt_date(opened, 'long_r')}", body),
        gap(2),
    ]
    rows = [[P("Nr", bold), P("Wykonawca", bold), P("NIP", bold), P("Cena brutto", bold)]]
    for i in range(1, rng.randint(3, 5) + 1):
        bidder = invent_org(rng, public=False)
        rows.append(
            [
                P(str(i), body),
                P(f"{bidder.name}, {bidder.address}", body),
                P(bidder.nip, body),
                P(fmt_amount(rng.randint(300, 900) * 1000, "space_comma_zl"), body),
            ]
        )
    return [
        *story,
        grid(rows, [10, 95, 30, 35], lines="grid"),
        gap(2),
        P(
            f"Kwota przeznaczona na sfinansowanie zamówienia: {fmt_amount(rng.randint(600, 950) * 1000, 'space_comma_zl')}",
            body,
        ),
    ]


def statement(rng: random.Random, pick: Pick, look: Look) -> list:
    body, small = look.style(), look.style("small", fontSize=look.size - 1.5)
    owner, start = invent_org(rng, public=False), stamp(rng)
    printed, _ = fmt_account(iban(rng), "code_grouped")
    story = [
        P("Wyciąg z rachunku bankowego", look.bold("h", fontSize=look.size + 3)),
        P(f"Właściciel: {owner.name}", body),
        P(f"Rachunek: {printed}", body),
        gap(2),
    ]
    rows = [[P(h, small) for h in ("Data", "Opis operacji", "Kwota", "Saldo")]]
    balance = rng.randint(20_000, 90_000) + 0.0
    for i in range(rng.randint(6, 10)):
        amount = (
            -rng.randint(100, 12_000) - rng.random() if rng.random() < 0.7 else rng.randint(100, 8_000) + rng.random()
        )
        balance += amount
        debit = [
            "PRZELEW ZEWNĘTRZNY",
            "Opłata za usługę",
            "Opłata prowizyjna",
            "Wpis od odwołania - Urząd Zamówień Publicznych",
        ]
        text = rng.choice(debit) if amount < 0 else "Wpływ od kontrahenta"
        rows.append(
            [
                P(fmt_date(start + timedelta(days=i * 3), "iso"), small),
                P(text, small),
                P(fmt_amount(abs(amount), "debit_sign" if amount < 0 else "space_comma_pln"), small),
                P(fmt_amount(balance, "space_comma_pln"), small),
            ]
        )
    return [*story, grid(rows, [25, 75, 35, 35], lines="under")]


def response(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    buyer, appellant, sent = invent_org(rng, public=True), invent_org(rng, public=False), stamp(rng)
    story = [
        P(f"{buyer.city}, {fmt_date(sent, 'long')}", look.style("r", alignment=2)),
        P(buyer.name, bold),
        P(buyer.address, body),
        gap(3),
    ]
    story += [P("Odpowiedź na odwołanie", look.bold("h", fontSize=look.size + 3, alignment=1)), gap(2)]
    text = (
        f"W odpowiedzi na odwołanie wykonawcy {appellant.name} z dnia {fmt_date(sent - timedelta(days=4), 'dot_r')} Zamawiający wnosi o "
        "oddalenie odwołania w całości oraz o zasądzenie kosztów postępowania odwoławczego według norm przepisanych."
    )
    return [
        *story,
        P(text, body),
        P(
            "Zamawiający prowadzi postępowanie zgodnie z przepisami ustawy Prawo zamówień publicznych, a zarzuty odwołania są bezzasadne.",
            body,
        ),
        gap(6),
        P(person_name(rng), bold),
    ]


def letter(rng: random.Random, pick: Pick, look: Look) -> list:
    body, bold = look.style(), look.bold()
    sender, receiver, sent = invent_org(rng, public=True), invent_org(rng, public=False), stamp(rng)
    story = [
        P(f"{sender.city}, {fmt_date(sent, 'dot')}", look.style("r", alignment=2)),
        P(sender.name, bold),
        P(sender.address, body),
        gap(3),
    ]
    text = (
        f"Szanowni Państwo, w nawiązaniu do rozmowy telefonicznej informujemy, że spotkanie dotyczące realizacji umowy zostało wyznaczone na dzień {fmt_date(sent + timedelta(days=9), 'long')}. "
        "Prosimy o potwierdzenie obecności do końca tygodnia."
    )
    return [
        *story,
        P(receiver.name, bold),
        gap(2),
        P(text, body),
        gap(5),
        P("Z poważaniem,", body),
        P(person_name(rng), bold),
    ]


BUILD = {
    "invoice": lambda r, p, lk: invoice(r, p, lk, proforma=False),
    "proforma": lambda r, p, lk: invoice(r, p, lk, proforma=True),
    "payment_request": payment_request,
    "notice": notice,
    "ruling": ruling,
    "decision": decision,
    "offer_opening": offer_opening,
    "statement": statement,
    "response": response,
    "letter": letter,
}


def render(kind: str, rng: random.Random) -> Rendered:
    pick = Pick(rng)
    look = Look(
        pick("font", ["sans", "serif"], [3, 2]),
        pick("size", [9.5, 10, 10.5, 11], [2, 3, 3, 1]),
        page=pick("page", ["a4", "letter"], [9, 1]),
    )
    story = BUILD[kind](rng, pick, look)
    return Rendered(
        build_pdf(story, look),
        {},
        {"class": "negatywny", "neg_kind": kind, "near": "yes" if kind in NEAR else "no", **pick.result()},
    )
