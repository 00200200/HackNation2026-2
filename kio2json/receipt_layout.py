"""Restore reading order when OCR emits a bank form's label and value columns separately."""

import re
from statistics import median

from rapidfuzz.distance import Levenshtein
from stdnum import iban

from .ocr_normalize import normalize_ocr
from .pdf_text import WordBox

BOOKING_HEADINGS = (
    "potwierdzenie wykonania operacji",
    "potwierdzenie wykonanej operacji",
    "potwierdzenie zaksięgowania transakcji",
)
DETACHED_LABEL = re.compile(
    r"(?im)^(?:kwota|tytułem|numer transakcji|rachunek beneficjenta|data obciążenia|z rachunku)\s*:?$"
)


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


def booking_heading(line: str) -> bool:
    heading = line.strip(" |:/").casefold()
    return any(Levenshtein.distance(heading, template, score_cutoff=2) <= 2 for template in BOOKING_HEADINGS)


def has_detached_labels(pages: list[str]) -> bool:
    if not pages or not re.search(r"(?im)^[ |/.-]*potwierdzenie ", pages[0]):
        return False
    return len(DETACHED_LABEL.findall(pages[0])) >= 3 or bool(
        re.search(r"(?im)\bdane\s+odbiorcy\b", pages[0]) and re.search(r"(?im)\btytu[łl]\s+operacji\b", pages[0])
    )


def _near(word: str, label: str, distance: int = 1) -> bool:
    return Levenshtein.distance(word.strip(" :|").casefold(), label, score_cutoff=distance) <= distance


def _parallel_fields(rows: list[list[WordBox]], height: float) -> list[str]:
    accounts = []
    payment = []
    for i, row in enumerate(rows[:-1]):
        # Party names identify the columns; the accounts must occupy their first data row.
        roles = []
        for word in row:
            for label, field in (("płatnika", "nadawcy"), ("odbiorcy", "odbiorcy")):
                if _near(word.text, label):
                    roles.append((word.x0, field))
        if len(roles) == 2 and roles[0][1] != roles[1][1]:
            divider = next(
                (w.x0 for w in reversed(row) if w.x0 < roles[1][0] and _near(w.text, "dane", 0)), roles[1][0]
            )
            numbers = []
            for right, (_, role) in enumerate(roles):
                cell = "".join(w.text for w in rows[i + 1] if (w.x0 >= divider) == bool(right))
                number = re.sub(r"\s", "", cell.strip("|"))
                if not re.fullmatch(r"[0-9?$]{26}", number):
                    break
                number = validated_account(number.replace("$", "?")) or number
                numbers.append(f"Rachunek {role}: {number}")
            if len(numbers) == 2:
                accounts.extend(numbers)
        # In the detail row the type separates the remittance text from the amount.
        headings = [
            next((w for w in row if _near(w.text, label, n)), None)
            for label, n in (("tytuł", 1), ("szczegóły", 3), ("kwota", 1))
        ]
        if not all(headings):
            continue
        title, kind, amount = headings
        if not title.x0 < kind.x0 < amount.x0:
            continue
        parts = []
        money = None
        previous = title.y1
        for values in rows[i + 1 :]:
            top = min(w.y0 for w in values)
            if top - previous > 3 * height:
                break
            previous = max(w.y1 for w in values)
            cell = " ".join(w.text for w in values if title.x0 - height <= w.x0 < kind.x0 - height)
            if cell:
                parts.append(cell)
            digits = " ".join(w.text for w in values if w.x0 >= amount.x0 - height)
            if money is None and re.fullmatch(r"[−-]?[0-9][0-9 .]*[.,][0-9]{2}(?: PLN)?", digits):
                money = digits
        if parts and money:
            payment.extend(["Tytuł operacji: " + " ".join(parts), "Kwota: " + money])
    return accounts + payment if len(accounts) == len(payment) == 2 else []


def restore_receipt_rows(pages: list[str], boxes: list[WordBox]) -> list[str]:
    words = [b for b in boxes if b.page == 1 and b.text.strip() and b.y1 > b.y0]
    if not words:
        return pages
    # Small OCR differences in the tops of capitals and descenders still belong to one baseline.
    height = median(w.y1 - w.y0 for w in words)
    tolerance = 0.65 * height
    rows = []
    baseline = float("-inf")
    for word in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        center = (word.y0 + word.y1) / 2
        if center - baseline > tolerance:
            rows.append([])
            baseline = center
        rows[-1].append(word)
    rows = [sorted(row, key=lambda w: w.x0) for row in rows]
    text = "\n".join(" ".join(w.text for w in row) for row in rows)
    if fields := _parallel_fields(rows, height):
        text = re.sub(r"(?im)^[ |/.-]*(potwierdzenie transakcji)[ |.]*$", r"\1", text)
        text = re.sub(r"(?i)[ \t]+(?=data księgowania:)", "\n", text)
        heading = re.search(r"(?im)^potwierdzenie [^\n]+", text)
        if heading:
            text = text[: heading.end()] + "\n" + "\n".join(fields) + text[heading.end() :]
    # Reordering must actually place a field opposite its value.
    if not re.search(r"(?im)^kwota\s*:?\s+[−-]?\d", text):
        return pages
    return [normalize_ocr(text), *pages[1:]]
