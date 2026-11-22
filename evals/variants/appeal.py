"""Appeals to the KIO in three template families, with varied party blocks, wording, number formats and layouts."""

import random
from dataclasses import dataclass
from datetime import date, timedelta

from evals.variants.blocks import P, gap, grid, rule, sentence_end
from evals.variants.facts import Case, Org, nip
from evals.variants.gold import appeal_gold
from evals.variants.pdfkit import Look, Rendered, build_pdf
from evals.variants.vocab import Pick, fmt_amount, fmt_date, fmt_nip, fmt_ted

# What the authority did, completing "Zamawiający w dniu D ...", keyed by the dictionary id of the reason.
SHORT = {
    1: [
        "poinformował o odrzuceniu oferty złożonej przez Odwołującego",
        "odrzucił ofertę złożoną przez Odwołującego",
        "przekazał zawiadomienie o odrzuceniu oferty Odwołującego",
    ],
    2: [
        "ogłosił wybór oferty w postępowaniu prowadzonym na podstawie przepisów ustawy",
        "dokonał wyboru oferty najkorzystniejszej złożonej przez {other}",
        "poinformował wykonawców o wyborze oferty najkorzystniejszej",
    ],
    3: [
        "poinformował o wykluczeniu z postępowania podmiotu działającego wspólnie z Odwołującym",
        "wykluczył Odwołującego z postępowania",
        "zawiadomił o wykluczeniu Odwołującego z postępowania",
    ],
    4: [
        "opublikował Specyfikację Warunków Zamówienia",
        "udostępnił Specyfikację Warunków Zamówienia wraz z ogłoszeniem o zamówieniu",
        "opublikował SWZ",
    ],
    5: [
        "zmodyfikował treść Specyfikacji Warunków Zamówienia",
        "dokonał zmiany treści SWZ",
        "wprowadził zmiany do Specyfikacji Warunków Zamówienia",
    ],
    6: [
        "przekazał wykonawcom odpowiedzi i wyjaśnienia do treści Specyfikacji Warunków Zamówienia",
        "udzielił odpowiedzi na pytania wykonawców dotyczące SWZ",
        "opublikował wyjaśnienia treści SWZ",
    ],
    7: [
        "nie odrzucił oferty złożonej przez Odwołującego",
        "zaniechał odrzucenia oferty wykonawcy {other}",
        "nie odrzucił oferty wykonawcy {other}, mimo jej niezgodności z warunkami zamówienia",
    ],
    8: [
        "nie wykluczył z postępowania podmiotu działającego wspólnie z Odwołującym",
        "zaniechał wykluczenia wykonawcy {other} z postępowania",
        "nie wykluczył z postępowania wykonawcy {other}",
    ],
    9: [
        "unieważnił postępowanie",
        "unieważnił przedmiotowe postępowanie",
        "dokonał unieważnienia postępowania o udzielenie zamówienia",
    ],
    10: [
        "zaniechał unieważnienia postępowania",
        "nie unieważnił postępowania obarczonego wadą niemożliwą do usunięcia",
    ],
    11: [
        "udostępnił Opis Przedmiotu Zamówienia",
        "opublikował OPZ wraz z dokumentami zamówienia",
        "udostępnił opis przedmiotu zamówienia stanowiący załącznik do SWZ",
    ],
    12: [
        "opublikował projektowane postanowienia umowy",
        "udostępnił wzór umowy stanowiący załącznik do SWZ",
        "przekazał wykonawcom projektowane postanowienia umowy w sprawie zamówienia publicznego",
    ],
}
# The same acts as a charge in a numbered list ("polegających na: 1) ..."); {d} is the date of the act.
LONG = {
    1: [
        "odrzuceniu oferty Odwołującego na podstawie art. 226 ust. 1 pkt {n} Pzp, o którym Zamawiający zawiadomił pismem z dnia {d}",
        "odrzuceniu oferty Odwołującego w postępowaniu, o czym poinformowano wykonawców w dniu {d}",
    ],
    2: [
        "wyborze jako najkorzystniejszej oferty złożonej przez {other}, o którym Zamawiający poinformował wykonawców w dniu {d}",
        "wyborze oferty wykonawcy {other} jako najkorzystniejszej, ogłoszonym w dniu {d}",
    ],
    3: [
        "wykluczeniu Odwołującego z postępowania na podstawie art. 109 ust. 1 pkt {n} Pzp, o czym Zamawiający zawiadomił w dniu {d}",
        "wykluczeniu z postępowania podmiotu działającego wspólnie z Odwołującym, o czym Zamawiający poinformował w dniu {d}",
    ],
    4: [
        "ustaleniu treści Specyfikacji Warunków Zamówienia, opublikowanej wraz z ogłoszeniem o zamówieniu w dniu {d}",
        "opublikowaniu w dniu {d} Specyfikacji Warunków Zamówienia z postanowieniami naruszającymi przepisy ustawy",
    ],
    5: [
        "modyfikacji treści SWZ dokonanej w dniu {d}",
        "modyfikacji treści SWZ, dokonanej w dniu {d}, bez przedłużenia terminu składania ofert",
    ],
    6: [
        "udzieleniu w dniu {d} odpowiedzi na pytania wykonawców nr 3, 8 i 11 w sposób faktycznie zmieniający treść SWZ",
        "udzieleniu wyjaśnień treści SWZ w dniu {d} w sposób prowadzący do zmiany wymagań",
    ],
    7: [
        "zaniechaniu odrzucenia oferty wykonawcy {other}, pomimo jej niezgodności z warunkami zamówienia, ujawnionym w informacji o wyniku postępowania z dnia {d}",
        "zaniechaniu odrzucenia oferty wykonawcy {other}, co wynika z informacji Zamawiającego z dnia {d}",
    ],
    8: [
        "zaniechaniu wykluczenia z postępowania wykonawcy {other}, o czym Zamawiający poinformował w dniu {d}",
        "zaniechaniu wykluczenia wykonawcy {other} z postępowania, co wynika z informacji Zamawiającego z dnia {d}",
    ],
    9: [
        "unieważnieniu postępowania, o czym Zamawiający zawiadomił w dniu {d}",
        "unieważnieniu postępowania o udzielenie zamówienia, o którym zawiadomiono wykonawców w dniu {d}",
    ],
    10: [
        "zaniechaniu unieważnienia postępowania obarczonego wadą niemożliwą do usunięcia, ujawnionym w informacji z dnia {d}",
        "zaniechaniu unieważnienia postępowania, o czym Zamawiający poinformował w dniu {d}",
    ],
    11: [
        "opisaniu przedmiotu zamówienia w sposób utrudniający uczciwą konkurencję, w dokumentacji udostępnionej w dniu {d}",
        "określeniu Opisu Przedmiotu Zamówienia udostępnionego w dniu {d} z naruszeniem zasad równego traktowania wykonawców",
    ],
    12: [
        "ukształtowaniu projektowanych postanowień umowy w sposób naruszający równowagę stron, opublikowanych w dniu {d}",
        "ustaleniu projektowanych postanowień umowy udostępnionych w dniu {d}",
    ],
}
TOPICS = [
    (
        "naruszenia zasady uczciwej konkurencji i równego traktowania wykonawców",
        (
            "Zamawiający sformułował wymagania w sposób nieproporcjonalny do przedmiotu zamówienia, co ogranicza krąg "
            "potencjalnych wykonawców i prowadzi do nieuzasadnionego preferowania podmiotów o określonej technologii."
        ),
    ),
    (
        "naruszenia obowiązku sporządzenia dokumentacji postępowania w sposób przejrzysty",
        (
            "Dokumentacja postępowania nie zawiera pełnego uzasadnienia przyjętych rozstrzygnięć, co uniemożliwia "
            "weryfikację prawidłowości czynności Zamawiającego i ocenę jego stanowiska."
        ),
    ),
    (
        "naruszenia zasady proporcjonalności",
        (
            "Przyjęte rozwiązania wykraczają poza to, co jest niezbędne do osiągnięcia celu postępowania, a Zamawiający "
            "nie wykazał, że łagodniejsze środki nie byłyby wystarczające."
        ),
    ),
    (
        "błędnej oceny ofert ze względu na niejasne kryteria",
        (
            "Kryteria oceny ofert nie zostały sformułowane w sposób jednoznaczny, a sposób ich zastosowania nie został "
            "wyjaśniony, co uniemożliwia odtworzenie toku rozumowania Zamawiającego."
        ),
    ),
    (
        "naruszenia obowiązku wyjaśnienia treści dokumentów zamówienia",
        (
            "Udzielone wyjaśnienia są lakoniczne i nie odnoszą się do istoty zadanych pytań, przez co wykonawcy nie "
            "mogą należycie przygotować ofert."
        ),
    ),
]
BODY = [
    (
        "Odwołujący ma interes w uzyskaniu zamówienia i może ponieść szkodę polegającą na utracie możliwości jego "
        "uzyskania, a w konsekwencji na utracie zysku, który zamierzał osiągnąć w związku z jego realizacją."
    ),
    (
        "Zamawiający nie przedstawił rachunku ekonomicznego dla przyjętych rozwiązań ani nie wyjaśnił, dlaczego "
        "wymagania parametryczne odpowiadają najkorzystniejszemu rozwiązaniu dla przedmiotu zamówienia."
    ),
    (
        "Zgodnie z art. 534 ust. 1 Pzp strony i uczestnicy postępowania odwoławczego są obowiązani wskazywać dowody "
        "dla stwierdzenia faktów, z których wywodzą skutki prawne."
    ),
    (
        "Odwołanie zostało wniesione z zachowaniem terminu określonego w art. 515 ust. 1 Pzp, a jego kopię przekazano "
        "Zamawiającemu w sposób umożliwiający zapoznanie się z jego treścią przed upływem tego terminu."
    ),
    (
        "Wymaga podkreślenia, że celem postępowania odwoławczego jest przywrócenie stanu zgodnego z prawem, zanim "
        "dojdzie do zawarcia umowy w sprawie zamówienia publicznego."
    ),
    (
        "Odwołujący zastrzega sobie prawo do przedstawienia dalszych dowodów oraz do rozszerzenia zarzutów w toku "
        "postępowania odwoławczego, w szczególności w odpowiedzi na stanowisko Zamawiającego."
    ),
]
MODES = ["przetargu nieograniczonego", "przetargu ograniczonego", "negocjacji z ogłoszeniem", "dialogu konkurencyjnego"]
FAMILIES = ["lap", "formal", "letterhead"]
LABELS = {
    "appellant": ["Odwołujący:", "Wykonawca wnoszący odwołanie:", "Odwołujący (wykonawca):", "Wnoszący odwołanie:"],
    "authority": ["Zamawiający:", "Zamawiający (strona przeciwna):", "Instytucja zamawiająca:"],
    "number": ["nr referencyjny sprawy", "numer postępowania", "znak sprawy", "sygnatura postępowania"],
}
DNIA_STYLES = {"long_roku", "long_r", "dot", "dot_r"}
QUOTES = [("„", "”"), ('"', '"'), ("«", "»")]


