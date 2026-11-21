"""Bind receipt labels to printed values in the same row or table column."""

import re
from collections import defaultdict
from functools import lru_cache
from itertools import product
from statistics import median

from rapidfuzz.distance import Levenshtein
from stdnum import iban

from .common import DATE_RE
from .ocr_normalize import normalize_ocr
from .pdf_text import WordBox


def validated_account(number: str) -> str | None:
    if iban.is_valid("PL" + number):
        return number
    unknown = [i for i, char in enumerate(number) if char == "?"]
    if len(unknown) > 1:
        return None
    valid = []
    for i in unknown or range(len(number)):
        for digit in "0123456789":
            candidate = number[:i] + digit + number[i + 1 :]
            if iban.is_valid("PL" + candidate):
                valid.append(candidate)
                if len(valid) > 1:
                    return None
    return valid[0] if valid else None


# Canonical labels retain the date and reference semantics for the downstream extractor.
# Empty outputs mark neighbouring columns whose text must stay out of another field.
LABELS = {
    "Kwota": ("kwota", "wartość", "kwota transakcji", "kwota operacji", "kwota przelewu", "kwota zaksięgowana"),
    "Tytuł": ("tytuł", "tytułem", "opis", "tytuł operacji", "tytuł przelewu", "opis operacji"),
    "Rachunek nadawcy": (
        "rachunek nadawcy",
        "rachunek zleceniodawcy",
        "rachunek obciążany",
        "z rachunku",
        "dane nadawcy",
        "dane zleceniodawcy",
        "dane płatnika",
        "nadawca",
        "zleceniodawca",
        "płatnik",
    ),
    "Rachunek odbiorcy": (
        "rachunek odbiorcy",
        "rachunek beneficjenta",
        "rachunek uznawany",
        "na rachunek",
        "dane odbiorcy",
        "dane beneficjenta",
        "odbiorca",
        "beneficjent",
        "adresat przelewu",
    ),
    "Numer transakcji": (
        "numer transakcji",
        "nr transakcji",
        "identyfikator transakcji",
        "identyfikator operacji",
        "numer referencyjny",
        "nr ref",
        "referencje banku",
        "referencja banku",
    ),
    "Dzienny numer transakcji": ("dzienny numer transakcji",),
    "Data operacji": ("data operacji", "data transakcji"),
    "Data księgowania": ("data księgowania",),
    "Data obciążenia": ("data obciążenia",),
    "Data realizacji": ("data realizacji", "data wykonania"),
    "": (
        "data waluty",
        "data wydruku",
        "data stempla",
        "data wystawienia",
        "waluta",
        "szczegóły operacji",
        "szczegóły",
        "typ",
        "rodzaj",
        "status",
        "opłata",
        "prowizja",
        "saldo",
        "adres banku",
    ),
}
PHRASES = {tuple(phrase.split()): field for field, phrases in LABELS.items() for phrase in phrases}
MAX_LABEL = max(map(len, PHRASES))
BOOKING_ACTIONS = {"wykonania", "wykonanej", "wykonanego", "zaksięgowania", "realizacji", "zrealizowanej"}
DOCUMENT_WORDS = {"potwierdzenie", "dowód", "operacji", "przelewu", "transakcji"} | BOOKING_ACTIONS
VOCABULARY = {word for phrase in PHRASES for word in phrase} | DOCUMENT_WORDS
MONEY_CELL = re.compile(
    r"(?:(?:[A-Z]{3}|zł)\s*)?[−–-]?\s*(?:\d{1,3}(?:[ .]\d{3})+|\d+)[.,]\d{2}(?:\s*(?:[A-Z]{3}|zł))?"
)


