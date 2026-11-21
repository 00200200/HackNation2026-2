"""Bank-transfer confirmation -> przelew_bankowy."""

import re

from .common import DATE, squash, to_iso

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\d])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?!\d)")
SENDER_RE = re.compile(r"nadawc|zleceniodawc|płatnik|obciąż|z rachunku")
RECIPIENT_RE = re.compile(r"odbiorc|beneficjent|adresat|uznawan|na rachunek")

MONEY = r"(?<![\d.,])(?:\d{1,3}(?:[ .\u00a0]\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?![.,]?\d)"
AMOUNT_LABEL = r"(?:kwota(?: (?:operacji|przelewu))?|wartość)"
DATE_LABEL = r"data (?:operacji|transakcji|realizacji|wykonania|księgowania|zlecenia)"
REFERENCE_LABEL = r"(?:nr ref\.?|numer (?:referencyjny|transakcji)|identyfikator (?:operacji|transakcji))(?: operacji)?"
TITLE_LABEL = r"(?:tytuł(?: przelewu)?|tytułem|opis)"
FIELD_LABEL = rf"(?:{AMOUNT_LABEL}|{DATE_LABEL}|{REFERENCE_LABEL}|{TITLE_LABEL})"
GENERIC_LABEL = r"[^\W\d_][\w /().-]{0,55}:"
# A known undelimited field must match the full label word, never a prefix of a title.
BOUNDARY_RE = re.compile(
    rf"^(?:{GENERIC_LABEL}|{FIELD_LABEL}(?!\w)|(?:status|waluta|typ operacji|kanał|tryb|nadawca|odbiorca|"
    r"zleceniodawca|beneficjent|płatnik|adresat przelewu|dane (?:nadawcy|odbiorcy)|rachunek|"
    r"opłata(?:/prowizja)?(?=\s*[\d.:]|$))\b|[-*]{3,}|bank nie ponosi\b|dokument wygenerowany\b|potwierdzenie ma charakter\b)",
    re.IGNORECASE,
)
AMOUNT_DATE_ROW_RE = re.compile(
    rf"^{AMOUNT_LABEL}[ \t]+{DATE_LABEL}[ \t]*\n[ \t]*(?:PLN\s*)?({MONEY})(?:\s*(?:PLN|zł))?\s+({DATE})",
    re.IGNORECASE | re.MULTILINE,
)
PADDING = r"[\s.:]*"
AMOUNT_RE = re.compile(rf"^{AMOUNT_LABEL}{PADDING}(?:PLN\s*)?({MONEY})", re.IGNORECASE | re.MULTILINE)
OPERATION_DATE_RE = re.compile(rf"^{DATE_LABEL}{PADDING}({DATE})", re.IGNORECASE | re.MULTILINE)
REFERENCE_RE = re.compile(rf"^(?i:{REFERENCE_LABEL}){PADDING}([A-Z]*\d[A-Z0-9/\-]{{5,}})", re.MULTILINE)
TITLE_LABEL_RE = re.compile(rf"^{TITLE_LABEL}\b\s*:?\s*(.*)$", re.IGNORECASE)
# Bank letters attest a dated debit and a completed payment in one sentence.
LETTER_RE = re.compile(
    rf"^Bank potwierdza,? że w dniu ({DATE}) z rachunku\b(?:(?!\n\s*{GENERIC_LABEL}).)*?"
    rf"\bwykonano przelew(?: \w+)? w kwocie ({MONEY})",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)


def _accounts(text: str) -> tuple[str | None, str | None]:
    """Resolve labelled roles or an ordered pair of column headers."""
    found = {}
    for match in ACCOUNT_RE.finditer(text):
        found.setdefault(re.sub(r"\s", "", match[1]), match)
    if not found or len(found) > 2:
        return None, None

    roles = []
    previous_end = 0
    column_order = []
    for match in found.values():
        context = text[previous_end : match.start()].casefold()
        labels = sorted(
            [(m.start(), "sender") for m in SENDER_RE.finditer(context)]
            + [(m.start(), "recipient") for m in RECIPIENT_RE.finditer(context)]
        )
        role = labels[-1][1] if labels else None
        if not roles and labels and "\n" in context[labels[-1][0] :]:
            last_heading = context[: labels[-1][0] + 1].rpartition("\n")[2]
            if SENDER_RE.search(last_heading) or RECIPIENT_RE.search(last_heading):
                column_order = list(dict.fromkeys(label for _, label in labels[-2:]))
        roles.append(role)
        previous_end = match.end()

    if len(roles) == 2:
        if len(column_order) == 2 and roles[1] is None:
            roles = column_order
        elif roles.count(None) == 1 and re.search(r"\b(?:konto|rachunek)\b", text, re.IGNORECASE):
            known = next(role for role in roles if role)
            roles[roles.index(None)] = "recipient" if known == "sender" else "sender"
    if roles.count("sender") > 1 or roles.count("recipient") > 1:
        return None, None
    assigned = dict(zip(roles, found))
    return assigned.get("sender"), assigned.get("recipient")


def _amount(raw: str) -> float:
    digits = re.sub(r"[ \u00a0]", "", raw)
    whole, cents = digits[:-3], digits[-2:]
    return float(re.sub(r"[.,]", "", whole) + "." + cents)


def _title(text: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        label = TITLE_LABEL_RE.match(line.strip())
        if not label:
            continue
        value = label.group(1).strip()
        if BOUNDARY_RE.match(value):
            return None
        parts = [value]
        for following in lines[index + 1 :]:
            if BOUNDARY_RE.match(following.strip()):
                break
            parts.append(following)
        title = squash(" ".join(parts))
        quoted = re.match(r"„(.+?)”", title)
        return quoted.group(1) if quoted else title or None
    return None


def _field_text(text: str) -> str:
    # PDF table columns may share a physical line. An empty title before a new
    # label also has a boundary even when only one space survives extraction.
    text = re.sub(rf"[ \t]{{2,}}(?={GENERIC_LABEL})", "\n", text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        label = TITLE_LABEL_RE.match(line)
        if label:
            value = re.sub(rf"\s+(?=(?:{FIELD_LABEL}|status|waluta|tryb)\s*:)", "\n", label[1], flags=re.IGNORECASE)
            if re.match(GENERIC_LABEL, value):
                value = "\n" + value
            line = line[: label.start(1)] + value
        lines.append(line)
    return "\n".join(lines)


def transaction_values(text: str) -> tuple[float | None, str | None]:
    text = _field_text(text)
    row = AMOUNT_DATE_ROW_RE.search(text)
    if row:
        return _amount(row[1]), to_iso(row[2])
    letter = LETTER_RE.search(text)
    if letter:
        return _amount(letter[2]), to_iso(letter[1])
    amount = AMOUNT_RE.search(text)
    date = OPERATION_DATE_RE.search(text)
    return _amount(amount[1]) if amount else None, to_iso(date[1]) if date else None


def extract(text: str) -> dict:
    sender, recipient = _accounts(text)
    amount, day = transaction_values(text)
    text = _field_text(text)
    reference = REFERENCE_RE.search(text)
    return {
        "przelew_bankowy": {
            "data_operacji": day,
            "kwota": amount,
            "na_rachunek": recipient,
            "numer_transakcji": reference.group(1) if reference else None,
            "tytul": _title(text),
            "z_rachunku": sender,
        }
    }
