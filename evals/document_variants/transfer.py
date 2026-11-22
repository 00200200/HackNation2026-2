"""Transfer confirmations: eight bank layouts printed with varied wording and date, amount and account formats."""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from xml.sax.saxutils import escape as e

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Table

from evals.document_variants.blocks import P, gap, grid, leader, rule
from evals.document_variants.facts import UZP, Case, Org, iban
from evals.document_variants.pdfkit import Look, Rendered, build_pdf, mm
from evals.document_variants.vocab import Pick, fmt_account, fmt_amount, fmt_date

LABELS = {
    "payer": ["Zleceniodawca", "Płatnik", "Nadawca", "Dane nadawcy"],
    "payer_acct": [
        "Rachunek zleceniodawcy",
        "Rachunek obciążany",
        "Z rachunku",
        "Rachunek nadawcy",
        "Numer rachunku nadawcy",
    ],
    "payee": ["Odbiorca", "Beneficjent", "Adresat przelewu", "Dane odbiorcy"],
    "payee_acct": [
        "Rachunek odbiorcy",
        "Na rachunek",
        "Rachunek beneficjenta",
        "Rachunek uznawany",
        "Numer rachunku odbiorcy",
    ],
    "amount": ["Kwota", "Kwota operacji", "Kwota przelewu", "Wartość operacji"],
    "date": ["Data operacji", "Data transakcji", "Data realizacji", "Data wykonania"],
    "ref": ["Numer referencyjny", "Nr ref.", "Numer transakcji", "Identyfikator operacji", "ID transakcji"],
    "title": ["Tytuł przelewu", "Tytułem", "Opis", "Tytuł", "Szczegóły płatności"],
}
HEADINGS = [
    "POTWIERDZENIE WYKONANIA PRZELEWU",
    "POLECENIE PRZELEWU",
    "Potwierdzenie przelewu krajowego",
    "POTWIERDZENIE REALIZACJI POLECENIA PRZELEWU",
    "Potwierdzenie transakcji",
]
ACCOUNT_STYLES = ["code_grouped", "code_bare", "code_space_grouped", "bare", "grouped"]
ACCOUNT_WEIGHTS = [4, 1, 2, 1, 2]
DATE_STYLES = ["dot", "iso", "dash", "slash", "long"]
AMOUNT_STYLES = [
    "space_comma_pln",
    "space_comma_zl",
    "nbsp_comma_pln",
    "plain_dot_pln",
    "plain_comma_zl",
    "bare_comma",
    "pln_first",
]
LAYOUTS = ["boxes", "leaders", "letter", "form", "business", "statement", "ledger", "stacked"]
LOOKS = {  # layout -> (font family, size)
    "boxes": ("sans", 9.5),
    "leaders": ("mono", 9),
    "letter": ("serif", 10.5),
    "form": ("sans", 9.5),
    "business": ("sans", 9),
    "statement": ("sans", 9),
    "ledger": ("sans", 9),
    "stacked": ("sans", 10),
}
GREY = colors.Color(0.4, 0.4, 0.4)


@dataclass
class Slip:
    payer: Org
    payee: Org
    payer_acct: str  # as printed
    payee_acct: str
    amount: str
    date: str
    ref: str | None
    title: str
    bank: str
    heading: str
    printed_at: str
    booked: str
    labels: dict[str, str]
    look: Look
    extras: list[tuple[str, str]] = field(default_factory=list)
    swap: bool = False
    payer_name_shown: bool = True


def new_ref(rng: random.Random, d: date) -> str:
    return rng.choice(
        [
            f"CEN{rng.randint(10**12, 10**13 - 1)}",
            f"TRX{rng.randint(10**9, 10**10 - 1)}",
            f"{d:%Y%m%d}{rng.randint(10**5, 10**6 - 1)}",
        ]
    )


