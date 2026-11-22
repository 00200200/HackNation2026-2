"""Morphological agreement in short Polish appeal party captions."""

import re
from functools import lru_cache

from .personal_names import _analyser

CARD_HEAD = r"(?:dane(?: identyfikacyjne| teleadresowe)?|(?:pełna )?nazwa(?: i (?:adres|siedziba))?|oznaczenie)"
_IDENTITY = re.compile(rf"^{CARD_HEAD} ")
_APPELLANT = {"wykonawca", "podmiot", "strona", "przedsiębiorca"}
_BUYER = {
    "gmina",
    "powiat",
    "miasto",
    "województwo",
    "urząd",
    "jednostka",
    "instytucja",
    "podmiot",
    "szpital",
    "zamawiający",
    "związek",
    "uczelnia",
    "zamawiająca",
}
# A parenthetical after a collective qualifies the caption. It cannot identify an individual member.
_GROUP_AGENT = re.compile(r"(?:pełnomocnik|reprezentant|przedstawiciel|lider) (?:wspólnych )?zamawiających")
_JOINT = re.compile(r"(?:wspólni zamawiający|zamawiający wspólnie|zamawiający wspólni|zamawiający)")
_CANDIDATE = re.compile(r"odwołuj|skarżą|wnoszą|składają|jako zamawiają|zamawiając.*\(", re.IGNORECASE)


@lru_cache(maxsize=256)
def _forms(word, case):
    """Lemmas, number and gender for complete nominal or attributive readings."""
    forms = set()
    for _, _, (surface, lemma, tag, _, _) in _analyser().analyse(word):
        slots = tag.split(":")
        if (
            surface != word
            or slots[0] not in {"subst", "pact", "adj"}
            or "neg" in slots
            or case not in slots[2].split(".")
        ):
            continue
        for number in slots[1].split("."):
            for gender in slots[3].split("."):
                forms.add((lemma.partition(":")[0], number, gender))
    return forms


def _features(word, lemmas, case):
    return {(n, g) for lemma, n, g in _forms(word, case) if lemma in lemmas}


def descriptive_role(line: str) -> str | None:
    caption = line.partition(":")[0].strip().casefold()
    if caption == "odwołujący" or len(caption) > 100 or not _CANDIDATE.search(caption):
        return None
    structure = re.fullmatch(r"([\w -]+?)(?:\s*\(([\w -]+)\))?", caption)
    if not structure:
        return None
    phrase, qualifier = structure.groups()
    case = "gen" if _IDENTITY.match(phrase) else "nom"
    words = _IDENTITY.sub("", phrase).split()
    if qualifier and _GROUP_AGENT.fullmatch(qualifier) and _JOINT.fullmatch(" ".join(words)):
        return "Zamawiający"
    if len(words) == 3 and words[1] == "jako" and not qualifier:
        if _features(words[0], _BUYER, case) and _features(words[2], {"zamawiać"}, case):
            return "Zamawiający"
        return None
    if qualifier and not _features(qualifier, _APPELLANT, "nom"):
        return None
    # An appeal can be expressed by a participle with a reflexive particle or a direct object.
    for index, word in enumerate(words):
        role = _features(word, {"skarżyć", "skarżący", "skarżąca", "odwoływać"}, case)
        end = index + 1
        if role and words[end : end + 1] == ["się"] and _features(word, {"odwoływać"}, case):
            end += 1
        elif words[end : end + 1] == ["odwołanie"]:
            role = _features(word, {"wnosić", "składać"}, case)
            end += 1
        if not role:
            continue
        head = words[:index] + words[end:]
        if not head or (len(head) == 1 and role & _features(head[0], _APPELLANT, case)):
            return "Odwołujący"
    return None