@dataclass
class Ctx:
    case: Case
    pick: Pick
    rng: random.Random
    look: Look
    nip_style: str
    act_style: str
    other_nip: str
    reg_style: str
    reg_order: str

    @property
    def body(self):
        return self.look.style()

    @property
    def bold(self):
        return self.look.bold()

    @property
    def small(self):
        return self.look.style("small", fontSize=self.look.size - 1.5)

    def act(self, d: date) -> str:
        return fmt_date(d, self.act_style)


def registry(c: Ctx, org: Org) -> list:
    parts = [("KRS", org.krs), ("NIP", org.nip and fmt_nip(org.nip, c.nip_style)), ("REGON", org.regon)]
    if c.reg_order == "nip_first":
        parts = [parts[1], parts[2], parts[0]]
    parts = [(k, v) for k, v in parts if v]
    if not parts:
        return []
    style = c.reg_style
    if style == "inline":
        return [P(", ".join(f"{k}: {v}" for k, v in parts), c.body)]
    if style == "plain":
        return [P("  ".join(f"{k} {v}" for k, v in parts), c.body)]
    if style == "pipes":
        return [P(" | ".join(f"{k} {v}" for k, v in parts), c.body)]
    if style == "lines":
        return [P(f"{k}: {v}", c.look.style(spaceAfter=0)) for k, v in parts]
    width = [170 / len(parts)] * len(parts)
    return [grid([[P(k, c.small) for k, _ in parts], [P(v, c.body) for _, v in parts]], width, lines="box")]


