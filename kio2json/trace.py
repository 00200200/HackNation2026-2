"""Opt-in extraction trace: class, routing reason and a located source for each field.

The pipeline only records what it already computes. Field sources are located afterwards by
searching the text the extractor read; a value that cannot be found there is reported as such.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from rapidfuzz.distance import Levenshtein

from . import power_of_attorney
from .accounts import normalize_account
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


def note_route(class_id: str, router: str, rule: str | None = None, match: dict | None = None) -> None:
    """Record why a class applied; a configured class also records the cues it found."""
    events = _events.get()
    if events is not None:
        events["routes"][class_id] = {"router": router, "rule": rule} | ({"match": match} if match else {})


def note_warnings(warnings: list[dict]) -> None:
    events = _events.get()
    if events is not None:
        events["warnings"].extend(warnings)


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
    if label is None:
        return trace
    routing = dict(events["routes"].get(label) or {"router": None, "rule": None})
    if routing["router"] == "rules":
        routing["cue"] = heading_cue(label, pages)
    trace["routing"] = routing
    candidates = events["candidates"]
    declared = events.get("declared_fields") or {}
    for path, value in leaves(record):
        patterns = declared_patterns(declared, path)
        trace["fields"].append(field_source(path, value, pages, ocr_pages, candidates, patterns))
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


def after_case_repair(trace: dict | None, record: dict) -> dict | None:
    if not trace or not trace.get("fields"):
        return trace
    fields = []
    for field in trace["fields"]:
        value = lookup(record, field["field"])
        if value != field["value"]:
            field = dict(
                field,
                value=value,
                page=None,
                snippet=None,
                engine="case repair",
                note="confirmed by a sibling document",
            )
        fields.append(field)
    return trace | {"fields": fields}


def declared_patterns(fields: dict, path: str) -> tuple[re.Pattern, ...]:
    """Patterns to locate a labelled scalar within its enclosing object captures."""
    field = None
    patterns = []
    for key, index in PATH_PARTS.findall(path):
        if index:
            return ()  # A repeated list item has its own capture. Locate its printed value instead.
        field = (fields if field is None else field.fields or {}).get(key)
        if field is None:
            return ()
        if field.pattern:
            patterns.append(field.pattern)
    return tuple(patterns) if field and field.pattern else ()


def source_snippet(page: str, value, patterns: tuple[re.Pattern, ...] = ()) -> str | None:
    for pattern in patterns[:-1]:
        capture = pattern.search(page)
        if not capture or capture[1] is None:
            return None
        page = capture[1]
    if patterns:
        match = patterns[-1].search(page)
    elif isinstance(value, (float, int)):
        from .output_schema import NUMBER_TOKEN, money_value

        amount = Decimal(str(value))
        match = next((token for token in NUMBER_TOKEN.finditer(page) if money_value(token) == amount), None)
    else:
        match = value_pattern(value).search(page)
    return snippet(page, match) if match else None


def field_source(
    path: str, value, pages: list[str], ocr_pages: list[int], candidates, patterns: tuple[re.Pattern, ...] = ()
) -> dict:
    """Locate a labelled field by its capture chain, or find a printed form of the value."""
    entry = {"field": path, "value": value, "engine": None, "page": None, "snippet": None}
    if value is None:
        return entry | {"note": "no value extracted"}
    producer = next((engine for engine, candidate in candidates if lookup(candidate, path) == value), None)
    # A label pattern locates only what the labelled engine read; a value from another engine is searched as printed.
    patterns = patterns if producer == "labelled_fields" else ()
    if not patterns and (isinstance(value, bool) or (isinstance(value, int) and abs(value) < 100)):
        entry["note"] = "derived code or flag, not a printed value"
    else:
        for number, page in enumerate(pages, 1):
            source = source_snippet(page, value, patterns)
            if source:
                entry["page"], entry["snippet"] = number, source
                break
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
    if text[:2].isalpha() and normalize_account(text):
        return re.compile(r"(?<!\w)" + r"\s*".join(map(re.escape, text)) + r"(?!\w)", re.IGNORECASE)
    if text.isdigit():
        return re.compile(r"(?<!\d)" + r"[ \-]?".join(text) + r"(?!\d)")
    return re.compile(r"\s+".join(map(re.escape, text.split())), re.IGNORECASE)


def snippet(page: str, match: re.Match) -> str:
    start = page.rfind("\n", 0, match.start()) + 1
    end = page.find("\n", match.end())
    line = page[start : end if end != -1 else len(page)].strip()
    if len(line) <= SNIPPET_CHARS:
        return line
    offset = max(0, match.start() - start - 60)
    return "…" + line[offset : offset + SNIPPET_CHARS] + "…"
