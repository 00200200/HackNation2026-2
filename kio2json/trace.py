"""Opt-in extraction trace: class, routing reason and a located source for each field.

The pipeline only records what it already computes. Field sources are located afterwards by
searching the text the extractor read; a value that cannot be found there is reported as such.
"""

import re
from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from rapidfuzz.distance import Levenshtein

from . import power_of_attorney
from .classify import CONFIRMATION_HEADING, DEBIT_DETAILS, EXECUTED
from .receipt_layout import booking_heading

_events: ContextVar[dict | None] = ContextVar("extraction_trace", default=None)
ENGINES = {"python": "rule", "labelled_fields": "rule", "llm": "model"}
MONTHS = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]
SNIPPET_CHARS = 200


@contextmanager
def recording():
    events = {"routes": {}, "candidates": [], "warnings": []}
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


def note(key: str, value) -> None:
    events = _events.get()
    if events is not None:
        events[key] = value


def repaired(trace: dict, record: dict) -> dict:
    """Show a value changed after extraction, such as a case repair, with its new value and a note."""
    fields = []
    for entry, (path, value) in zip(trace["fields"], leaves(record), strict=False):
        if entry["field"] == path and entry["value"] != value:
            note = "corrected from another document in the case folder"
            entry = entry | {"value": value, "note": f"{entry['note']}; {note}" if entry.get("note") else note}
        fields.append(entry)
    return trace | {"fields": fields}


def note_route(class_id: str, router: str, rule: str | None = None, match: dict | None = None) -> None:
    """Record why a class applied; a configured class also records the cues it found."""
    events = _events.get()
    if events is not None:
        events["routes"][class_id] = {"router": router, "rule": rule} | ({"match": match} if match else {})


def note_warnings(warnings: list[dict]) -> None:
    events = _events.get()
    if events is not None:
        events["warnings"].extend(warnings)


def discard_attempt() -> None:
    """Drop what an attempt whose output was discarded recorded, before a retry records its own."""
    events = _events.get()
    if events is not None:
        events["warnings"].clear()
        events["candidates"].clear()


def note_candidate(engine: str, candidate: dict) -> None:
    events = _events.get()
    if events is not None:
        events["candidates"].append((engine, candidate))


def build(label: str | None, record: dict, events: dict) -> dict:
    pages = events.get("pages", [])
    ocr_pages = sorted(events.get("ocr_pages", []))
    trace = {
        "class": label,
        "routing": None,
        "pages": {"read": len(pages), "ocr": ocr_pages} if "pages" in events else None,
        "fields": [],
        "warnings": events["warnings"],
    }
    if "recovery" in events:
        trace["recovery"] = events["recovery"]
    if events.get("optional_ocr_expired"):
        trace["optional_ocr_expired"] = True
    if label is None:
        return trace
    routing = dict(events["routes"].get(label) or {"router": None, "rule": None})
    if routing["router"] == "rules":
        routing["cue"] = heading_cue(label, pages)
    trace["routing"] = routing
    candidates = events["candidates"]
    declared = events.get("declared_fields") or {}
    words = {}
    for box in events.get("boxes", []):
        words.setdefault(box.page, []).append(box)
    for path, value in leaves(record):
        patterns = declared_patterns(declared, path)
        trace["fields"].append(field_source(path, value, pages, ocr_pages, candidates, patterns, words))
    return trace


def heading_cue(label: str, pages: list[str]) -> dict | None:
    """The first line that the rule classifier's heading patterns accept for this class."""
    for number, page in enumerate(pages[:2], 1):
        for line in (row.strip() for row in page.splitlines()):
            heading = re.sub(r"\s", "", line).upper()
            if label == "appeal":
                matched = Levenshtein.distance(heading.strip("*•|.,„”'—–-"), "ODWOŁANIE", score_cutoff=1) <= 1
            elif label == "power_of_attorney":
                matched = heading.startswith("PEŁNOMOCNICTWO")
            else:
                matched = bool(
                    CONFIRMATION_HEADING.match(line)
                    or DEBIT_DETAILS.match(line)
                    or booking_heading(line, ocr=True)
                    or EXECUTED.match(line)
                )
            if matched:
                return {"page": number, "line": line}
    if label == "power_of_attorney" and power_of_attorney.has_notarial_grant("\n".join(pages[:2])):
        return {"page": None, "line": None, "note": "notarial deed grant wording, no heading line"}
    return None


