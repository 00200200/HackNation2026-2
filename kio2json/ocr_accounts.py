"""OCR account fields and evidence shared by routing and extraction."""

import re
from dataclasses import dataclass

from stdnum import iban

from .bank_transfer import BOUNDARY_RE, printed_accounts
from .common import to_iso
from .receipt_layout import validated_account

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\w/|*])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?![\w/|*])")
ACCOUNT_NOUN = r"(?:(?:numer|nr\.?) (?:rachunku|konta)|rachunek|konto)"
SENDER = r"(?:nadawc[ay]|zleceniodawc[ay]|płatnik(?:a)?)"
RECIPIENT = r"(?:odbiorc[ay]|beneficjent(?:a)?|adresat(?:a)?(?: przelewu)?)"
SENDER_FIELD = rf"(?:{ACCOUNT_NOUN} (?:{SENDER}|obciąż(?:an|on)[ye])|z rachunku)"
RECIPIENT_FIELD = rf"(?:{ACCOUNT_NOUN} (?:{RECIPIENT}|uznawan[ye])|na rachunek)"
ACCOUNT_LABEL = re.compile(
    rf"(?:(?P<sender>{SENDER_FIELD}|(?:dane )?{SENDER})|"
    rf"(?P<recipient>{RECIPIENT_FIELD}|(?:dane )?{RECIPIENT})|(?P<generic>{ACCOUNT_NOUN}))\b",
    re.IGNORECASE,
)
ACCOUNT_FIELD = re.compile(rf"(?:{SENDER_FIELD}|{RECIPIENT_FIELD})", re.IGNORECASE)
ACCOUNT_VALUE = re.compile(rf"(?:{ACCOUNT_RE.pattern}|(?<!\w)(?:\*{{4,}}|[Xx]{{3,}}|[—–-])(?!\w))")


@dataclass(frozen=True)
class AccountEvidence:
    sender: str | None
    recipient: str | None
    distinct_numbers: int
    masked_pair: bool
    declared: frozenset[str]


def account_evidence(text: str) -> AccountEvidence:
    """Bind complete numbers or masks to their printed field or ordered table column."""
    numbers = set()

    def compact(match: re.Match) -> str:
        number = "".join(match[1].split())
        numbers.add(number)
        return number

    text = ACCOUNT_RE.sub(compact, text)
    # Preserve inline columns and the two explicit account clauses in bank letters.
    text = re.sub(rf"(?:(?<=[\d*:—–-])|(?<=XXX))[ \t]+(?={ACCOUNT_LABEL.pattern})", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b(z rachunku|na rachunek) nr (?=\d{26}\b)", r"\n\1 ", text)
    values = {"sender": set(), "recipient": set(), "generic": set()}
    declared = set()
    strict = []
    roles = []
    table = False
    participant_heading = False
    cells = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label = ACCOUNT_LABEL.match(line)
        if label:
            # One participant can have a company/name row before its “Rachunek”
            # subfield. A different field or ambiguous table clears that owner.
            parent = roles[0] if participant_heading and len(roles) == 1 and label.lastgroup == "generic" else None
            roles, cells = [], []
            field = parent is not None or ACCOUNT_FIELD.fullmatch(label[0]) is not None
            participant_heading = label.lastgroup != "generic" and not field
            participant = participant_heading
            count = 0
            while label:
                role = parent if not count and parent else label.lastgroup
                declared.add(role)
                if role not in roles:
                    roles.append(role)
                count += 1
                line = line[label.end() :].lstrip(" :")
                label = ACCOUNT_LABEL.match(line)
            table = count > 1
            if not line:
                continue
        if not roles:
            continue
        if BOUNDARY_RE.match(line) and not ACCOUNT_VALUE.match(line):
            roles = []
            continue
        if len(roles) > 1:
            # A row under two headers has only cells. A later archive or
            # reference field cannot complete a one-cell, ambiguous row.
            matches = list(ACCOUNT_VALUE.finditer(line))
            if ACCOUNT_VALUE.sub("", line).strip():
                if cells or matches:
                    roles = []
                continue
        else:
            match = ACCOUNT_VALUE.search(line) if table else ACCOUNT_VALUE.match(line)
            matches = [match] if match else []
            if not matches and participant:
                # A participant heading can name the company before its NRB
                # on the following line. Consume at most one company row.
                participant = False
                continue
        cells.extend(match[1] for match in matches)  # A mask occupies its own cell with value None.
        if len(cells) == len(roles):
            if field and not table and ACCOUNT_VALUE.fullmatch(line):
                strict.append((roles[0], cells[0]))
            for role, number in zip(roles, cells):
                values[role].add(number)
            roles = []
        elif len(roles) == 1 or len(cells) > len(roles):
            roles = []

    # A generic "Konto" beside one named account identifies the other member of
    # a pair. An explicit empty or masked field cannot acquire this number.
    if len(numbers) == 2 and len(values["generic"]) == 1:
        for role, opposite in (("sender", "recipient"), ("recipient", "sender")):
            if role not in declared and values[opposite] and values["generic"].isdisjoint(values[opposite]):
                values[role] = values["generic"]

    sender, recipient = (
        next(iter(values[role])) if len(values[role]) == 1 else None for role in ("sender", "recipient")
    )
    masked_pair = (
        len(strict) == 2
        and {role for role, _ in strict} == {"sender", "recipient"}
        and sum(number is None for _, number in strict) == 1
        and any(number and iban.is_valid("PL" + number) for number in (sender, recipient))
    )
    # Supplement bank statements in prose and debit tables only with role-specific evidence.
    printed = printed_accounts(text)
    if "sender" not in declared:
        sender = printed.get("sender", sender)
    if "recipient" not in declared:
        recipient = printed.get("recipient", recipient)
    return AccountEvidence(sender, recipient, len(numbers), masked_pair, frozenset(declared | printed.keys()))


# Normalize only complete account tokens and calendar dates read by OCR on a receipt.
OCR_NRB = re.compile(r"(?<![\w/?*])(?:PL\s?)?([0-9?]{2}(?:[ \n]?[0-9?]{4}){6})(?![\w/?*])")
OCR_DATE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})(\d{4})(?!\d)")


def normalize_receipt(text: str) -> str:
    def number(match: re.Match) -> str:
        compact = "".join(match[1].split())
        if iban.is_valid("PL" + compact):
            return match[0]
        return validated_account(compact) or "?"

    def date(match: re.Match) -> str:
        candidate = ".".join(match.groups())
        return candidate if to_iso(candidate) else match[0]

    return OCR_NRB.sub(number, OCR_DATE.sub(date, text))