def payment(case: Case, pick: Pick) -> tuple[str, float, Org, str, str | None]:
    """Title, amount, payee, payee account and reference. Appeal-fee titles pay the Office, stamp duty the authority."""
    t, rng = case.transfer, pick.rng
    titled = " i ".join(a.titled for a in case.attorneys[:2])
    number, authority = case.procurement.number, case.authorities[0].name
    style = pick(
        "title", ["training", "stamp_titled", "stamp_upper", "wpis_short", "wpis_dash", "wpis_long"], [3, 2, 2, 2, 1, 2]
    )
    ref = t.ref if style == "training" else (new_ref(rng, t.date) if pick.chance("ref", 0.65) else None)
    suffix = f" {ref}" if ref and pick.chance("ref_in_title", 0.6) else ""
    if style == "training":
        return t.title, t.amount, t.payee, t.payee_account, ref
    if style.startswith("stamp"):
        text = f"opłata skarbowa od pełnomocnictwa dla {titled} w postępowaniu przed KIO w przetargu {number}{suffix}"
        return (
            (text.upper() if style == "stamp_upper" else text),
            17.0 * min(len(case.attorneys), 3),
            t.payee,
            t.payee_account,
            ref,
        )
    uzp = Org(UZP["name"], UZP["street"], UZP["postcode"], UZP["city"])
    text = {
        "wpis_short": f"Wpis od odwołania, {number}, {authority.upper()}{suffix}",
        "wpis_dash": f"wpis od odwołania - postępowanie nr {number}{suffix}",
        "wpis_long": f"WPIS OD ODW., ZAM: {authority.upper()}, {number}, {case.procurement.title.upper()}{suffix}"[
            :140
        ],
    }[style]
    return text, float(rng.choice([7500, 10000, 15000, 20000])), uzp, iban(rng), ref


def lab(look: Look):
    return look.style("lab", fontSize=look.size - 2, textColor=GREY, spaceAfter=0)


def boxes(s: Slip, pick: Pick) -> list:
    look, small, body, bold = s.look, lab(s.look), s.look.style(), s.look.bold()
    parties = [(s.payer, s.payer_acct, "payer", "payer_acct"), (s.payee, s.payee_acct, "payee", "payee_acct")]
    rows = []
    for org, acct, role, acct_role in parties[::-1] if s.swap else parties:
        rows.append([P(s.labels[role], small), P(s.labels[acct_role], small)])
        rows.append([P(f"<b>{e(org.name)}</b><br/>{e(org.address)}", body, raw=True), P(acct, bold)])
    rows += [[P(s.labels["amount"], small), P(s.labels["date"], small)], [P(s.amount, bold), P(s.date, bold)]]
    story = [
        P(s.heading, look.bold("h", fontSize=15)),
        P(f"{s.bank} · wydrukowano {s.printed_at}", look.style("s", textColor=GREY)),
    ]
    story += [gap(4), grid(rows, [95, 75], lines="under"), gap(3), P(s.labels["title"], small), P(s.title, body)]
    if s.ref:
        story += [P(s.labels["ref"], small), P(s.ref, bold)]
    return [*story, gap(2), *[P(f"{k}: {v}", body) for k, v in s.extras]]


def leaders(s: Slip, pick: Pick) -> list:
    look, body, bold = s.look, s.look.style(), s.look.bold()
    dashes = P("-" * 62, look.style("d", spaceAfter=1))
    story = [P(s.bank.upper(), look.bold("h", fontSize=12)), P(s.heading, bold), dashes]
    story += [
        leader(s.labels["amount"].upper(), s.amount, look, 160),
        leader(s.labels["date"].upper(), s.date, look, 160),
        dashes,
    ]
    story += [P(s.labels["payer_acct"].upper(), bold), P(s.payer_acct, body)]
    if s.payer_name_shown:
        story.append(P(s.payer.name, body))
    story += [
        P(s.labels["payee_acct"].upper(), bold),
        P(s.payee_acct, body),
        P(s.payee.name, body),
        P(s.payee.address, body),
        dashes,
    ]
    story += [P(s.labels["title"].upper() + ":", bold), P(s.title, body)]
    if s.ref:
        story.append(leader(s.labels["ref"].upper(), s.ref, look, 160))
    story += [leader(k.upper(), v, look, 160) for k, v in s.extras]
    return [*story, dashes, P("*** DZIĘKUJEMY ***", look.style("c", alignment=1))]


