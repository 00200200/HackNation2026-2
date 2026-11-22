"""Select the operative appeal clause and read its Polish predicate, polarity and object."""

import re
from functools import lru_cache

from .appeal import REASONS
from .appeal_charges import act_date, raw_sentences
from .common import DATE, squash, to_iso
from .personal_names import _analyser

# An appeal can declare its object before listing it, or refer back after the list.
_FILING = re.compile(
    r"\bodwołanie\s+(?:(?:wnoszę|wnosimy|wnosi|składam|składamy)\s+)?"
    r"(?:od|wobec|na|dotyczy|obejmuje)\b|\bprzedmiotem\s+odwołania\s+(?:jest|są)\b|"
    r"\bodwołuj(?:ę|emy)\s+się\s+od\b|\b(?:zaskarżam(?:y)?|skarż(?:ę|ymy)|kwestionuj(?:ę|emy))\b|"
    r"\bodwołujący\s+(?:zaskarża|kwestionuje)\b",
    re.IGNORECASE,
)
_CAPTION = re.compile(
    r"(?im)^[ \t]*(?:(?:[IVX]+|\d+)[.)]\s*)?(?:zarzuty|zaskarżone czynności|zakres zaskarżenia|"
    r"(?:odwołujący )?zarzuca(?:m|my)?(?: zamawiającemu)?)[^\n]{0,75}:?[ \t]*$"
)
_RETROSPECTIVE = re.compile(r"(?i)\b(?:powyższ\w*|wskazan\w*|te)\s+(?:czynności|zaniechania)\b")
_FIRST = re.compile(r"(?im)^[ \t]*(?:\([1ia]\)|[1ia][.)])(?:[ \t]+|(?=$))")
_STOP = re.compile(
    r"(?im)^[ \t]*(?:(?:\([2-9b-h]\)|(?:[2-9]|II|[b-h])[.)])\s+|"
    r"(?:zarzut (?:drugi|nr 2)|uzasadnienie|żądania|wnioski|wnosz[ęą] o|załączniki|dowody)\b)|"
    r"\b(?:ewentualn\w*|alternatywnie|subsydiarn\w*|pomocniczo|z ostrożności|na wypadek)\b|"
    r"(?<=[.;])\s+(?:2|II|b)[.)]\s+"
)
_HISTORY = re.compile(
    r"(?i)\b(?:(?:poprzedni|dawniejsz|wcześniejsz)\w* (?:odwołani\w*|spraw\w*)|(?:oddalił|rozpoznał|wycofał)\w* odwołani\w*|historyczn\w*|wyroki?\w*|inny (?:oferent|wykonawca)|konkurent|przystępujący|cytuj\w*|wówczas)\b"
)
_NOTICE = re.compile(
    rf"\b(?:o (?:tej czynności|tym fakcie|czym|któr\w+)|"
    rf"(?:informacj\w*|zawiadomieni\w*) (?:o tym|o tej czynności|w tej sprawie))"
    rf"(?:\s+(?:odwołując\w*|wykonawc\w*|spół\w*|nas|mnie|został\w*)){{0,4}}\s+"
    rf"(?:zawiadom\w*|powiadom\w*|poinform\w*|doręcz\w*|otrzym\w*|przekaz\w*)"
    rf"(?:\s+(?:nas|mnie|odwołując\w*|wykonawc\w*|pismem|z|w|dniu|dnia))*\s+({DATE})",
    re.IGNORECASE,
)


