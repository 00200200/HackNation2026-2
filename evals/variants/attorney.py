"""Powers of attorney in prose, clause and table layouts, for one or two grantors and one or two attorneys."""

import random

from evals.variants.blocks import P, gap, grid, sentence_end
from evals.variants.facts import Case, Grantor
from evals.variants.gold import poa_gold
from evals.variants.pdfkit import Look, Rendered, build_pdf
from evals.variants.vocab import Pick, fmt_date, fmt_nip

LAYOUTS = ["prose", "clauses", "table"]
GENITIVE = {"Wykonawca": "Wykonawcy", "Mocodawca": "Mocodawcy"}
DOTS = "............................................"
SCOPE = [
    "zasięgania informacji o dokumentacji postępowania i jej udostępniania {who}",
    "składania i odbierania pism procesowych, wniosków dowodowych i oświadczeń w imieniu {who}",
    "udzielania dalszych pełnomocnictw radcom prawnym i adwokatom",
    "odbioru dokumentów i korespondencji kierowanej do {who} w postępowaniu",
    "wniesienia odwołania do Prezesa Krajowej Izby Odwoławczej oraz jego cofnięcia",
    "zastępowania {who} na posiedzeniach i rozprawach przed Krajową Izbą Odwoławczą",
    "wniesienia skargi na orzeczenie Krajowej Izby Odwoławczej do sądu zamówień publicznych",
]


def numbers(c: Case, g: Grantor, nip_style: str, *, krs_words: bool) -> str:
    """The registry numbers of one grantor as running text; only the numbers the grantor has."""
    org = g.org
    parts = []
    if org.krs:
        parts.append(f"KRS {org.krs}")
    if org.nip:
        parts.append(f"NIP {fmt_nip(org.nip, nip_style)}")
    if org.regon:
        parts.append(f"REGON {org.regon}")
    if krs_words and org.krs:
        parts[0] = f"wpisana do rejestru przedsiębiorców Krajowego Rejestru Sądowego pod numerem {parts[0]}"
    return ", ".join(parts)


def attorney_text(c: Case, pick: Pick) -> str:
    items = []
    for a in c.attorneys:
        extra = [f"nr wpisu na listę: {a.bar_no.replace('-', ' ', 1)}"] if a.bar_no else []
        if a.pesel:
            extra.append(f"PESEL: {a.pesel}")
        items.append(f"{a.titled} ({', '.join(extra)})" if extra else a.titled)
    return pick("attorney_join", [", ", " oraz "]).join(items)  # the training powers join two attorneys with a comma


def procedure(c: Case, pick: Pick) -> str:
    proc = c.procurement
    number_label = pick("poa_number", ["numer postępowania", "znak sprawy", "nr referencyjny"])
    return (
        f"w postępowaniu o udzielenie zamówienia publicznego pn. „{proc.title}”, {number_label}: {proc.number}, "
        f"prowadzonym przez {c.authorities[0].name}"
    )


def signature_blocks(c: Case, pick: Pick, look: Look, *, each: bool) -> list:
    """Dotted line, name and role for every signer; with several grantors, headed by "W imieniu X:"."""
    body, small = look.style(spaceAfter=1), look.style("small", fontSize=look.size - 1.5)
    out = []
    for g in c.grantors:
        if each:
            out.append(P(f"W imieniu {g.org.name}:", body))
        for s in g.signers:
            out += [gap(5), P(DOTS, body), P(s.name, look.bold(spaceAfter=0))]
            if s.role and g.person is None:
                out.append(P(s.role, small))
    if pick.chance("acceptance", 0.5):
        out += [gap(5), P("Pełnomocnictwo przyjmuję:", body)]
        for a in c.attorneys:
            out += [gap(4), P(DOTS, body), P(a.titled, look.bold(spaceAfter=0))]
    return out


