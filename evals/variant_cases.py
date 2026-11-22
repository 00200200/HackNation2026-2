"""Construct case-consistent documents from the organizer's public synthetic facts."""

import json
import random
import textwrap
from datetime import date

from evals.variant_pages import render

PROFILES = ("single-column", "two-column", "synonyms", "reordered", "alternative-formats", "scan")
NEGATIVES = {
    "bzp": ("Ogłoszenie o zamówieniu", "Biuletyn Zamówień Publicznych", "Termin składania ofert"),
    "ted": ("Ogłoszenie o udzieleniu zamówienia", "TED – wynik postępowania", "Wartość udzielonego zamówienia"),
    "ruling": ("WYROK", "Krajowa Izba Odwoławcza po rozpoznaniu odwołania orzeka", "Oddala odwołanie."),
    "invoice": ("Faktura VAT", "Sprzedawca i nabywca", "Należność ogółem"),
    "request": ("Wezwanie do zapłaty", "Prosimy o uregulowanie należności", "Termin płatności"),
    "pro-forma": ("Faktura pro forma", "Oferta cenowa", "Kwota do zapłaty przelewem"),
}
SEED = 63059


def dated(value, alternate):
    if not value:
        return ""
    return date.fromisoformat(value).strftime("%Y-%m-%d" if alternate else "%d.%m.%Y")


def registry(party):
    return ", ".join(f"{key.upper()} {party[key]}" for key in ("nip", "krs", "regon") if party.get(key))


def appeal(gold, synonym, alternate):
    meta = gold["OdwolanieKIO"]
    sections = [[", ".join(filter(None, [meta["miejscowosc"], dated(meta["data"], alternate)]))]]
    for party in gold["Zamawiajacy"]:
        role = "Instytucja zamawiająca" if synonym else "Zamawiający"
        if party.get("prowadzacy_postepowanie") is not None:
            role += " (prowadzący postępowanie)" if party["prowadzacy_postepowanie"] else " (uczestnik wspólny)"
        sections.append([role, party["nazwa"], registry(party)])
    for party in gold["Odwolujacy"]:
        block = ["Wykonawca wnoszący odwołanie" if synonym else "Odwołujący", party["nazwa"], registry(party)]
        if lawyer := party.get("pelnomocnik"):
            block += ["reprezentowany przez pełnomocnika", *filter(None, lawyer.values())]
        sections.append(block)
    proc = gold["ZamowieniePubliczne"]
    sections.append(
        list(
            filter(
                None,
                [
                    proc["tytul"],
                    "Numer postępowania: " + proc["numer_postepowania"] if proc["numer_postepowania"] else "",
                    "Ogłoszenie BZP: " + proc["numer_bzp"] if proc["numer_bzp"] else "",
                    "Ogłoszenie TED: " + proc["numer_ted"] if proc["numer_ted"] else "",
                ],
            )
        )
    )
    sections.append(
        [
            "Do Prezesa Krajowej Izby Odwoławczej",
            "Wnoszę odwołanie wobec czynności zamawiającego.",
            "Zaskarżona czynność: " + (meta["czynnosc_opis"] or ""),
            "Data czynności: " + dated(meta["czynnosc_dzien"], alternate),
        ]
    )
    return "Odwołanie do Krajowej Izby Odwoławczej", sections


def mandate(gold, synonym):
    sections = []
    for issuer in gold["mocodawca"]:
        party = issuer["data"]
        sections.append(
            list(
                filter(
                    None,
                    [
                        "Udzielający umocowania" if synonym else "Mocodawca",
                        party["typ"].replace("_", " "),
                        party["nazwa"],
                        party["imie_nazwisko"],
                        registry(party),
                        *[
                            "Podpis: " + name["imie_nazwisko"]
                            for name in issuer["podpisujacy"]
                            if name["imie_nazwisko"]
                        ],
                    ],
                )
            )
        )
    for lawyer in gold["pelnomocnicy"]:
        sections.append(
            [
                "Niniejszym upoważniam do reprezentowania przed Krajową Izbą Odwoławczą:",
                lawyer["imie_nazwisko"],
                *(["PESEL " + lawyer["pesel"]] if lawyer["pesel"] else []),
            ]
        )
    return "Pełnomocnictwo procesowe", sections


def receipt(gold, synonym, alternate):
    tx = gold["przelew_bankowy"]
    amount = f"{tx['kwota']:,.2f}".replace(",", " ").replace(".", ",") if alternate else f"{tx['kwota']:.2f}"
    sections = [
        ["Dzień wykonania operacji" if synonym else "Data operacji", dated(tx["data_operacji"], alternate)],
        ["Obciążenie" if synonym else "Kwota przelewu", amount + " PLN"],
        [
            "Konto zleceniodawcy" if synonym else "Z rachunku",
            " ".join(textwrap.wrap(tx["z_rachunku"], 4)) if alternate else tx["z_rachunku"],
        ],
        [
            "Konto beneficjenta" if synonym else "Na rachunek",
            " ".join(textwrap.wrap(tx["na_rachunek"], 4)) if alternate else tx["na_rachunek"],
        ],
        ["Opis płatności" if synonym else "Tytuł przelewu", tx["tytul"]],
        ["Referencja banku" if synonym else "Numer transakcji", tx["numer_transakcji"]],
    ]
    if alternate:
        sections = [[f"{key}: {value}"] for key, value in reversed(sections)]
    return ("Wyciąg operacji – potwierdzenie realizacji" if alternate else "Potwierdzenie przelewu"), sections


def generate(folder, index, seed, profile, negative):
    rng = random.Random(f"{seed}/{index}/{folder.name}")
    a, p, t = [
        json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("odwolanie", "pelnomocnictwo", "przelew")
    ]
    proc = a["ZamowieniePubliczne"]
    tx = t["przelew_bankowy"]
    # Substitute both the identifiers and every occurrence in the transfer narrative.
    for record, key, prefix in [(proc, "numer_postepowania", "ZP"), (tx, "numer_transakcji", "TR")]:
        if original := record[key]:
            record[key] = f"{prefix}/{rng.randrange(100000, 1000000)}/2026"
            tx["tytul"] = tx["tytul"].replace(original, record[key])
    for key in ("z_rachunku", "na_rachunek"):
        if rng.choice((True, False)):
            tx[key] = "PL" + tx[key]
    synonym, alternate = profile == "synonyms", profile == "alternative-formats"
    docs = []
    for gold, (title, sections) in [
        (a, appeal(a, synonym, alternate)),
        (p, mandate(p, synonym)),
        (t, receipt(t, synonym, alternate)),
    ]:
        if profile == "reordered":
            rng.shuffle(sections)
        docs.append((profile, gold, render(title, sections, profile, rng)))
    title, intro, purpose = NEGATIVES[negative]
    sections = [
        [intro, proc["tytul"] or "", proc["numer_postepowania"] or ""],
        ["Zamawiający: " + a["Zamawiajacy"][0]["nazwa"]],
    ]
    if negative in ("invoice", "request", "pro-forma"):
        sections += [[purpose, f"{tx['kwota']:.2f} PLN", "Rachunek do wpłaty: " + tx["na_rachunek"]]]
    else:
        sections += [
            [
                purpose,
                {"ruling": "Kosztami obciąża odwołującego.", "bzp": "18 grudnia 2026 r.", "ted": "340 000 PLN"}[
                    negative
                ],
            ]
        ]
    docs.append((negative, {}, render(title, sections, profile, rng)))
    rng.shuffle(docs)
    return docs
