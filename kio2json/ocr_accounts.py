"""OCR account fields and evidence shared by routing and extraction."""

import re
from dataclasses import dataclass

from stdnum import iban

from .bank_transfer import AMOUNT_LABEL, BOUNDARY_RE, completed_value_block, posted_party_debit, printed_accounts
from .common import DATE, to_iso
from .ocr_booking import normalize_booking_rows
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
    prefixed_roles: frozenset[str] = frozenset()


def account_evidence(text: str) -> AccountEvidence:
    """Bind complete numbers or masks to their printed field or ordered table column."""
    numbers = set()
    prefixed = set()

    def compact(match: re.Match) -> str:
        number = "".join(match[1].split())
        numbers.add(number)
        return ("PL" if match[0].startswith("PL") else "") + number

    # A party block can contain a name/address and account column on one physical row.
    table_roles = {}
    for header in re.finditer(r"(?im)^dane (nadawcy|odbiorcy)\s*\n[^\n]*\bnumer rachunku\b[^\n]*\n([^\n]+)", text):
        row = list(ACCOUNT_RE.finditer(header[2]))
        if len(row) == 1:
            role = "sender" if header[1].casefold() == "nadawcy" else "recipient"
            number = "".join(row[0][1].split())
            table_roles.setdefault(role, set()).add(number)
            if row[0][0].startswith("PL"):
                prefixed.add((role, number))

    text = ACCOUNT_RE.sub(compact, text)
    # Preserve inline columns and the two explicit account clauses in bank letters.
    text = re.sub(rf"(?:(?<=[\d*:—–-])|(?<=XXX))[ \t]+(?={ACCOUNT_LABEL.pattern})", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b(z rachunku|na rachunek) nr (?=(?:PL)?\d{26}\b)", r"\n\1 ", text)
    values = {"sender": set(), "recipient": set(), "generic": set()}
    for role, cells in table_roles.items():
        values[role].update(cells)
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
        for role, token in zip(roles[len(cells) :], matches):
            if token[0].startswith("PL"):
                prefixed.add((role, token[1]))
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
    if sender is None and posted_party_debit(text):
        # A bank can restate the holder's own account in international format below the debit.
        owner = re.findall(r"(?im)^numer IBAN tego rachunku[ :]+PL(\d{26})\b", text)
        if len(set(owner)) == 1 and iban.is_valid("PL" + owner[0]):
            sender = owner[0]
            prefixed.add(("sender", sender))
    formats = frozenset(
        role for role, value in (("sender", sender), ("recipient", recipient)) if (role, value) in prefixed
    )
    return AccountEvidence(sender, recipient, len(numbers), masked_pair, frozenset(declared | printed.keys()), formats)


# Normalize only complete account tokens and calendar dates read by OCR on a receipt.
OCR_NRB = re.compile(r"(?<![\w/?*])(?:PL\s?)?([0-9?]{2}(?:[ \n]?[0-9?]{4}){6})(?![\w/?*])")
OCR_DATE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})(\d{4})(?!\d)")


def normalize_receipt(text: str) -> str:
    def number(match: re.Match) -> str:
        compact = "".join(match[1].split())
        if iban.is_valid("PL" + compact):
            return match[0]
        repaired = validated_account(compact)
        return ("PL" if match[0].startswith("PL") else "") + repaired if repaired else "?"

    def date(match: re.Match) -> str:
        candidate = ".".join(match.groups())
        return candidate if to_iso(candidate) else match[0]

    # Ignore a section title in front of the three booking columns. The typed row
    # parser still requires a date in both date columns and exactly one debit.
    text = re.sub(
        r"(?im)^[^\n]*\bda[łt]a waluty[ \t]+data księgowania[ \t]+kwota[ \t]*$",
        "Data waluty Data księgowania Kwota",
        text,
    )
    text = re.sub(r"(?im)^[|/–-]+[ \t]*(?=potwierdzenie\b)", "", text)
    text = re.sub(
        rf"(?im)^({AMOUNT_LABEL}[ :]+[−-]?[\d \u00a0]+?)[ \t]*([,.])[ \t]*(\d{{2}})(?=[ \t]*(?:PLN|zł)\b)",
        r"\1\2\3",
        text,
    )
    text = re.sub(r"(?im)^(tytu[łl])[ :]+[;| \t]+(?:[a-z])?[ \t]*$", r"\1:", text)
    text = re.sub(r"(?im)^((?:typ|rodzaj) transakcji) ", r"\1: ", text)
    # A reference value can share a line with the next date column.
    text = re.sub(r"(?im)^(\d+)[ \t]+(?=data księgowania\b)", r"\1\n", text)
    block = completed_value_block(text)
    if block:
        day, amount = block
        text += f"\nData operacji: {day}\nKwota: {amount}"
    text = re.sub(r'(?im)^(data operacji)\s+["„](?=\d)', r"\1 ", text)
    text = re.sub(r"(?im)^rachunk(?= odbiorcy\b)", "Rachunek", text)
    text = re.sub(rf"(?im)^data[ :]+({DATE})[ \t]*\nwykonania\b", r"Data wykonania: \1", text)
    text = re.sub(r"(?im)^[+| \t]*numer[ :]+(\d+)[ \t]*\ntransakcji[ |\t]*$", r"Numer transakcji: \1", text)
    return OCR_NRB.sub(number, OCR_DATE.sub(date, normalize_booking_rows(text)))