def first_phrase(text: str) -> str | None:
    """Return a bounded source passage, including a directly following notice sentence."""
    for anchor in sorted((*_FILING.finditer(text), *_CAPTION.finditer(text)), key=lambda m: m.start()):
        before = text[: anchor.start()]
        context = re.split(r"[.!?\n]", before)[-1]
        if _HISTORY.search(context + anchor[0]) or _STOP.search(context):
            continue
        if re.search(r"(?im)^\s*(?:załączniki|dowody)\s*:", before):
            break
        start = anchor.end()
        remainder = text[start : start + 1500]
        # A standalone subject field below the title introduces the procurement.
        if re.search(r"\n\s*dotyczy$", anchor[0], re.IGNORECASE) and remainder.lstrip().startswith(":"):
            continue
        # Unnumbered lists use the same dash for the first and later items.
        bullets = list(re.finditer(r"(?m)^[ \t]*[-–—][ \t]+", remainder))
        if bullets and remainder[: bullets[0].start()].rstrip().endswith(":"):
            end = bullets[1].start() if len(bullets) > 1 else len(remainder)
            return _STOP.split(remainder[bullets[0].end() : end], maxsplit=1)[0].strip()
        first = _FIRST.search(remainder)
        if first and (
            not remainder[: first.start()].strip(" \t\n:–-")
            or re.fullmatch(r"[^.;:]{1,155}:\s*", remainder[: first.start()])
        ):
            start += first.end()
        elif anchor.re is _CAPTION or _RETROSPECTIVE.match(remainder.lstrip(" :")):
            continue
        return _STOP.split(text[start : start + 1500], maxsplit=1)[0].strip(" \t\n:–-")
    for item in _FIRST.finditer(text):
        prior = text[: item.start()]
        if re.search(r"(?im)^\s*(?:wnoszę o|żądania|załączniki|dowody|wnioski)\b", prior):
            continue
        rest = text[item.end() :]
        if _RETROSPECTIVE.search(rest) and re.search(r"\bodwołanie\b", rest, re.IGNORECASE):
            return _STOP.split(rest, maxsplit=1)[0].strip()
    return None


@lru_cache(maxsize=4096)
def _lemmas(word: str) -> frozenset[str]:
    values = {word}
    parts = set()
    for _, _, (surface, lemma, tag, _, _) in _analyser().analyse(word):
        if surface.casefold() == word:
            values.add(lemma.partition(":")[0].casefold())
            parts.add(tag.partition(":")[0])
            if tag.endswith(":neg"):
                values.add("nie")
    if parts == {"subst"}:
        values.add("<noun>")
    return frozenset(values)


# Inflected nouns, participles and conjugated verbs typically share an infinitive.
_PREDICATES = {
    1: {"odrzucić", "odrzucenie", "odrzucać"},
    2: {"wybrać", "wybór", "wybranie"},
    3: {"wykluczyć", "wykluczenie", "wykluczać"},
    5: {"modyfikacja", "zmiana", "modyfikować", "zmienić", "zmodyfikować"},
    6: {"odpowiedź", "odpowiedzieć", "wyjaśnienie", "wyjaśnić"},
    9: {"unieważnić", "unieważnienie", "unieważniać"},
    11: {"opis", "opisać", "opisywać"},
    12: {"projekt", "projektować", "warunek", "postanowienie", "wzór", "klauzula"},
}
_SPEC = {"swz", "siwz", "specyfikacja"}
_PERSON = {"wykonawca", "odwoływać", "oferent", "przedsiębiorca", "konkurent", "my", "nas", "mnie", "spółka"}
_OBJECTS = {1: {"oferta"}, 2: {"oferta"}, 3: _PERSON, 5: _SPEC, 6: _SPEC, 9: {"postępowanie"}, 12: {"umowa"}}
_OMISSION = {"zaniechać", "zaniechanie", "brak"}
_OPPOSITE = {1: 7, 3: 8, 9: 10}
_OTHER_OBJECT = {
    "odmowa",
    "kopia",
    "wniosek",
    "termin",
    "protokół",
    "faktura",
    "skarga",
    "wezwanie",
    "wadium",
    "reklamacja",
    "możliwość",
}
_PUBLICATION = {"publikacja", "opublikować", "ogłosić", "ogłoszenie", "udostępnić", "treść", "postanowienie"}