def sole_trader(c: Case, g: Grantor, pick: Pick, look: Look, nip_style: str) -> list:
    """The training wording for a sole trader: a first-person statement, then a scope list that ends the sentence."""
    body = look.style()
    first = sentence_end(
        f"Ja, niżej podpisany {g.person.name}, prowadzący działalność gospodarczą pod firmą {g.org.name}, {g.org.address}, "
        f"{numbers(c, g, nip_style, krs_words=False)}, wpisany do Centralnej Ewidencji i Informacji o Działalności "
        f"Gospodarczej (dalej: „Mocodawca”), niniejszym udzielam pełnomocnictwa: {attorney_text(c, pick)}"
    )
    second = (
        f"Pełnomocnictwo udzielone zostaje do reprezentowania Mocodawcy {procedure(c, pick)}, a w szczególności do:"
    )
    return [P(first, body), P(second, body), *scope(pick, look, "Mocodawcy", marker="numbers")[1:]]


def prose(c: Case, pick: Pick, look: Look, nip_style: str) -> list:
    body = look.style()
    label = pick("grantor_label", ["Wykonawca", "Mocodawca"])
    heading = pick("poa_title", ["PEŁNOMOCNICTWO", "PEŁNOMOCNICTWO PROCESOWE", "Pełnomocnictwo"])
    story = [P(heading, look.bold("h", fontSize=look.size + 3, alignment=1)), gap(2)]
    if len(c.grantors) == 1:
        g = c.grantors[0]
        if g.person and pick("sole_trader_wording", ["training", "acting_in_own_name"]) == "training":
            return [
                *story,
                *sole_trader(c, g, pick, look, nip_style),
                gap(3),
                *signature_blocks(c, pick, look, each=False),
            ]
        if g.person:
            who = (
                f"Działając we własnym imieniu jako {g.person.name}, przedsiębiorca prowadzący działalność gospodarczą "
                f"pod firmą {g.org.name} (dalej: „{label}”), {numbers(c, g, nip_style, krs_words=False)}"
            )
        else:
            who = f"Działając w imieniu {g.org.name} (dalej: „{label}”), {numbers(c, g, nip_style, krs_words=True)}"
        who = sentence_end(
            f"{who}, niniejszym upoważniam {attorney_text(c, pick)} do reprezentowania {GENITIVE[label]} {procedure(c, pick)}"
        )
        story.append(P(who, body))
    else:
        listed = "; ".join(
            f"{i}) {g.org.name}, {g.org.address}, {numbers(c, g, nip_style, krs_words=False)}"
            for i, g in enumerate(c.grantors, 1)
        )
        text = sentence_end(
            f"Wykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum): {listed} (dalej łącznie: "
            f"„Mocodawca”), reprezentowani przez osoby podpisane poniżej, udzielają pełnomocnictwa: "
            f"{attorney_text(c, pick)} do reprezentowania Mocodawcy {procedure(c, pick)}"
        )
        story.append(P(text, body))
    story += scope(pick, look, GENITIVE[label] if len(c.grantors) == 1 else "Mocodawcy")
    return [*story, gap(3), *signature_blocks(c, pick, look, each=len(c.grantors) > 1)]


def scope(pick: Pick, look: Look, who: str, marker: str | None = None) -> list:
    body = look.style()
    items = pick("scope_count", [("3", 3), ("4", 4), ("5", 5)])
    marker = marker or pick("scope_marker", ["letters", "numbers"])
    chosen = [SCOPE[i].format(who=who) for i in sorted(pick.rng.sample(range(len(SCOPE)), items))]
    labels = "abcdefg" if marker == "letters" else "1234567"
    suffix = ")" if marker == "letters" else "."
    return [P("Pełnomocnictwo obejmuje umocowanie do:", body)] + [
        P(f"{labels[i]}{suffix} {text}{';' if i < len(chosen) - 1 else '.'}", body) for i, text in enumerate(chosen)
    ]