def party(c: Ctx, label: str, org: Org, *, email: bool = False) -> list:
    out = [P(label, c.bold), P(org.name, c.bold), P(org.address, c.body), *registry(c, org)]
    if email and org.email:
        out.append(P(org.email, c.body))
    return [*out, gap(2)]


def authorities(c: Ctx) -> list:
    case = c.case
    if len(case.authorities) == 1:
        return party(c, c.pick("authority_label", LABELS["authority"], [6, 1, 1]), case.authorities[0], email=True)
    out = [
        P("Zamawiający (zamawiający wspólnie przeprowadzający postępowanie na podstawie art. 38 ust. 1 Pzp):", c.bold)
    ]
    for i, org in enumerate(case.authorities):
        role = "Lider, prowadzący postępowanie" if i == case.lead else "Partner"
        out += [P(f"{i + 1}) Zamawiający – {role}:", c.body), P(org.name, c.bold), P(org.address, c.body)]
        out += [*registry(c, org), gap(2)]
    return out


def representative(c: Ctx) -> list:
    case, firm = c.case, c.case.firm
    label = c.pick("representative", ["reprezentowany przez", "reprezentowana przez", "działający przez pełnomocnika"])
    names = ", ".join(a.titled for a in case.attorneys)
    mail = c.pick("mail_label", ["e-mail: ", "", "adres e-mail: ", "email: "], [4, 2, 1, 1])
    contact = f"tel. {case.phone}" + (f", {mail}{firm.email}" if firm.email else "")
    return [
        P(f"{label}: {names}", c.body),
        P(f"adres do korespondencji: {firm.name}, {firm.address}", c.body),
        P(contact, c.body),
    ]


