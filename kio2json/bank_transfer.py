"""Bank-transfer confirmation -> przelew_bankowy."""

import re

from .common import DATE, squash, to_iso

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\d])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?!\d)")
SENDER_RE = re.compile(r"nadawc|zleceniodawc|płatnik|obciąż|z rachunku")
RECIPIENT_RE = re.compile(r"odbiorc|beneficjent|adresat|uznawan|na rachunek")

MONEY_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .\u00a0]\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?![.,]?\d)")
AMOUNT_LABEL_RE = re.compile(r"kwo[tc]|wartość", re.IGNORECASE)
DATE_LABEL_RE = re.compile(
    rf"(?:data\s+(?:operacji|transakcji|realizacji|wykonania|księgowania|zlecenia)|w\s+dniu)(?:(?!{DATE}).)*?({DATE})",
    re.IGNORECASE | re.DOTALL,
)
REFERENCE_RE = re.compile(
    r"(?i:nr\s*ref\.?|numer\s+referencyjny|numer\s+transakcji|identyfikator\s+(?:operacji|transakcji))"
    r"(?i:\s+operacji)?[\s.:]*([A-Z]*\d[A-Z0-9/\-]{5,})"
)
TITLE_LABEL_RE = re.compile(r"^(?:Tytuł przelewu|Tytułem|Tytuł|Opis)\b\s*:?\s*(.*)$", re.IGNORECASE)
# A line starting with another field label ends a wrapped title.
NEXT_FIELD_RE = re.compile(
    r"^(?:kwota|wartość|data|numer|nr|identyfikator|status|waluta|typ|kanał|opłata|tryb|nadawca|dane|"
    r"beneficjent|adresat|odbiorca|zleceniodawca|płatnik|rachunek|wydrukowano|bank|potwierdzenie|"
    r"dokument|zrealizowano|-{5,}|\*{3})",
    re.IGNORECASE,
)


def _accounts(text: str) -> tuple[str | None, str | None]:
    """(sender, recipient). Each account takes the role of the nearest label before it.
    Sender-first order is the fallback, and it also holds for two accounts on one line.
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
    if not same_line and (both_reversed or one_reversed):
        numbers.reverse()
    return numbers[0], numbers[1]


def _amount(text: str) -> float | None:
    label = AMOUNT_LABEL_RE.search(text)
    match = MONEY_RE.search(text, label.end()) if label else None
    if not match:
        return None
    digits = re.sub(r"[ \u00a0]", "", match.group(1))
    whole, cents = digits[:-3], digits[-2:]
    return float(re.sub(r"[.,]", "", whole) + "." + cents)


def _title(text: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        label = TITLE_LABEL_RE.match(line.strip())
        if not label:
            continue
        parts = [label.group(1)]
        for following in lines[index + 1 :]:
            # The value may start on the line after its label; only later lines can end it.
            if any(parts) and NEXT_FIELD_RE.match(following.strip()):
                break
            parts.append(following)
        title = squash(" ".join(parts))
        quoted = re.match(r"„(.+?)”", title)
        return quoted.group(1) if quoted else title or None
    return None


def extract(text: str) -> dict:
    sender, recipient = _accounts(text)
    labelled_date = DATE_LABEL_RE.search(text)
    reference = REFERENCE_RE.search(text)
    return {
        "przelew_bankowy": {
            "data_operacji": to_iso(labelled_date.group(1)) if labelled_date else None,
            "kwota": _amount(text),
            "na_rachunek": recipient,
            "numer_transakcji": reference.group(1) if reference else None,
            "tytul": _title(text),
            "z_rachunku": sender,
        }
    }