def leaves(value, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, f"{path}[{index}]")
    else:
        yield path, value


PATH_PARTS = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def lookup(record, path: str, missing=None):
    for key, index in PATH_PARTS.findall(path):
        try:
            record = record[int(index)] if index else record[key]
        except (KeyError, IndexError, TypeError):
            return missing
    return record


def assign(record, path: str, value) -> None:
    """Set the value at a trace path such as "osoby[1].nip"."""
    keys = [int(index) if index else key for key, index in PATH_PARTS.findall(path)]
    for key in keys[:-1]:
        record = record[key]
    record[keys[-1]] = value


def declared_patterns(fields: dict, path: str) -> list[re.Pattern]:
    """The label patterns on a field's path, outermost first; none for list rows or a field without its own.

    A list row is located by its value: its pattern finds every row, and the trace cannot tell which one.
    """
    field, patterns = None, []
    for key, index in PATH_PARTS.findall(path):
        field = None if index else (fields if field is None else field.fields or {}).get(key)
        if field is None:
            return []
        if field.pattern is not None:
            patterns.append(field.pattern)
    return patterns if field is not None and field.pattern is not None else []


def locate(pages: list[str], patterns: Sequence[re.Pattern], value) -> tuple[int, tuple[int, int, str]] | None:
    """The first page, span and text of a value: inside its label patterns when given, else as printed."""
    for number, page in enumerate(pages, 1):
        if patterns:
            found = scoped_match(patterns, page)
        else:
            match = value_pattern(value).search(page)
            found = match and (match.start(), match.end(), match[0])
        if found:
            return number, found
    return None


def scoped_match(patterns: Sequence[re.Pattern], page: str) -> tuple[int, int, str] | None:
    """Search each pattern inside the previous one's capture, as the labelled engine reads nested objects.

    Returns the innermost match's span on the page and its captured text.
    """
    offset, text, found = 0, page, None
    for pattern in patterns:
        match = pattern.search(text)
        if match is None or match[1] is None:
            return None
        found = (offset + match.start(), offset + match.end(), match[1])
        offset, text = offset + match.start(1), match[1]
    return found


def field_source(
    path: str,
    value,
    pages: list[str],
    ocr_pages: list[int],
    candidates,
    patterns: Sequence[re.Pattern] = (),
    words: dict[int, list] | None = None,
) -> dict:
    """Locate a value by its field's own label pattern when the class declares one, else by its printed forms.

    `boxes` lists the page words that spell the printed value, in PDF points from the top left.
    """
    entry = {"field": path, "value": value, "engine": None, "page": None, "snippet": None, "boxes": []}
    if value is None:
        return entry | {"note": "no value extracted"}
    producer = next((engine for engine, candidate in candidates if lookup(candidate, path) == value), None)
    # A label pattern locates only what the labelled engine read; a value from another engine is searched as printed.
    patterns = patterns if producer == "labelled_fields" else ()
    derived = isinstance(value, bool) or (isinstance(value, int) and abs(value) < 100)
    if not patterns and derived:
        entry["note"] = "derived code or flag, not a printed value"
    else:
        located = locate(pages, patterns, value)
        if located is None and patterns and not derived:
            # The labelled engine reads the joined pages, so a capture can cross a page break; search the value.
            located = locate(pages, (), value)
        if located:
            number, (start, end, printed) = located
            page = pages[number - 1]
            entry["page"], entry["snippet"] = number, snippet(page, start, end)
            # A whitespace-only capture still shows where the label is.
            spelled = word_span((words or {}).get(number, []), printed.strip() or page[start:end])
            entry["boxes"] = [[round(c, 1) for c in (w.x0, w.y0, w.x1, w.y1)] for w in spelled]
        else:
            entry["note"] = "value not found verbatim in the text read"
    if producer is None:
        entry["note"] = (entry.get("note", "") + "; " if "note" in entry else "") + "producing engine not recorded"
    elif ENGINES.get(producer) == "rule" and ocr_pages:
        if entry["page"] is not None:
            entry["engine"] = "ocr" if entry["page"] in ocr_pages else "rule"
        elif len(ocr_pages) == len(pages):
            entry["engine"] = "ocr"
        else:
            entry["engine"] = "rule or ocr"
    else:
        entry["engine"] = ENGINES.get(producer, producer)
    return entry