def kio_block(c: Ctx) -> list:
    head = c.pick(
        "kio_head",
        ["Prezes Krajowej Izby Odwoławczej", "Krajowa Izba Odwoławcza", "Do: Prezes Krajowej Izby Odwoławczej"],
    )
    return [P(head, c.bold), P("ul. Postępu 17A", c.body), P("02-676 Warszawa", c.body), gap(2)]


def place_date(c: Ctx) -> list:
    case = c.case
    if not case.header:
        return []
    style = c.pick("header_date", ["long_roku", "dot", "iso", "long_r", "dot_r", "slash"], [3, 3, 1, 2, 1, 1])
    dnia = c.pick("header_dnia", [("dnia", "dnia "), ("no_dnia", "")], [4, 6]) if style in DNIA_STYLES else ""
    align = c.pick("header_align", ["right", "left"], [3, 2])
    text = f"{case.place}, {dnia}{fmt_date(case.appeal_date, style)}"
    return [P(text, c.look.style("pd", alignment={"right": 2, "left": 0}[align])), gap(2)]


def subject(c: Ctx) -> list:
    proc = c.case.procurement
    open_q, close_q = c.pick("title_quotes", [(f"{a}{b}", (a, b)) for a, b in QUOTES], [4, 1, 1])
    title = f"{open_q}{proc.title}{close_q}"
    number_label = c.pick("number_label", LABELS["number"])
    ted = None
    if proc.ted:
        number, year = proc.ted.split("-")
        ted = fmt_ted(
            int(number),
            int(year),
            c.rng.randint(1, 250),
            c.pick("ted_style", ["nnnnnn_yyyy", "yyyy_s_nnnnnn", "yyyy_s_compact"], [4, 1, 1]),
        )[0]
    bzp = proc.bzp and (
        proc.bzp.replace("BZP", "BZP ", 1) if c.pick("bzp_style", ["plain", "spaced"], [3, 1]) == "spaced" else proc.bzp
    )
    mode = c.pick("procedure_mode", MODES, [6, 2, 1, 1])
    style = c.pick("subject", ["sentence", "table", "labelled"], [5, 2, 2])
    if style == "sentence":
        text = f"postępowania o udzielenie zamówienia w trybie {mode} pn. {title} {number_label}: {proc.number}"
        text += f", ogłoszenie o zamówieniu nr {bzp}" if bzp else ""
        text += f", TED: {ted}" if ted else ""
        return [P("dotyczy:", c.bold), P(text, c.body), gap(2)]
    rows = [("Tytuł zamówienia", title), (number_label.capitalize(), proc.number)]
    rows += [("Ogłoszenie w BZP", bzp)] if bzp else []
    rows += [("Ogłoszenie w Dz. Urz. UE (TED)", ted)] if ted else []
    if style == "table":
        return [
            P("Dotyczy postępowania:", c.bold),
            grid([[P(k, c.small), P(v, c.body)] for k, v in rows], [50, 120], lines="grid"),
            gap(2),
        ]
    return [P(f"{k}: {v}", c.body) for k, v in rows] + [gap(2)]