@lru_cache(maxsize=2048)
def _label_words(token: str, ocr: bool) -> tuple[str, ...]:
    word = token.strip("|:/.,").casefold()
    if not ocr or word in VOCABULARY or len(word) < 4 or not word.isalpha():
        return (word,)
    # Resolve equally close spellings only when the complete phrase gives one field.
    cutoff = 1 if len(word) < 9 else 2
    scores = [(Levenshtein.distance(word, label, score_cutoff=cutoff), label) for label in VOCABULARY]
    best = min(distance for distance, _ in scores)
    return tuple(label for distance, label in scores if distance == best) if best <= cutoff else (word,)


def booking_heading(line: str, *, ocr: bool = False) -> bool:
    tokens = line.strip(" |:/.-").split()
    if len(tokens) != 3:
        return False
    words = [set(_label_words(w, ocr)) for w in tokens]
    return (
        bool(words[0] & {"potwierdzenie", "dowód"})
        and bool(words[1] & BOOKING_ACTIONS)
        and bool(words[2] & {"operacji", "transakcji", "przelewu"})
    )


def _headers(tokens: list[str], ocr: bool) -> list[tuple[int, int, str]]:
    words = tuple(_label_words(w, ocr) for w in tokens)
    headers = []
    start = 0
    while start < len(words):
        for stop in range(min(start + MAX_LABEL, len(words)), start, -1):
            fields = {PHRASES[p] for p in product(*words[start:stop]) if p in PHRASES}
            if len(fields) == 1:
                headers.append((start, stop, fields.pop()))
                start = stop
                break
        else:
            start += 1
    return headers


def has_detached_labels(pages: list[str], *, ocr: bool = False) -> bool:
    if not pages:
        return False
    first = pages[0]
    if not (
        DATE_RE.search(first) or MONEY_CELL.search(first) or re.search(r"(?<!\d)\d{2}(?:[ ]?\d{4}){6}(?!\d)", first)
    ):
        return False
    detached = set()
    for line in first.splitlines():
        tokens = line.strip(" |").split()
        headers = _headers(tokens, ocr)
        if not headers or headers[0][0] != 0:
            continue
        fields = {field for _, _, field in headers if field}
        if len(headers) > 1 and fields:
            return True
        if headers[-1][1] == len(tokens):
            detached.update(fields)
    return len(detached) >= 2


def _word_rows(boxes: list[WordBox]) -> tuple[list[list[WordBox]], float]:
    words = []
    for box in boxes:
        if box.page != 1 or box.y1 <= box.y0:
            continue
        # The native reader returns individual words. Some OCR backends also return multiword spans.
        for match in re.finditer(r"\S+", box.text):
            width = (box.x1 - box.x0) / len(box.text)
            words.append(
                box._replace(text=match[0], x0=box.x0 + width * match.start(), x1=box.x0 + width * match.end())
            )
    if not words:
        return [], 0
    height = median(w.y1 - w.y0 for w in words)
    rows = []
    baseline = float("-inf")
    for word in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        center = (word.y0 + word.y1) / 2
        if center - baseline > 0.65 * height:
            rows.append([])
            baseline = center
        rows[-1].append(word)
    return [sorted(row, key=lambda w: w.x0) for row in rows], height