def value_pattern(value) -> re.Pattern:
    if isinstance(value, float | int):
        whole, _, fraction = format(abs(Decimal(str(value))), "f").partition(".")
        fraction = fraction.rstrip("0")
        # Thousands may be grouped by a space or a dot ("7 500", "7.500"), and the value must not continue
        # a longer number on either side: 500 is not the end of "7.500,00".
        head = len(whole) % 3 or 3
        digits = r"[ . ]?".join([whole[:head], *(whole[i : i + 3] for i in range(head, len(whole), 3))])
        start = r"(?<!\d)(?<!\d[ ., ])"
        if fraction:
            # The printed value may pad the cents ("15,50" for 15.5); a longer group is another number.
            zeros = "0" * max(0, 2 - len(fraction))
            return re.compile(rf"{start}{digits}[.,]{fraction}(?:{zeros})?(?![.,]?\d)")
        # A whole amount may print ",00", but must not be the integer part of a different amount.
        return re.compile(rf"{start}{digits}(?:[.,]00?)?(?![.,]?\d)")
    text = str(value)
    date = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])-(\d{2})", text)
    if date:
        year, month, day = date.groups()
        day_forms = rf"0?{int(day)}" if day.startswith("0") else day
        return re.compile(
            rf"(?<!\d){day_forms}[ .\-/]{month}[ .\-/]{year}|{year}-{month}-{day}"
            rf"|(?<!\d){day_forms}\s+{MONTHS[int(month) - 1]}\s+{year}",
            re.IGNORECASE,
        )
    if re.fullmatch(r"(?:[A-Za-z]{2})?\d{6,}", text):
        # Identifiers and accounts, with a printed country code kept, may be grouped by spaces or hyphens.
        before = r"(?<!\d)" if text.isdigit() else r"(?<!\w)"
        return re.compile(before + r"[ \-]?".join(map(re.escape, text)) + r"(?!\d)", re.IGNORECASE)
    return re.compile(r"\s+".join(map(re.escape, text.split())), re.IGNORECASE)


def _token(text: str) -> str:
    return re.sub(r"^\W+|\W+$", "", text).casefold()


def word_span(words: list, printed: str) -> list:
    """The consecutive words that spell the printed value, ignoring edge punctuation and spacing.

    A value printed inside a longer word, such as "NIP:5260250995", falls back to that one word.
    """
    target = "".join(_token(part) for part in printed.split())
    if not target:
        return []
    tokens = [_token(word.text) for word in words]
    for start, first in enumerate(tokens):
        if not first or not target.startswith(first):
            continue
        joined = ""
        for end in range(start, len(words)):
            joined += tokens[end]
            if joined == target:
                return words[start : end + 1]
            if not target.startswith(joined):
                break
    return next(([word] for word, token in zip(words, tokens, strict=True) if target in token), [])


def snippet(page: str, begin: int, finish: int) -> str:
    start = page.rfind("\n", 0, begin) + 1
    end = page.find("\n", finish)
    line = page[start : end if end != -1 else len(page)].strip()
    if len(line) <= SNIPPET_CHARS:
        return line
    offset = max(0, begin - start - 60)
    return "…" + line[offset : offset + SNIPPET_CHARS] + "…"