def first_charge(c: Ctx, *, short: bool) -> str:
    case = c.case
    bank = SHORT if short else LONG
    template = c.rng.choice(bank[case.reason])
    d = c.act(case.act_date)
    return template.format(other=case.other_bidder, d=d, n=c.rng.choice([1, 2, 5, 7, 8, 10]))


def other_charges(c: Ctx, count: int) -> list[str]:
    reasons = [r for r in LONG if r != c.case.reason]
    out = []
    for r in c.rng.sample(reasons, count):
        d = c.case.act_date + timedelta(days=c.rng.choice([-9, -4, 1, 3, 6, 11]))
        out.append(c.rng.choice(LONG[r]).format(other=c.case.other_bidder, d=c.act(d), n=3))
    return out


def charge_sections(c: Ctx, count: int, *, subpoints: bool) -> list:
    out = []
    for k, (title, text) in enumerate(c.rng.sample(TOPICS, count), 1):
        out.append(P(f"Zarzut nr {k} {title}:", c.bold))
        if subpoints:
            out += [P(f"{k}.1. {text}", c.body), P(f"{k}.2. {c.rng.choice(BODY)}", c.body)]
        else:
            out.append(P(text, c.body))
    return out


def requests(c: Ctx, style: str = "numbered") -> list:
    if style == "training":
        items = [
            "wnoszę o zasądzenie na rzecz Odwołującego kosztów postępowania odwoławczego",
            "wnoszę o uwzględnienie odwołania w zakresie, w jakim zarzuty odwołania są zasadne",
            "wnoszę o oddalenie zarzutów odwołania",
        ]
        return [P(f"{i}.{i}) {t};", c.body) for i, t in enumerate(items, 1)]
    items = [
        "uwzględnienie odwołania w całości",
        "nakazanie Zamawiającemu powtórzenia czynności w postępowaniu",
        "zasądzenie od Zamawiającego na rzecz Odwołującego kosztów postępowania odwoławczego",
    ]
    return [P("Wnoszę o:", c.bold), *[P(f"{i}. {t};", c.body) for i, t in enumerate(items, 1)]]


def closing(c: Ctx, style: str = "numbered") -> list:
    attorney = c.case.attorneys[0]
    if style == "training":
        items = [
            "pełnomocnictwo udzielone przedstawicielowi Odwołującego",
            "dowód uiszczenia wadium",
            "wyciąg z rejestru przedmiotowego",
            "odwołanie wraz z uzasadnieniem",
        ]
        return [
            *[P(f"{i}.{i}) {t};", c.body) for i, t in enumerate(items, 1)],
            gap(4),
            P("." * 30, c.body),
            P(", ".join(part for part in (attorney.name, attorney.title) if part), c.body),
        ]
    items = [
        "pełnomocnictwo wraz z dowodem uiszczenia opłaty skarbowej",
        "dowód uiszczenia wpisu od odwołania",
        "dowód przekazania kopii odwołania Zamawiającemu",
    ]
    return [
        P("Załączniki:", c.bold),
        *[P(f"{i}) {t}", c.body) for i, t in enumerate(items, 1)],
        gap(6),
        P("Z poważaniem,", c.body),
        P(attorney.titled, c.bold),
        P("pełnomocnik Odwołującego", c.small),
    ]


