"""Ground names of grant recipients in the visible printed text."""

import re
from typing import NamedTuple

SPACE = r"[^\S\r\n\t]"
WORD = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*(?![\w’'\-])")
PARTICLES = {"de", "del", "la", "van", "von", "den", "der"}
LABELS = {"PESEL", "NIP", "REGON", "KRS", "Mecenas", "Pani", "Pan", "Pana", "Radca", "Adwokat", "Firma"}
RECEIVES = rf"otrzymuje{SPACE}+(?:umocowanie|pełnomocnictwo)\b"
RECIPIENT = re.compile(
    rf"^{SPACE}*(?:(?:osoba{SPACE}+umocowana|pełnomocni(?:k|cy)){SPACE}*:"
    rf"|upoważnienie{SPACE}+otrzymuje\b|(?:(?:pierwszym|drugim|kolejnym){SPACE}+)?pełnomocnikiem{SPACE}+jest\b"
    rf"|(?P<subject>(?=[^\r\n]*\b{RECEIVES})(?:(?:wymienion[ay]|wskazan[ay]){SPACE}+w{SPACE}+dokumencie{SPACE}+)?"
    rf"(?:(?:adwokat|radca{SPACE}+prawny){SPACE}+)?))"
    rf"{SPACE}*(?:(?:pani|pan|adw\.|r\.{SPACE}*pr\.){SPACE}+)?",
    re.IGNORECASE | re.MULTILINE,
)
NON_OPERATIVE = re.compile(
    r"\b(?:przykład\w*|wzór|wzor(?:u|ze)|projekt pełnomocnictwa|jeśli|jeżeli|pod warunkiem|"
    r"warunkowo|historyczn\w*|poprzedni\w* pełnomocnictw\w*|odwołan[eya]\b|cofnięt[eya]\b|"
    r"nie jest (?:udzielon\w* )?pełnomocnictw\w*|nie (?:stanowi|udziel\w*|upoważni\w*|ustanawi\w*)|odwołuj\w* pełnomocnictw\w*)\b",
    re.IGNORECASE,
)
COMPANY = re.compile(r"(?i)^[ ,]*(?:sp\.|spółk\w*|s\.\s*a\.)")
WRONG_ROLE = re.compile(r"(?i)\b(?:mocodawca|podpisujący|zamawiający|świadek)\s*:[^:]*$")
END = re.compile(r"(?:[, ]*PESEL[ :]+(?P<pesel>\d{11}))?[ .]*$", re.IGNORECASE)


class Appointment(NamedTuple):
    name: str
    start: int
    end: int
    pesel: str | None


def _name_word(word: str) -> bool:
    return bool(WORD.fullmatch(word)) and len(word) > 1 and word[0].isupper() and word not in LABELS


def _appointments(full: str, visible: int):
    """Yield each explicit role line, including unresolved, multiple and partly displayed appointments."""
    if NON_OPERATIVE.search(full[:visible]):
        yield None
        return
    for role in RECIPIENT.finditer(full):
        if role.start() >= visible:
            break
        end = start = role.end()
        line_end = full.find("\n", start)
        line_end = len(full) if line_end == -1 else line_end
        parts = []
        for word in WORD.finditer(full, start, line_end):
            if not re.fullmatch(SPACE + "*", full[end : word.start()]) or not (
                _name_word(word[0]) or word[0] in PARTICLES
            ):
                break
            parts.append(word[0])
            end = word.end()
        rest = full[end:line_end].strip("\r")
        if role["subject"] is not None:
            # In subject-first prose the name must itself receive authority.
            predicate = re.match(SPACE + "+" + RECEIVES, rest, re.IGNORECASE)
            if predicate is None:
                continue
            rest = rest[predicate.end() :]
        final = END.fullmatch(rest)
        if len(parts) < 2 or parts[0] in PARTICLES or parts[-1] in PARTICLES or COMPANY.match(rest) or end > visible:
            yield None
            continue
        # A conjunction or additional columns can introduce a second recipient.
        if final is None or line_end > visible:
            yield None
            continue
        yield Appointment(" ".join(parts), start, end, final["pesel"])


def _read_appointments(readings):
    return [(full, shown, list(_appointments(full, len(shown)))) for full, shown in readings]


def printed_attorney_name(proposal: str, readings) -> str | None:
    return _name_from_readings(proposal, _read_appointments(readings))


def _name_from_readings(proposal: str | None, readings) -> str | None:
    words = (proposal or "").split()
    if not words or not (_name_word(words[0]) and _name_word(words[-1])):
        return None
    if not all(_name_word(w) or w in PARTICLES for w in words):
        return None
    copied = re.compile(r"(?<![\w’'\-])" + (SPACE + "+").join(map(re.escape, words)) + r"(?![\w’'\-])")
    names = set()
    for full, shown, appointments in readings:
        for hit in copied.finditer(full):
            if hit.end() > len(shown):
                break
            appointment = next((a for a in appointments if a and a.start <= hit.start() and hit.end() <= a.end), None)
            if appointment:
                names.add(appointment.name)
                continue
            if len(words) < 2:
                return None
            # Keep already complete, printed names from free prose. Never join adjacent lines or table cells.
            before = full[full.rfind("\n", 0, hit.start()) + 1 : hit.start()]
            after = full[hit.end() :].split("\n", 1)[0]
            previous = re.search(r"([^\s]+)" + SPACE + r"+$", before)
            following = re.match(SPACE + r"+([^\s,.;]+)", after)
            if (
                WRONG_ROLE.search(before)
                or COMPANY.match(after)
                or (previous and (_name_word(previous[1]) or previous[1] in PARTICLES))
                or (following and (_name_word(following[1]) or following[1] in PARTICLES))
            ):
                return None
            names.add(" ".join(hit[0].split()))
    return names.pop() if len(names) == 1 else None


def ground_recipients(raw_rows, identifiers, readings):
    """A single unambiguous appointment may supply a missing row or repair one existing row."""
    parsed = _read_appointments(readings)
    candidates = {(a.name, a.pesel) if a else None for _, _, appointments in parsed for a in appointments}
    names = {record[0] for record in candidates if record}
    sole = next(iter(candidates)) if len(candidates) == 1 else None
    if not raw_rows:
        return [{"imie_nazwisko": sole[0], "pesel": None}] if sole else []

    rows = []
    seen = set()
    for raw, identifier in zip(raw_rows, identifiers, strict=True):
        name = _name_from_readings(raw["imie_nazwisko"], parsed)
        if names and name not in names:
            name = None
        if not name and sole and len(raw_rows) == 1:
            name = sole[0]
        if candidates and raw["pesel"] is not None and (not identifier or (name, identifier) not in candidates):
            name = None
        record = (name, identifier)
        # Only collapse equivalent rows backed by a single appointment in each reading.
        if (
            record in seen
            and name
            and all(sum(a is not None and a.name == name for a in group) <= 1 for _, _, group in parsed)
        ):
            continue
        rows.append({"imie_nazwisko": name, "pesel": identifier})
        if name in names and None not in candidates and sum(c[0] == name for c in candidates) == 1:
            seen.add(record)
    return rows
