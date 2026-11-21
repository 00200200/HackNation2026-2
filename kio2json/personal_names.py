"""Resolve an inflected Polish personal name using its role and grammatical case."""

import re
from functools import cache, lru_cache
from itertools import product

from .common import PERSON, squash

# A professional title or honorific supplies the case of the name which follows it.
CASE_CUE = re.compile(
    r"(?P<dat>radcy\s+prawnemu|adwokatowi|panu|pani)|(?P<acc>radcę\s+prawnego|adwokata|pana|panią)", re.IGNORECASE
)
ATTESTED = re.compile(rf"(?im:^[ \t]*(?:pełnomocnik\s*:|pełnomocnictwo przyjmuję\s*:?)\s*)({PERSON})\b")


@cache
def _analyser():
    import morfeusz2

    return morfeusz2.Morfeusz(generate=False)


@lru_cache(maxsize=512)
def same_nominal_form(inflected: str, nominal: str) -> bool:
    """Confirm a genitive noun/adjective against its independently printed nominative."""

    def lemmas(word, case):
        return {
            (lemma, tag.split(":")[0])
            for _, _, (surface, lemma, tag, _, _) in _analyser().analyse(word)
            if surface == word and tag.split(":")[0] in {"subst", "adj"} and case in tag.split(":")[2].split(".")
        }

    return bool(lemmas(inflected, "gen") & lemmas(nominal, "nom"))


def _readings(word: str, label: str, case: str) -> set[tuple[str, str]]:
    result = set()
    for _, _, (surface, lemma, tag, labels, _) in _analyser().analyse(word):
        slots = tag.split(":")
        if surface != word or label not in labels or len(slots) < 4 or slots[0] != "subst":
            continue
        if "sg" in slots[1].split(".") and case in slots[2].split(".") and slots[3] in {"f", "m1"}:
            result.add((lemma.partition(":")[0], slots[3]))
    return result


def _name_readings(name: str, case: str, *, printed_given: bool = False) -> set[str]:
    parts = name.split()
    if len(parts) != 2:
        return set()
    given = _readings(parts[0], "imię", case)
    if printed_given:
        given |= {(lemma, gender) for lemma, gender in _readings(parts[0], "imię", "nom") if lemma == parts[0]}
    readings = [given, *(_readings(w, "nazwisko", case) for w in parts[1].split("-"))]
    return {
        variant[0][0] + " " + "-".join(word for word, _ in variant[1:])
        for variant in product(*readings)
        if len({gender for _, gender in variant}) == 1
    }


def nominative(name: str, case: str) -> str | None:
    names = _name_readings(name, case)
    return next(iter(names)) if len(names) == 1 else None


def compatible_names(printed: str, labelled: str) -> bool:
    """Check inflection only against an independently printed nominative name."""
    for inflected, nominal in zip(printed.casefold().split(), labelled.casefold().split(), strict=True):
        if inflected == nominal:
            continue
        if nominal.endswith("a"):
            forms = {nominal[:-1] + ending for ending in ("ą", "ę", "ej", "ie", "i", "y")}
            for ending, replacement in (
                ("da", "dzie"),
                ("ta", "cie"),
                ("ka", "ce"),
                ("ga", "dze"),
                ("ra", "rze"),
                ("ła", "le"),
            ):
                if nominal.endswith(ending):
                    forms.add(nominal[: -len(ending)] + replacement)
        elif nominal.endswith(("i", "y")):
            forms = {nominal[:-1] + ending for ending in ("ego", "emu", "iego", "iemu")}
        else:
            forms = {nominal + ending for ending in ("a", "owi", "u")}
        if inflected not in forms:
            return False
    return True


def resolve_attorneys(text: str, attorneys: list[dict]) -> list[dict]:
    if not attorneys:
        return attorneys
    attested = {squash(m[1]) for m in ATTESTED.finditer(text)}
    cues = {}
    for match in re.finditer(rf"\b(?i:{CASE_CUE.pattern})\s+({PERSON})\b", text, flags=0):
        cues.setdefault(squash(match[3]), set()).add("dat" if match["dat"] else "acc")
    for match in re.finditer(
        rf"(?i:\b(udziela(?:m|my|ją)?|ustanawia(?:m|my|ją)?|upoważnia(?:m|my|ją)?)\s*[:,]?\s*"
        rf"(?:(?:adwokat|adw\.|r\.\s*pr\.)\s+)?)({PERSON})\b",
        text,
    ):
        cues.setdefault(squash(match[2]), set()).add("dat" if match[1].lower().startswith("udziel") else "acc")
    for person in attorneys:
        name = person["imie_nazwisko"]
        if len(name.split()) != 2:
            continue
        candidates = {other for other in attested if compatible_names(name, other)}
        if len(candidates) == 1:
            person["imie_nazwisko"] = candidates.pop()
        elif not candidates and len(cues.get(name, set())) == 1:
            form = nominative(name, next(iter(cues[name])))
            if form:
                person["imie_nazwisko"] = form
    return attorneys


TITLED_ROW = re.compile(r"(?i:^[ \t]*(?:adw\.|r\.[ \t]*pr\.)[ \t]+)(\w+[ \t]+[\w-]+)[ \t]*[,;]?[ \t]*$")
LIST_START = re.compile(r"\b(udziela(?:m|my|ją)?|ustanawia(?:m|my|ją)?|upoważnia(?:m|my|ją)?)\s*:\s*$", re.IGNORECASE)


def repair_appointment_initials(page: str) -> str:
    """Distinguish capital I from L only in a scanned list governed by an appointment verb."""
    lines = page.split("\n")
    case = None
    for index, line in enumerate(lines):
        if start := LIST_START.search(line):
            case = "dat" if start[1].lower().startswith("udziel") else "acc"
            continue
        row = TITLED_ROW.fullmatch(line)
        if not row:
            case = None
            continue
        if case and row[1].startswith("l"):
            variants = [initial + squash(row[1])[1:] for initial in "IL"]
            attested = {
                squash(m[1])
                for m in ATTESTED.finditer(page)
                if any(compatible_names(v, squash(m[1])) for v in variants)
            }
            names = attested or {n for v in variants for n in _name_readings(v, case, printed_given=True)}
            if len(names) == 1:
                lines[index] = line[: row.start(1)] + names.pop() + line[row.end(1) :]
    return "\n".join(lines)
