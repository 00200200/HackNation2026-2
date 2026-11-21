"""Bank-transfer confirmation -> przelew_bankowy."""

import re

from .common import DATE, squash, to_iso

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\d])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?!\d)")
SENDER_RE = re.compile(r"nadawc|zleceniodawc|płatnik|obciąż|z rachunku")
RECIPIENT_RE = re.compile(r"odbiorc|beneficjent|adresat|uznawan|na rachunek")

MONEY = r"(?<![\d.,])(?:\d{1,3}(?:[ .\u00a0]\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?![.,]?\d)"
AMOUNT_LABEL = r"\b(?:kwota(?:\s+(?:operacji|przelewu))?|wykonano\s+przelew(?:\s+\w+)?\s+w\s+kwocie|wartość)\b"
DATE_LABEL = (
    r"\b(?:data\s+(?:operacji|transakcji|realizacji|wykonania|księgowania|zlecenia)|potwierdza,?\s+że\s+w\s+dniu)\b"
)
# Tabular statements print both column headings above a single row of values.
AMOUNT_DATE_ROW_RE = re.compile(
    rf"{AMOUNT_LABEL}[ \t]+{DATE_LABEL}[ \t]*\n\s*(?:PLN\s*)?({MONEY})(?:\s*(?:PLN|zł))?\s+({DATE})",
    re.IGNORECASE,
)
FIELD_PADDING = r"[\s.:]*"
AMOUNT_RE = re.compile(rf"{AMOUNT_LABEL}{FIELD_PADDING}(?:PLN\s*)?({MONEY})", re.IGNORECASE)
OPERATION_DATE_RE = re.compile(rf"{DATE_LABEL}{FIELD_PADDING}({DATE})", re.IGNORECASE)
REFERENCE_RE = re.compile(
    r"(?i:nr\s*ref\.?|numer\s+referencyjny|numer\s+transakcji|identyfikator\s+(?:operacji|transakcji))"
    r"(?i:\s+operacji)?[\s.:]*([A-Z]*\d[A-Z0-9/\-]{5,})"
)
TITLE_LABEL_RE = re.compile(r"^(?:Tytuł przelewu|Tytułem|Tytuł|Opis)\b\s*:?\s*(.*)$", re.IGNORECASE)
# A line starting with another field label ends a wrapped title.
NEXT_FIELD_RE = re.compile(
    r"^(?:kwota|wartość|data|numer|nr|identyfikator|status|waluta|typ|kanał|opłata(?=\s*[:.\d]|$)|tryb|nadawca|dane|"
    r"beneficjent|adresat|odbiorca|zleceniodawca|płatnik|rachunek|wydrukowano|bank|potwierdzenie|"
    r"dokument|zrealizowano|-{5,}|\*{3}|[^\W\d_][\w -]{0,40}:)",
    re.IGNORECASE,
)


def _accounts(text: str) -> tuple[str | None, str | None]:
    """(sender, recipient). Each account takes the role of the nearest label before it.
    Sender-first order is the fallback when labels do not establish the roles.
    When only one account has a label, the label counts only if it is on that account's line:
    in a two-column header ("Płatnik Beneficjent") the nearest label is just the right-hand column."""
    found = {}  # account number -> its first match, in reading order
    for match in ACCOUNT_RE.finditer(text):
        found.setdefault(re.sub(r"\s", "", match.group(1)), match)
    numbers, matches = list(found)[:2], list(found.values())[:2]
    if len(numbers) < 2:
        return (numbers[0] if numbers else None), None

    roles, on_own_line = [], []
    previous_end = 0
    for match in matches:
        context = text[previous_end : match.start()].lower()
        sender = max((m.start() for m in SENDER_RE.finditer(context)), default=-1)
        recipient = max((m.start() for m in RECIPIENT_RE.finditer(context)), default=-1)
        roles.append(None if sender == recipient else "sender" if sender > recipient else "recipient")
        on_own_line.append("\n" not in context[max(sender, recipient) :])
        previous_end = match.end()
    same_line = "\n" not in text[matches[0].end() : matches[1].start()]
    both_reversed = roles == ["recipient", "sender"]
    one_reversed = (roles == ["recipient", None] and on_own_line[0]) or (roles == [None, "sender"] and on_own_line[1])
    if both_reversed or (not same_line and one_reversed):
        numbers.reverse()
    return numbers[0], numbers[1]


def _amount(raw: str) -> float:
    digits = re.sub(r"[ \u00a0]", "", raw)
    whole, cents = digits[:-3], digits[-2:]
    return float(re.sub(r"[.,]", "", whole) + "." + cents)


def _title(text: str) -> str | None:
    # Explicit inline labels also delimit fields in flattened PDF tables.
    text = re.sub(
        r"[ \t]+(?=(?:tytuł(?: przelewu)?|numer transakcji|nr ref\.|data \w+|kwota|opłata)\s*:)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        label = TITLE_LABEL_RE.match(line.strip())
        if not label:
            continue
        parts = [label.group(1)]
        for following in lines[index + 1 :]:
            if NEXT_FIELD_RE.match(following.strip()):
                break
            parts.append(following)
        title = squash(" ".join(parts))
        quoted = re.match(r"„(.+?)”", title)
        return quoted.group(1) if quoted else title or None
    return None


def extract(text: str) -> dict:
    sender, recipient = _accounts(text)
    row = AMOUNT_DATE_ROW_RE.search(text)
    amount = row or AMOUNT_RE.search(text)
    date = OPERATION_DATE_RE.search(text)
    raw_date = row.group(2) if row else date.group(1) if date else None
    reference = REFERENCE_RE.search(text)
    return {
        "przelew_bankowy": {
            "data_operacji": to_iso(raw_date) if raw_date else None,
            "kwota": _amount(amount.group(1)) if amount else None,
            "na_rachunek": recipient,
            "numer_transakcji": reference.group(1) if reference else None,
            "tytul": _title(text),
            "z_rachunku": sender,
        }
    }