def letter(s: Slip, pick: Pick) -> list:
    look = s.look
    body, bold = look.style(spaceAfter=7), look.bold()
    story = [
        P(f"{s.bank} S.A.", bold),
        P("ul. Bankowa 65, 00-665 Warszawa", body),
        P("Centrum Obsługi Klienta", body),
        gap(3),
    ]
    story += [
        P(f"Warszawa, {s.printed_at}", look.style("r", alignment=2)),
        P(s.payer.name, bold),
        P(s.payer.address, body),
        gap(4),
    ]
    story += [P(f"Dotyczy: {s.heading.lower()}", bold)]
    story += [
        P(
            f"Bank potwierdza, że w dniu {s.date} z rachunku nr {s.payer_acct}, prowadzonego dla {s.payer.name}, wykonano przelew "
            f"krajowy w kwocie {s.amount} na rachunek nr {s.payee_acct}, prowadzony dla {s.payee.name}, {s.payee.address}.",
            body,
        ),
        P(f"{s.labels['title']}: „{s.title}”.", body),
    ]
    if s.ref:
        story.append(P(f"{s.labels['ref']}: {s.ref}.", body))
    story += [P(f"{k}: {v}.", body) for k, v in s.extras]
    return [*story, P("Z poważaniem,", body), P("Dział Rozliczeń", body)]


def form(s: Slip, pick: Pick) -> list:
    look, body, bold = s.look, s.look.style(spaceAfter=2), s.look.bold(spaceAfter=2, spaceBefore=5)
    labels = s.labels
    story = [P(f"{s.bank.upper()} {s.heading}", look.bold("h", fontSize=12)), gap(2)]
    story += [P(labels["payer"], bold), P(f"Nazwa: {s.payer.name}", body), P(f"Adres: {s.payer.address}", body)]
    story += [P(f"{labels['payer_acct']}: {s.payer_acct}", body)]
    story += [P(labels["payee"], bold), P(f"Nazwa: {s.payee.name}", body), P(f"Adres: {s.payee.address}", body)]
    story += [P(f"{labels['payee_acct']}: {s.payee_acct}", body), P("Szczegóły operacji", bold)]
    story += [P(f"{labels['amount']}: {s.amount}", body), P(f"{labels['date']}: {s.date}", body)]
    if s.ref:
        story.append(P(f"{labels['ref']}: {s.ref}", body))
    story += [P(f"{labels['title']}: {s.title}", body)]
    return [*story, *[P(f"{k}: {v}", body) for k, v in s.extras]]