def clauses(c: Case, pick: Pick, look: Look, nip_style: str) -> list:
    body, bold = look.style(), look.bold()
    story = [P("PEŁNOMOCNICTWO", look.bold("h", fontSize=look.size + 3, alignment=1)), gap(2)]
    for i, g in enumerate(c.grantors, 1):
        kind = f"{g.person.name}, prowadzący działalność gospodarczą pod firmą " if g.person else ""
        story.append(
            P(
                f"§ {i}. Mocodawca: {kind}{g.org.name}, {g.org.address}, {numbers(c, g, nip_style, krs_words=False)}.",
                body,
            )
        )
    n = len(c.grantors)
    story += [P(f"§ {n + 1}. Mocodawca udziela pełnomocnictwa: {attorney_text(c, pick)}.", body)]
    story += [P(sentence_end(f"§ {n + 2}. Pełnomocnik jest uprawniony do działania {procedure(c, pick)}"), body)]
    story += [P(f"§ {n + 3}. Zakres pełnomocnictwa:", bold), *scope(pick, look, "Mocodawcy")[1:]]
    return [*story, gap(3), *signature_blocks(c, pick, look, each=n > 1)]


def table(c: Case, pick: Pick, look: Look, nip_style: str) -> list:
    body, small, bold = look.style(), look.style("small", fontSize=look.size - 1.5), look.bold()
    grantors = []
    for g in c.grantors:
        lines = [P(g.org.name, bold), P(g.org.address, body)]
        if g.person:
            lines.append(P(f"osoba fizyczna: {g.person.name}", body))
        lines.append(P(numbers(c, g, nip_style, krs_words=False), body))
        grantors += lines + [gap(2)]
    attorneys = []
    for a in c.attorneys:
        attorneys += [P(a.titled, bold)]
        attorneys += [P(f"nr wpisu: {a.bar_no}", body)] if a.bar_no else []
        attorneys += [P(f"PESEL: {a.pesel}", body)] if a.pesel else []
        attorneys += [P(c.firm.name, small), gap(2)]
    story = [
        P(
            pick("poa_title", ["PEŁNOMOCNICTWO", "PEŁNOMOCNICTWO PROCESOWE"]),
            look.bold("h", fontSize=look.size + 3, alignment=1),
        ),
        gap(2),
    ]
    story += [
        grid([[P("MOCODAWCA", small), P("PEŁNOMOCNIK", small)], [grantors, attorneys]], [85, 85], lines="grid"),
        gap(3),
    ]
    story += [P(sentence_end(f"Mocodawca udziela pełnomocnictwa do reprezentowania go {procedure(c, pick)}"), body)]
    story += scope(pick, look, "Mocodawcy")
    return [*story, gap(3), *signature_blocks(c, pick, look, each=len(c.grantors) > 1)]


def render(case: Case, rng: random.Random, faithful: bool = False) -> Rendered:
    pick = Pick(rng, faithful)
    layout = pick("poa_layout", LAYOUTS, [5, 2, 2])
    look = Look(
        pick("font", ["sans", "serif"], [3, 2]),
        pick("size", [9.5, 10, 10.5, 11], [2, 3, 3, 1]),
        page=pick("page", ["a4", "letter"], [9, 1]),
        align=pick("align", ["left", "justify"], [3, 2]),
    )
    nip_style = pick("nip_style", ["plain", "dashed", "spaced"], [6, 1, 1])
    # Tags that come from the facts, not from a choice: they are the same in the control and the drifted set.
    pick.tags["grantor_quotes"] = "yes" if any("„" in g.org.name for g in case.grantors) else "no"
    pick.tags["grantors"] = str(len(case.grantors))
    pick.tags["attorneys"] = str(len(case.attorneys))
    spelled_out = any(a.title and not a.title.endswith(".") for a in case.attorneys)
    pick.tags["attorney_titles"] = "spelled_out" if spelled_out else "abbreviated"
    story = []
    if pick("poa_header", [("yes", True), ("no", False)], [8, 2]):
        style = pick("poa_date", ["long", "long_r", "dot", "iso"], [3, 2, 2, 1])
        story += [P(f"{case.place}, {fmt_date(case.poa_date, style)}", look.style("pd", alignment=2)), gap(2)]
    build = {"prose": prose, "clauses": clauses, "table": table}[layout]
    story += build(case, pick, look, nip_style)
    return Rendered(build_pdf(story, look, footer=""), poa_gold(case), {"class": "pelnomocnictwo", **pick.result()})