def acting(c: Ctx, tail: str = "", ending: str = "wnoszę odwołanie", pzp: str = "„Pzp”") -> list:
    text = (
        f"Działając w imieniu wykonawcy {c.case.appellant.name} (dalej: „Odwołujący”), w oparciu o załączone "
        "pełnomocnictwo, na podstawie art. 513 pkt 1) i 2) w zw. z art. 515 ust. 2 pkt 1) lit. a) ustawy z dnia "
        f"11 września 2019 r. – Prawo zamówień publicznych (dalej: {pzp}), {ending}{tail}"
    )
    return [P(text, c.body)]


def lap(c: Ctx) -> tuple[list, int]:
    case = c.case
    first_party = c.pick("party_order", ["appellant_first", "authority_first"], [3, 2])
    kio_top = c.pick("kio_position", ["top", "after_subject"], [3, 2]) == "top"
    appellant = [
        *party(c, c.pick("appellant_label", LABELS["appellant"], [6, 1, 1, 1]), case.appellant),
        *representative(c),
        gap(2),
    ]
    blocks = [appellant, authorities(c)] if first_party == "appellant_first" else [authorities(c), appellant]
    story = [*place_date(c), *(kio_block(c) if kio_top else []), *blocks[0], *blocks[1]]
    story += [
        P(
            c.pick("title", ["ODWOŁANIE", "O D W O Ł A N I E", "Odwołanie"]),
            c.look.bold("h", fontSize=c.look.size + 3, alignment=1),
        ),
        gap(2),
    ]
    story += (
        subject(c)
        + ([] if kio_top else kio_block(c))
        + acting(
            c,
            ending=c.pick("wnosze", [("o:", "wnoszę o:"), ("odwolanie", "wnoszę odwołanie")], [3, 2]),
            pzp=c.pick("pzp", [("both", "„Prawo zamówień publicznych” lub „Pzp”"), ("short", "„Pzp”")], [1, 1]),
        )
    )
    sentence = c.pick("charge_lead", ["Zamawiający w dniu {d} {s}", "W dniu {d} Zamawiający {s}"])
    story.append(P(sentence_end(sentence.format(d=c.act(case.act_date), s=first_charge(c, short=True))), c.body))
    story += charge_sections(c, c.rng.randint(2, 3), subpoints=True)
    if c.pick.chance("deadline_line", 0.35):
        story.append(P(f"Termin składania ofert upływa w dniu {c.act(case.act_date + timedelta(days=21))}.", c.body))
    ending = c.pick("ending", ["training", "numbered"], [1, 1])
    return [*story, *requests(c, ending), *closing(c, ending)], 0


def formal(c: Ctx) -> tuple[list, int]:
    case = c.case
    head = [*place_date(c), *kio_block(c)]
    head += [
        *party(c, c.pick("appellant_label", LABELS["appellant"], [6, 1, 1, 1]), case.appellant),
        *representative(c),
        gap(2),
    ]
    head += [*authorities(c), *subject(c)]
    fee = c.rng.choice([7500, 10000, 15000])
    head += [
        P(f"Wpis od odwołania: {fmt_amount(fee, c.pick('fee_style', ['space_comma_zl', 'space_comma_pln']))}", c.body),
        gap(2),
    ]
    head += [
        P(
            c.pick("title", ["ODWOŁANIE", "O D W O Ł A N I E", "Odwołanie"]),
            c.look.bold("h", fontSize=c.look.size + 3, alignment=1),
        ),
        gap(2),
    ]
    story = acting(c, " wobec niezgodnych z przepisami ustawy czynności i zaniechań Zamawiającego, polegających na:")
    charges = [first_charge(c, short=False), *other_charges(c, c.rng.randint(1, 2))]
    story += [P(f"{i}) {t};", c.body) for i, t in enumerate(charges, 1)]
    story += charge_sections(c, c.rng.randint(2, 3), subpoints=False)
    story += requests(c)
    story += [P("UZASADNIENIE", c.bold), P("I. Stan faktyczny", c.bold)]
    rows = [["Data", "Zdarzenie"]]
    rows += [
        [
            c.act(case.act_date - timedelta(days=c.rng.randint(20, 40))),
            "Zawarcie porozumienia o wspólnym przeprowadzeniu postępowania.",
        ]
    ]
    rows += [[c.act(case.act_date), "Czynność Zamawiającego – zaskarżona czynność."]]
    rows += [
        [c.act(case.act_date + timedelta(days=c.rng.randint(15, 30))), "Wyznaczony termin składania i otwarcia ofert."]
    ]
    story += [grid([[P(x, c.small) for x in row] for row in rows], [35, 135], lines="grid"), gap(2)]
    story.append(
        P(
            f"Dotychczas usługi na rzecz Zamawiającego świadczył {case.other_bidder} (NIP {fmt_nip(c.other_nip, 'plain')}).",
            c.body,
        )
    )
    story += [P(t, c.body) for t in c.rng.sample(BODY, 4)]
    story += [P("II. Interes Odwołującego we wniesieniu odwołania oraz szkoda", c.bold)]
    story += [P(t, c.body) for t in c.rng.sample(BODY, 3)]
    return [*head, *story, *closing(c)], len(head)