def business(s: Slip, pick: Pick) -> list:
    look, small, body, bold = s.look, lab(s.look), s.look.style(), s.look.bold()
    cells = [[P(s.labels["amount"], small), P(s.labels["date"], small), P(s.labels["ref"] if s.ref else "", small)]]
    cells.append([P(s.amount, bold), P(s.date, bold), P(s.ref or "", bold)])

    acct_w = max(stringWidth(a, bold.fontName, bold.fontSize) for a in (s.payer_acct, s.payee_acct)) / mm + 7

    def party(org: Org, acct: str) -> Table:
        head = [P("Nazwa i adres", small), P("Numer rachunku", small), P("Nazwa banku", small)]
        row = [P(f"{org.name}, {org.address}", body), P(acct, bold), P(s.bank.upper(), body)]
        return grid([head, row], [170 - acct_w - 28, acct_w, 28])

    story = [
        P(f"{s.bank} Spółka Akcyjna", bold),
        P("ul. Bankowa 12, 00-950 Warszawa", body),
        P(f"Nazwa firmy: {s.payer.name.upper()}", body),
    ]
    story += [
        P("Numer klienta: 273846", body),
        gap(3),
        P(s.heading, look.bold("h", fontSize=13)),
        P(s.labels["title"], small),
        P(s.title, body),
    ]
    story += [
        gap(2),
        grid(cells, [60, 45, 65]),
        P("Typ transakcji / Kod", small),
        P("225 PRZELEW INTERNETOWY", body),
        gap(2),
    ]
    first, second = (
        [("Dane odbiorcy", s.payee, s.payee_acct), ("Dane nadawcy", s.payer, s.payer_acct)]
        if s.swap
        else [("Dane nadawcy", s.payer, s.payer_acct), ("Dane odbiorcy", s.payee, s.payee_acct)]
    )
    for head, org, acct in (first, second):
        story += [P(head, bold), party(org, acct)]
    return [
        *story,
        gap(2),
        *[P(f"{k}: {v}", body) for k, v in s.extras],
        P(f"Dokument wygenerowany w dniu {s.printed_at}", small),
    ]


def statement(s: Slip, pick: Pick) -> list:
    look, body, bold = s.look, s.look.style(), s.look.bold()
    story = [
        P(f"{s.bank} Polska SA", look.bold("h", fontSize=12)),
        P(f"właściciel: {s.payer.name.upper()}", body),
        P(f"data wydruku: {s.printed_at}", body),
        gap(3),
    ]
    rows = [[P("Przelew z rachunku", bold), P("Szczegóły transakcji", bold)]]
    details = [
        ("Numer rachunku", s.payer_acct),
        ("Data waluty", s.date),
        (s.labels["date"], s.date),
        ("Rachunek odbiorcy:", s.payee_acct),
    ]
    details += [
        ("Nazwa odbiorcy:", s.payee.name),
        ("Tytuł:", s.title),
        ("Typ transakcji", "Przelew z rachunku"),
        (s.labels["amount"], s.amount),
    ]
    rows += [[P(k, body), P(v, bold if k == s.labels["amount"] else body)] for k, v in details]
    if s.ref:
        rows.append([P(s.labels["ref"], body), P(s.ref, body)])
    rows += [[P(k, body), P(v, body)] for k, v in s.extras]
    return [*story, grid(rows, [55, 115], lines="under"), P("Strona 1/1", look.style("r", alignment=2))]


def ledger(s: Slip, pick: Pick) -> list:
    look, small, body, bold = s.look, lab(s.look), s.look.style(), s.look.bold()
    left = f"{s.labels['date']}<br/>{e(s.date)}<br/>Data księgowania<br/>{e(s.booked)}"
    middle = f"PRZELEW ELIXIR - ONLINE<br/><b>z rachunku: {e(s.payer_acct)}</b><br/>{e(s.payer.name.upper())} {e(s.payer.address.upper())}<br/>"
    middle += f"<b>Na rachunek: {e(s.payee_acct)}</b><br/>{e(s.payee.name)}<br/>{e(s.labels['title'])}: {e(s.title)}"
    if s.ref:
        middle += f"<br/>{e(s.labels['ref'])}: {e(s.ref)}"
    head = [[P("Data", bold), P("Opis", bold), P(s.labels["amount"], bold)]]
    row = [[P(left, body, raw=True), P(middle, body, raw=True), P(s.amount, bold)]]
    story = [
        P(s.bank, look.bold("h", fontSize=13)),
        P(f"Data wydruku: {s.printed_at}", body),
        gap(3),
        grid(head + row, [35, 100, 35], lines="under"),
    ]
    return [
        *story,
        gap(4),
        *[P(f"{k}: {v}", body) for k, v in s.extras],
        rule(),
        P("Dokument jest wydrukiem komputerowym i nie wymaga podpisu.", small),
    ]