def _cell_value(field: str, cell: str, ocr: bool) -> str | None:
    cell = cell.strip(" |:")
    if field.startswith("Rachunek"):
        compact = re.sub(r"\s+", "", cell.removeprefix("IBAN").lstrip(": ")).removeprefix("PL")
        if re.fullmatch(r"(?=.*[*Xx])[0-9*Xx]{4,34}", compact):
            return cell
        if ocr:
            compact = normalize_ocr(compact)
            if len(compact) == 26 and sum(c.isdigit() for c in compact) == 25:
                compact = re.sub(r"[^0-9]", "?", compact)
            return validated_account(compact) if re.fullmatch(r"[0-9?]{26}", compact) else None
        return compact if re.fullmatch(r"[0-9]{26}", compact) else None
    if field.startswith("Data"):
        day = DATE_RE.match(cell)
        if day and re.fullmatch(r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?", cell[day.end() :]):
            return day[0]
        return None
    if field == "Kwota":
        return cell if MONEY_CELL.fullmatch(cell) else None
    if field == "Tytuł":
        return cell or None
    if field == "Dzienny numer transakcji":
        return cell if cell.isdigit() else None
    if field == "Numer transakcji" and re.fullmatch(r"(?=.*\d)[\w/-]+", cell):
        return cell
    return None


def _row_headers(row: list[WordBox], following: list[WordBox], height: float, ocr: bool) -> list[tuple[int, int, str]]:
    headers = [
        (start, stop, field)
        for start, stop, field in _headers([w.text for w in row], ocr)
        if start == 0 or row[start].x0 - row[start - 1].x1 > height * 0.75
    ]
    # On a header row, a visually separate phrase with its own data column is a cell
    # boundary even when the bank uses a heading outside our extraction vocabulary.
    if not headers or any(any(c.isdigit() for c in w.text) for w in row):
        return headers
    next_labels = _headers([w.text for w in following], ocr)
    if next_labels and next_labels[0][0] == 0:
        return headers
    label_tokens = {i for start, stop, _ in headers for i in range(start, stop)}
    for i, word in enumerate(row):
        if i in label_tokens or (i and word.x0 - row[i - 1].x1 <= 2 * height):
            continue
        if any(abs(value.x0 - word.x0) <= height for value in following):
            headers.append((i, i + 1, ""))
    return sorted(headers)


def receipt_cell_fields(boxes: list[WordBox], *, ocr: bool = False) -> dict[str, str]:
    rows, height = _word_rows(boxes)
    labels = [_row_headers(row, following, height, ocr) for row, following in zip(rows, rows[1:] + [[]])]
    evidence = defaultdict(set)
    for index, (row, headers) in enumerate(zip(rows, labels)):
        if not headers or headers[0][0] != 0:
            continue
        # Stop at the next heading or visual break. All columns share a block boundary,
        # while each field can bind independently within that block.
        below = []
        bottom = max(w.y1 for w in row)
        for j in range(index + 1, len(rows)):
            following = rows[j]
            if (labels[j] and labels[j][0][0] == 0) or min(w.y0 for w in following) - bottom > 3 * height:
                break
            below.append(following)
            bottom = max(w.y1 for w in following)
        columns = {}
        repeated_row = False
        for n, (start, stop, field) in enumerate(headers):
            if not field:
                continue
            end = headers[n + 1][0] if n + 1 < len(headers) else len(row)
            left = row[start].x0 - height
            right = row[end].x0 - height if end < len(row) else float("inf")
            cells = [" ".join(w.text for w in row[stop:end])]
            cells.extend(" ".join(w.text for w in values if left <= w.x0 < right) for values in below)
            values = [value for cell in cells if (value := _cell_value(field, cell, ocr))]
            if field == "Tytuł" and values:
                columns[field] = " ".join(values)
            elif len(values) > 1 and (field == "Kwota" or field.startswith("Data")):
                repeated_row = True
            elif len(set(values)) == 1:
                columns[field] = values[0]
        # Multiple debit rows cannot contribute a single transaction's date, amount or title.
        if not repeated_row:
            for field, value in columns.items():
                evidence[field].add(value)
    return {field: values.pop() for field, values in evidence.items() if len(values) == 1}


def append_receipt_fields(pages: list[str], fields: dict[str, str]) -> list[str]:
    if not pages:
        return pages
    source_lines = {line.strip() for line in pages[0].splitlines()}
    lines = [f"{field}: {value}" for field, value in fields.items()]
    if not lines or all(line in source_lines for line in lines):
        return pages
    # Keep every original heading, role, status and exclusion for the router. The separator
    # terminates even a final multi-line title before the original transcript begins.
    return ["\n".join([*lines, "---", pages[0]]), *pages[1:]]


def restore_receipt_rows(pages: list[str], boxes: list[WordBox], *, ocr: bool = False) -> list[str]:
    return append_receipt_fields(pages, receipt_cell_fields(boxes, ocr=ocr))