def letterhead(c: Ctx) -> tuple[list, int]:
    case, firm = c.case, c.case.firm
    story = [
        P(firm.name, c.look.bold("lh", fontSize=c.look.size + 2, alignment=1)),
        P(firm.address, c.look.style("lc", alignment=1)),
    ]
    contact = f"tel. {case.phone}" + (f" · {firm.email}" if firm.email else "")
    story += [P(contact, c.look.style("lc2", alignment=1)), rule(), *place_date(c)]
    story += kio_block(c)
    story += [P(f"Znak sprawy kancelarii: {c.rng.randint(10, 99)}/{case.appeal_date.year}", c.small), gap(1)]
    story += party(c, "Odwołujący:", case.appellant)
    story += [
        P(f"pełnomocnik: {', '.join(a.titled for a in case.attorneys)} (pełnomocnictwo w załączeniu)", c.body),
        gap(2),
    ]
    story += authorities(c)
    story += [
        P(c.pick("title", ["ODWOŁANIE", "O D W O Ł A N I E"]), c.look.bold("h", fontSize=c.look.size + 3, alignment=1)),
        gap(2),
    ]
    story += subject(c) + acting(c)
    sentence = c.pick("charge_lead", ["Zamawiający w dniu {d} {s}", "W dniu {d} Zamawiający {s}"])
    story.append(P(sentence_end(sentence.format(d=c.act(case.act_date), s=first_charge(c, short=True))), c.body))
    story += charge_sections(c, c.rng.randint(2, 3), subpoints=True) + requests(c) + closing(c)
    return story, 0


RENDER = {"lap": lap, "formal": formal, "letterhead": letterhead}


def render(case: Case, rng: random.Random, faithful: bool = False) -> Rendered:
    pick = Pick(rng, faithful)
    family = pick("family", FAMILIES, [5, 3, 2])
    size = pick("size", [9, 9.5, 10, 10.5, 11], [1, 3, 3, 2, 1])
    look = Look(
        pick("font", ["sans", "serif"], [3, 2]),
        size,
        page=pick("page", ["a4", "letter"], [9, 1]),
        align=pick("align", ["left", "justify"], [3, 2]),
    )
    ctx = Ctx(
        case,
        pick,
        pick.rng,
        look,
        pick("nip_style", ["plain", "dashed", "spaced"], [6, 1, 1]),
        pick("act_date_style", ["long_roku", "long_r", "dot", "dot_r"], [4, 3, 2, 1]),
        nip(rng),
        pick("registry", ["inline", "lines", "pipes", "table", "plain"], [5, 1, 1, 1, 1]),
        pick("registry_order", ["krs_first", "nip_first"], [3, 1]),
    )
    story, head = RENDER[family](ctx)
    columns = 2 if family == "formal" and pick.chance("two_columns", 0.3) else 1
    pdf = build_pdf(story, look, columns=columns, footer="Strona {page}", head=head)
    return Rendered(pdf, appeal_gold(case), {"class": "odwolanie", **pick.result()})