def stacked(s: Slip, pick: Pick) -> list:
    look, small, bold = s.look, lab(s.look), s.look.bold()
    items = [
        (s.labels["payer"], f"{s.payer.name}, {s.payer.address}"),
        (s.labels["payer_acct"], s.payer_acct),
        (s.labels["payee"], f"{s.payee.name}, {s.payee.address}"),
        (s.labels["payee_acct"], s.payee_acct),
    ]
    items = items[2:] + items[:2] if s.swap else items
    items += [(s.labels["amount"], s.amount), (s.labels["date"], s.date)]
    if s.ref:
        items.append((s.labels["ref"], s.ref))
    items += [(s.labels["title"], s.title), *s.extras]
    story = [P(s.heading, look.bold("h", fontSize=14)), P(s.bank, small), gap(4)]
    for label, value in items:
        story += [P(label, small), P(value, bold), gap(1.5)]
    return story


RENDER = {f.__name__: f for f in (boxes, leaders, letter, form, business, statement, ledger, stacked)}


def render(case: Case, rng: random.Random, faithful: bool = False) -> Rendered:
    pick = Pick(rng, faithful)
    rng = pick.rng
    t = case.transfer
    layout = pick("layout", LAYOUTS)
    title, amount, payee, payee_account, ref = payment(case, pick)
    family, size = LOOKS[layout]
    look = Look(family, size, page=pick("page", ["a4", "letter"], [9, 1]))
    date_style = pick("date", DATE_STYLES)
    amount_style = "debit_sign" if layout in {"statement", "ledger"} else pick("amount", AMOUNT_STYLES)
    if layout in {"statement", "ledger"}:
        pick.tags["amount"] = "debit_sign"
    account_style = pick("account", ACCOUNT_STYLES, ACCOUNT_WEIGHTS)
    payer_printed, payer_json = fmt_account(t.payer_account, account_style)
    if payee.name != UZP["name"] and pick.chance("foreign_account", 0.07):
        payee_account = iban(rng, rng.choice(["DE", "CZ", "LT"]))
        payee_printed, payee_json = fmt_account(payee_account, "code_grouped")
    else:
        payee_printed, payee_json = fmt_account(payee_account, account_style)
    labels = {key: pick(f"label_{key}", options) for key, options in LABELS.items()}
    after = t.date + timedelta(days=rng.randint(0, 1))
    extras = [("Status", pick("status", ["ZREALIZOWANO", "Zrealizowany", "Przelew zrealizowany"]))]
    extras += [("Kanał", rng.choice(["Serwis transakcyjny", "Bankowość internetowa", "Bankowość mobilna"]))]
    if pick.chance("fee_line", 0.4):
        extras.append(("Opłata", fmt_amount(0, "space_comma_pln")))
    if pick.chance("balance_line", 0.2):
        extras.append(("Saldo po operacji", fmt_amount(rng.randint(5000, 90000) + rng.random(), "space_comma_pln")))
    slip = Slip(
        case.transfer.payer,
        payee,
        payer_printed,
        payee_printed,
        fmt_amount(amount, amount_style),
        fmt_date(t.date, date_style),
        ref,
        title,
        case.transfer.bank,
        pick("heading", HEADINGS),
        f"{fmt_date(after, date_style)} {rng.randint(7, 18)}:{rng.randint(10, 59)}",
        fmt_date(after, date_style),
        labels,
        look,
        extras,
        pick.chance("swap_parties", 0.25),
        pick.chance("payer_name", 0.5),
    )
    gold = {
        "przelew_bankowy": {
            "data_operacji": t.date.isoformat(),
            "kwota": amount,
            "na_rachunek": payee_json,
            "numer_transakcji": ref,
            "tytul": title,
            "z_rachunku": payer_json,
        }
    }
    return Rendered(build_pdf(RENDER[layout](slip, pick), look), gold, {"class": "przelew", **pick.result()})
