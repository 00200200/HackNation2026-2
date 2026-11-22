"""Reference JSON of a generated case, in the organizer's schema (same keys as `data/uzp/dane/*/*.json`)."""

from evals.document_variants.facts import Case, Org, read_reasons


def appeal_gold(c: Case) -> dict:
    """The appeal reference: the first listed attorney is the representative, the first charge sets reason and date."""
    reasons = read_reasons()
    appellant = c.appellant
    return {
        "OdwolanieKIO": {
            "data": c.appeal_date.isoformat() if c.header else None,
            "czynnosc_dzien": c.act_date.isoformat(),
            "czynnosc_powod_id": c.reason,
            "czynnosc_opis": reasons[c.reason],
            "miejscowosc": c.place if c.header else None,
        },
        "Odwolujacy": [
            {
                "krs": appellant.krs,
                "nazwa": appellant.name,
                "nip": appellant.nip,
                "regon": appellant.regon,
                "przez-pelnomocnika": 1,
                "pelnomocnik": {"imie_nazwisko": c.attorneys[0].name, "nazwa": c.firm.name, "mail": c.firm.email},
            }
        ],
        "Zamawiajacy": [authority(a, c.lead, i) for i, a in enumerate(c.authorities)],
        "ZamowieniePubliczne": {
            "numer_bzp": c.procurement.bzp,
            "numer_postepowania": c.procurement.number,
            "numer_ted": c.procurement.ted,
            "tytul": c.procurement.title,
        },
    }


def authority(org: Org, lead: int | None, index: int) -> dict:
    return {
        "krs": org.krs,
        "nazwa": org.name,
        "nip": org.nip,
        "regon": org.regon,
        "prowadzacy_postepowanie": None if lead is None else int(index == lead),
    }


def poa_gold(c: Case) -> dict:
    return {
        "mocodawca": [
            {
                "data": {
                    "imie_nazwisko": g.person.name if g.person else None,
                    "krs": g.org.krs,
                    "nazwa": g.org.name,
                    "nip": g.org.nip,
                    "typ": "osoba_fizyczna" if g.person else "osoba_prawna",
                },
                "podpisujacy": [{"imie_nazwisko": s.name} for s in g.signers],
            }
            for g in c.grantors
        ],
        "pelnomocnicy": [{"imie_nazwisko": a.name, "pesel": a.pesel} for a in c.attorneys],
    }
