"""Corroborate a damaged printed value against an independent reading in its case."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rapidfuzz.distance import Levenshtein
from stdnum.pl import nip

from .common import PARTY_LABELS, squash

if TYPE_CHECKING:
    from .pdf_text import WordBox

type FieldPath = tuple[str | int, ...]
_REFERENCE_END = r"(?=$|[\s,;)]|\.(?=$|\s))"
_REFERENCE = re.compile(
    r"\b(?:przetargu|(?:znak|nr|numer)\s+(?:sprawy|postępowania|zamówienia)|postępowani[ua](?:\s+nr)?)"
    r"(?:\s*[:.]\s*|\s+)([\w|�]+(?:[./‐‑‒–—-][\w|�]+)+)" + _REFERENCE_END,
    re.IGNORECASE,
)
_ROLE_HEADINGS = {**PARTY_LABELS, "sender": r"nadawca|zleceniodawca", "recipient": r"odbiorca"}
_ROLE = re.compile(
    r"\b(?:" + "|".join(f"(?P<{key}>{pattern})" for key, pattern in _ROLE_HEADINGS.items()) + r")[ \t]*(?::|$)",
    re.IGNORECASE | re.MULTILINE,
)
_TITLE_PARTY = re.compile(r"\b(?:odwołujący|nadawca|zleceniodawca)\s*:\s*([^;\n]+?)(?=;|$)", re.IGNORECASE)
_SENDER = re.compile(r"^(?:nadawca|zleceniodawca|nazwa nadawcy)\s*:[ \t]*([^\n;]+)$", re.IGNORECASE | re.MULTILINE)
# Limit low-confidence substitutions to common glyph confusions. Case/inflection alone is never damage.
_LOOKALIKE = ("0Oo", "1Ilłi", "5Ss", "8B", "2Zz", "6G", "ŁL", "łl")


def case_repair_enabled() -> bool:
    return os.getenv("KIO_CASE_REPAIR", "0") == "1"


@dataclass(frozen=True)
class Reading:
    kind: str
    path: FieldPath
    value: str
    scanned: bool
    trusted: bool
    weak_words: frozenset[str]
    # Identity evidence for the party owning this field.
    anchors: tuple[tuple[str, str], ...]
    span: tuple[int, int] | None = None


def procedure_references(title: str) -> Iterator[re.Match]:
    return (
        match
        for match in _REFERENCE.finditer(title)
        if any(c.isdigit() for c in match[1]) and not re.match(r"KIO[./‐‑‒–—-]", match[1], re.IGNORECASE)
    )


def _fields(label, data, pages):
    if label == "appeal":
        for i, party in enumerate(data.get("Odwolujacy") or []):
            path = ("Odwolujacy", i)
            for key in ("nazwa", "nip", "krs"):
                yield key, (*path, key), party.get(key), party, None
            person = (party.get("pelnomocnik") or {}).get("imie_nazwisko")
            yield "attorney", (*path, "pelnomocnik", "imie_nazwisko"), person, {}, None
        key = "numer_postepowania"
        yield "procedure", ("ZamowieniePubliczne", key), (data.get("ZamowieniePubliczne") or {}).get(key), {}, None
    elif label == "power_of_attorney":
        for i, entry in enumerate(data.get("mocodawca") or []):
            party = entry.get("data") or {}
            key = "nazwa" if party.get("nazwa") else "imie_nazwisko"
            for kind, field in (("nazwa", key), ("nip", "nip"), ("krs", "krs")):
                yield kind, ("mocodawca", i, "data", field), party.get(field), party, None
        for i, person in enumerate(data.get("pelnomocnicy") or []):
            yield "attorney", ("pelnomocnicy", i, "imie_nazwisko"), person.get("imie_nazwisko"), {}, None
    elif label == "bank_transfer":
        title = (data.get("przelew_bankowy") or {}).get("tytul") or ""
        for kind, matches in (("procedure", procedure_references(title)), ("nazwa", _TITLE_PARTY.finditer(title))):
            for match in matches:
                yield kind, ("przelew_bankowy", "tytul"), match[1], {}, match.span(1)
        for page in pages:
            for match in _SENDER.finditer(page):
                yield "nazwa", (), match[1].strip(), {}, None  # Sender has no organizer output field.


def _valid(kind, value):
    if kind == "nip":
        return bool(re.fullmatch(r"[0-9]{10}", value)) and nip.is_valid(value)
    if kind == "krs":
        return bool(re.fullmatch(r"[0-9]{10}", value))
    if kind == "procedure":
        return bool(re.fullmatch(r"(?=.*\d)[A-Za-z0-9]+(?:[./‐‑‒–—-][A-Za-z0-9]+)+", value))
    if kind == "attorney":
        return len(value.split()) >= 2 and all(c.isalpha() or c in " -’'" for c in value)
    return any(c.isalpha() for c in value) and not re.search(r"[|�]|[^\W\d_]\d[^\W\d_]", value)


def _printed_pattern(kind: str, value: str) -> re.Pattern:
    literal = re.escape(value)
    if kind == "nip" and value.isascii() and value.isdigit():
        literal = r"(?:PL\s*)?" + r"[ -]?".join(value)
    before, after = r"(?<!\w)", r"(?!\w)"
    if kind == "procedure":
        before, after = r"(?<![^\s(:,;])", _REFERENCE_END
    elif kind in ("nip", "krs"):
        before += r"(?<!\d[ -])"
        after += r"(?![ -]\d)"
    return re.compile(before + literal + after)


def _adjacent_owner(kind, pattern, anchor_kind, anchor_value, pages):
    """Bind an identity to the same printed group, without crossing another party or address."""
    anchor = _printed_pattern(anchor_kind, anchor_value).pattern
    gap = r"[\s,;:()]*"

    # A name precedes its registration details. Registry labels can occur in either order.
    def pair(left, right_kind, right):
        label = rf"(?:(?i:{right_kind})(?:\s+(?i:nr))?{gap})?" if right_kind in ("nip", "krs") else ""
        return left + gap + label + right

    patterns = []
    if anchor_kind != "nazwa":
        patterns.append(pair(pattern.pattern, anchor_kind, anchor))
    if kind != "nazwa":
        patterns.append(pair(anchor, kind, pattern.pattern))
    adjacent = re.compile("|".join(patterns))
    return any(adjacent.search(page) for page in pages)


def _sections(page: str):
    headings = list(_ROLE.finditer(page))
    if not headings:
        yield None, squash(page)
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(page)
        yield heading.lastgroup, squash(page[heading.end() : end])


def printed_readings(label: str, record: dict, pages: list[str], scanned: Sequence[int], boxes: list[WordBox]):
    """Retain field-sized evidence from the selected original page reading."""
    flat = [squash(page) for page in pages]
    sections = [(i, role, text) for i, page in enumerate(pages, 1) for role, text in _sections(page)]
    readings = []
    for kind, path, value, party, span in _fields(label, record, pages):
        if not isinstance(value, str) or len(value) < 5:
            continue
        pattern = _printed_pattern(kind, value)
        if label == "bank_transfer" and not path:
            matched = [
                (i, value)
                for i, page in enumerate(pages, 1)
                if any(m[1].strip() == value for m in _SENDER.finditer(page))
            ]
        elif span is not None:
            title = squash(record["przelew_bankowy"]["tytul"])
            matched = [(i, text) for i, text in enumerate(flat, 1) if title in text and pattern.search(text)]
        elif kind == "procedure":
            matched = [(i, text) for i, text in enumerate(flat, 1) if pattern.search(text)]
        else:
            roles = (
                ("appointee", "counsel", "representation")
                if kind == "attorney"
                else (("principal",) if label == "power_of_attorney" else ("appellant",))
            )
            matched = [
                (i, text) for i, role, text in sections if (role is None or role in roles) and pattern.search(text)
            ]
        hits = {i for i, _ in matched}
        if not hits:
            continue
        scan_only = hits.issubset(scanned)
        words = value.split()
        weak = set()
        confident = True
        if scan_only:
            for word in words:
                scores = [
                    getattr(b, "confidence", None) for b in boxes if b.page in hits and b.text.strip(",:;()") == word
                ]
                if not scores or any(s is None for s in scores):
                    confident = False
                    continue
                if max(scores) < 55:
                    weak.add(word)
                confident &= min(scores) >= 80
        trusted = _valid(kind, value) and (not scan_only or confident or kind == "nip")
        anchors = tuple(
            (k, v)
            for k in ("nazwa", "nip", "krs")
            if k != kind
            and isinstance(v := party.get(k), str)
            and v
            and _adjacent_owner(kind, pattern, k, v, (text for _, text in matched))
        )
        readings.append(Reading(kind, path, value, scan_only, trusted, frozenset(weak), anchors, span))
    return tuple(readings)


def _compatible(target: Reading, source: Reading) -> bool:
    # For near-identical registry numbers, independently confirm who owns them.
    left, right = dict(target.anchors), dict(source.anchors)
    same = [left[k].casefold() == right[k].casefold() for k in left.keys() & right.keys()]
    return all(same) and (target.kind not in ("nip", "krs") or bool(same))


def _damaged(target: Reading, candidate: str) -> bool:
    old = target.value
    if len(candidate) != len(old) or Levenshtein.distance(old, candidate, score_cutoff=1) != 1:
        return False
    if target.kind == "nip":
        return not nip.is_valid(old)
    if not target.scanned:
        return False
    at = next(i for i, (a, b) in enumerate(zip(old, candidate, strict=True)) if a != b)
    a, b = old[at], candidate[at]
    if a in "|�":
        return b.isalnum()
    if a.casefold() == b.casefold() or a.isspace():
        return False
    word = next(m[0] for m in re.finditer(r"\S+", old) if m.start() <= at < m.end())
    confusable = any(a in group and b in group for group in _LOOKALIKE)
    if target.kind in ("nazwa", "attorney") and a.isdigit() and confusable:
        return word in target.weak_words and 0 < at < len(old) - 1 and old[at - 1].isalpha() and old[at + 1].isalpha()
    return word in target.weak_words and (confusable or (target.kind == "krs" and a.isdigit() and b.isdigit()))


def repairs(readings: tuple[Reading, ...], siblings: list[Reading]) -> Iterator[tuple[Reading, str]]:
    for target in readings:
        if not target.path or target.trusted:
            continue
        candidates = {
            other.value
            for other in siblings
            if other.kind == target.kind
            and other.trusted
            and _compatible(target, other)
            and (other.value == target.value or _damaged(target, other.value))
        }
        if len(candidates) == 1 and target.value not in candidates:
            yield target, candidates.pop()