def reason_id(passage: str) -> int | None:
    opening = squash(next(raw_sentences(passage)))
    # Introductory legal grounds can precede the clause describing the act.
    opening = re.split(r"\b(?:poprzez|polegając\w* na)\s+", opening, maxsplit=1, flags=re.IGNORECASE)[-1]
    opening = re.split(
        r"\b(?:natomiast|zaś|a następnie|mimo że|pomimo|chociaż|podczas gdy|na podstawie|zgodnie z|gdyż)\b",
        opening,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    if re.search(r"\bnie(?:powiązan|związan)\w*\s+z\b", opening, re.IGNORECASE):
        return None
    words = [_lemmas(w) for w in re.findall(r"[^\W\d_]+", opening.casefold())[:70]]
    for index, token in enumerate(words):
        if token & {"lub", "albo", "bądź"}:
            left_acts = {code for code, verbs in _PREDICATES.items() if any(w & verbs for w in words[:index])}
            right_acts = {code for code, verbs in _PREDICATES.items() if any(w & verbs for w in words[index + 1 :])}
            if left_acts and right_acts - left_acts:
                return None
    for i, token in enumerate(words):
        if token & {"opz"}:
            return 11
        if token & _OTHER_OBJECT:
            return None
        # Object ownership can follow the action (wykluczenie nas) or precede
        # a passive verb (nasza oferta została odrzucona).
        after = words[i + 1 : i + 12]
        before = words[max(0, i - 7) : i]
        nearby = set().union(*after)
        left = set().union(*before)
        if "warunek" in token and "udział" in nearby and "postępowanie" in nearby:
            return 4
        for code, verbs in _PREDICATES.items():
            if token.isdisjoint(verbs):
                continue
            if code == 11:
                if {"przedmiot", "zamówienie"} <= nearby:
                    return code
                continue
            objects = _OBJECTS[code]
            # In the direct-object position a different noun owns the predicate.
            # Later prepositional complements can give the setting or name a party.
            governed = next((w for w in after if w & {"<noun>", "pytanie"} or w & objects), set())
            if (
                governed
                and not governed & (objects | {"dokument", "treść"})
                and not (code == 6 and "pytanie" in governed)
                and not any(w & {"przez", "z", "w", "do", "spośród"} for w in after[: after.index(governed)])
            ):
                if code == 12:
                    continue
                return None
            first_object = next((word for word in after if word & (objects | _OTHER_OBJECT)), set())
            forward = bool(first_object & objects)
            passive = bool(left & objects and left & {"być", "zostać"})
            if forward or passive:
                # Separate predicate negation from an incidental negative adjective.
                negated_auxiliary = any(
                    "nie" in word and (word == _lemmas("nie") or "dokonać" in word) for word in before[-2:]
                )
                omitted = bool(
                    left & _OMISSION
                    or "nie" in token
                    or negated_auxiliary
                    or any({"dokonać", "nie"} <= word for word in before)
                )
                return _OPPOSITE.get(code) if omitted else code
            # Contract terms are also used for specifications and entry conditions.
            if code != 12:
                return None
        if token & _SPEC and (i == 0 or left & _PUBLICATION):
            return 4
    return None


def phrase_day(passage: str, reason: int) -> str | None:
    clauses = iter(raw_sentences(squash(passage)))
    first_clause = next(clauses)
    opening = re.split(r"\b(?:natomiast|podczas gdy|zaś|a następnie)\b", first_clause, maxsplit=1, flags=re.IGNORECASE)[
        0
    ]
    next_clause = next(clauses, "").strip() if opening == first_clause else ""
    if (notice := _NOTICE.search(opening)) or (notice := _NOTICE.match(next_clause)):
        return to_iso(notice[1])
    if received := re.match(
        rf"(?:zawiadomienie|informację o tej (?:decyzji|czynności))\s+"
        rf"(?:otrzyma(?:łem|łam|liśmy)|doręczono nam|przekazano nam)\s+(?:w dniu |dnia )?({DATE})",
        next_clause,
        re.IGNORECASE,
    ):
        return to_iso(received[1])
    if reason in (4, 5, 6, 11, 12):
        publication = re.search(
            rf"\b(?:si?wz|specyfikacj\w*|opz|umow\w*)\s+(?:został\w*\s+)?"
            rf"(?:opublikowan\w*|zamieszczon\w*)\s+(?:w dniu |dnia )?({DATE})",
            opening,
            re.IGNORECASE,
        )
        if publication:
            return to_iso(publication[1])
    if direct := re.search(
        rf"\(\s*(?:decyzja|zawiadomienie|informacja)\s+(?:z dnia|z)\s+({DATE})", opening, re.IGNORECASE
    ):
        return to_iso(direct[1])
    return act_date(opening, reason)


def fill_missing_action(header: dict, text: str) -> None:
    """Only fill an appeal left without a reason by the complete extraction pipeline."""
    if (
        not {"czynnosc_powod_id", "czynnosc_opis", "czynnosc_dzien"} <= header.keys()
        or header["czynnosc_powod_id"] is not None
    ):
        return
    phrase = first_phrase(text)
    if not phrase or not (reason := reason_id(phrase)):
        return
    label = REASONS[reason]
    if header.get("czynnosc_opis") not in (None, label):
        return
    header["czynnosc_powod_id"] = reason
    if header.get("czynnosc_opis") is None:
        header["czynnosc_opis"] = label
    if header.get("czynnosc_dzien") is None:
        header["czynnosc_dzien"] = phrase_day(phrase, reason)
