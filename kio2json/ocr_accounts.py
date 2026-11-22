"""OCR account fields and evidence shared by routing and extraction."""

import re
from dataclasses import dataclass

from stdnum import iban

from .accounts import (
    ACCOUNT_RE,
    OCR_ACCOUNT_RE,
    account_identity,
    account_matches,
    complete_account_match,
    valid_account,
)
from .bank_transfer import (
    ACCOUNT_CURRENCY,
    AMOUNT_LABEL,
    BOUNDARY_RE,
    completed_value_block,
    posted_party_debit,
    printed_accounts,
)
from .common import DATE, to_iso
from .ocr_booking import normalize_booking_rows
from .receipt_layout import validated_account

ACCOUNT_NOUN = r"(?:(?:numer|nr\.?) (?:rachunku|konta)|rachunek|konto)"
SENDER = r"(?:nadawc[ay]|zleceniodawc[ay]|płatnik(?:a)?)"
RECIPIENT = r"(?:odbiorc[ay]|beneficjent(?:a)?|adresat(?:a)?(?: przelewu)?)"
SENDER_FIELD = rf"(?:{ACCOUNT_NOUN} (?:{SENDER}|obciąż(?:an|on)[ye])|z rachunku)"
RECIPIENT_FIELD = rf"(?:{ACCOUNT_NOUN} (?:{RECIPIENT}|uznawan[ye])|na rachunek)"
ACCOUNT_LABEL = re.compile(
    rf"(?:(?P<sender>{SENDER_FIELD}|(?:dane )?{SENDER})|"
    rf"(?P<recipient>{RECIPIENT_FIELD}|(?:dane )?{RECIPIENT})|(?P<generic>{ACCOUNT_NOUN}))\b{ACCOUNT_CURRENCY}",
    re.IGNORECASE,
)
ACCOUNT_FIELD = re.compile(rf"(?:{SENDER_FIELD}|{RECIPIENT_FIELD}){ACCOUNT_CURRENCY}", re.IGNORECASE)
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
        if not complete_account_match(match):
            return match[0]
        number = "".join(match[1].split())
        numbers.add(account_identity(number))
        after = text[match.end() :]
        if after.startswith((" ", "\t")) and ACCOUNT_LABEL.match(after.lstrip(" \t")):
            return number + "\n"
        return number

    # A party block can contain a name/address and account column on one physical row.
    table_roles = {}
    for header in re.finditer(r"(?im)^dane (nadawcy|odbiorcy)\s*\n[^\n]*\bnumer rachunku\b[^\n]*\n([^\n]+)", text):
        row = list(account_matches(header[2]))
        if len(row) == 1:
            role = "sender" if header[1].casefold() == "nadawcy" else "recipient"
            number = "".join(row[0][1].split())
            table_roles.setdefault(role, set()).add(number)

    text = ACCOUNT_RE.sub(compact, text)
    # Preserve inline columns and the two explicit account clauses in bank letters.
    text = re.sub(rf"(?:(?<=[\d*:—–-])|(?<=XXX))[ \t]+(?={ACCOUNT_LABEL.pattern})", "\n", text, flags=re.IGNORECASE)
    text = re.sub(rf"(?i)(?:\n[ \t]*)?\b(z rachunku|na rachunek) nr\.?\s+(?={ACCOUNT_RE.pattern})", r"\n\1 ", text)
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
            matches = [match] if match and (not match[1] or complete_account_match(match)) else []
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
        and any(number and valid_account(number) for number in (sender, recipient))
    )
    # Supplement bank statements in prose and debit tables only with role-specific evidence.
    printed = printed_accounts(text)
    if "sender" not in declared:
        sender = printed.get("sender", sender)
    if "recipient" not in declared:
        recipient = printed.get("recipient", recipient)
    if sender is None and posted_party_debit(text):
        # A bank can restate the holder's own account in international format below the debit.
        owner = re.findall(rf"(?im)^numer IBAN tego rachunku[ :]+{ACCOUNT_RE.pattern}", text)
        if len(set(owner)) == 1 and owner[0][:2].isalpha() and valid_account(owner[0]):
            sender = owner[0]
    return AccountEvidence(sender, recipient, len(numbers), masked_pair, frozenset(declared | printed.keys()))


# Receipt repairs touch only complete account tokens and valid calendar dates. `repair_receipt_layout` runs on every
# receipt, the checksum substitution of `normalize_receipt` on OCR text only.
# An inserted stroke can split an otherwise complete printed account. Only remove
# it in an explicit account cell when the remaining 26 digits verify unchanged.
SLASH_ACCOUNT = re.compile(
    rf"(?im)^((?:{ACCOUNT_FIELD.pattern})[ \t]*:[ \t]*(?:\n[ \t]*)?(?:PL[ \t]*)?)(\d+/\d+)[ \t]*$"
)
OCR_DATE = re.compile(r"(?<!\d)(\d{2})\.(\d{2})(\d{4})(?!\d)")


def _verified_account(match: re.Match) -> str:
    if not complete_account_match(match):
        return match[0]
    compact = "".join(match[1].split())
    if valid_account(compact):
        return match[0]
    return validated_account(compact) or "?"


def normalize_receipt(text: str) -> str:
    """OCR receipt text: the layout repairs, then every complete account token checked against its checksum."""
    return OCR_ACCOUNT_RE.sub(_verified_account, repair_receipt_layout(text))


def repair_receipt_layout(text: str) -> str:
    """Repair the layout of a booking printout.

    Accounts stay as printed, except that a stray stroke inside an account cell is removed when the remaining 26
    digits verify."""

    def remove_stroke(match: re.Match) -> str:
        digits = match[2].replace("/", "")
        return match[1] + digits if len(digits) == 26 and iban.is_valid("PL" + digits) else match[0]

    def date(match: re.Match) -> str:
        candidate = ".".join(match.groups())
        return candidate if to_iso(candidate) else match[0]

    text = SLASH_ACCOUNT.sub(remove_stroke, text)
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
    # In a faxed two-column confirmation, a payee address can precede the
    # reference heading while its value occupies the following row.
    text = re.sub(
        r"(?im)\bnumer referencyjny transakcji:[ \t]*\n(?=[A-Z0-9/-]*\d[A-Z0-9/-]*[ \t]*$)",
        "\nNumer transakcji: ",
        text,
    )
    block = completed_value_block(text)
    if block:
        day, amount = block
        text += f"\nData operacji: {day}\nKwota: {amount}"
    text = re.sub(r'(?im)^(data operacji)\s+["„](?=\d)', r"\1 ", text)
    text = re.sub(r"(?im)^rachunk(?= odbiorcy\b)", "Rachunek", text)
    text = re.sub(rf"(?im)^data[ :]+({DATE})[ \t]*\nwykonania\b", r"Data wykonania: \1", text)
    text = re.sub(r"(?im)^[+| \t]*numer[ :]+(\d+)[ \t]*\ntransakcji[ |\t]*$", r"Numer transakcji: \1", text)
    return OCR_DATE.sub(date, normalize_booking_rows(text))


def disputed_account_cells(record, boxes):
    from collections import Counter

    from .ocr_choices import Cell, shape
    from .receipt_layout import _row_headers, word_rows

    fields = record["przelew_bankowy"]
    roles = {"Rachunek nadawcy": "z_rachunku", "Rachunek odbiorcy": "na_rachunek"}
    cells = []
    labels = Counter()
    rows, height = word_rows(boxes)
    for row, following in zip(rows, rows[1:] + [[]]):
        headers = _row_headers(row, following, height, ocr=True)
        # A declaration still counts when its account is empty or partly
        # masked, including aliases absent from the table-header vocabulary.
        line = " ".join(w.text for w in row)
        mentioned = {m.lastgroup for m in ACCOUNT_LABEL.finditer(line)}
        recognized = [roles[label] for _, _, label in headers if label in roles]
        labels.update(recognized)
        for owner, field in (("sender", "z_rachunku"), ("recipient", "na_rachunek")):
            if owner in mentioned and field not in recognized:
                labels[field] += 1
        if not headers or headers[0][0]:
            continue
        for i, (start, stop, label) in enumerate(headers):
            if label not in roles:
                continue
            field = roles[label]
            end = headers[i + 1][0] if i + 1 < len(headers) else len(row)
            words = row[stop:end]
            if words:
                if words[0].x0 - row[stop - 1].x1 > 3 * height:
                    continue
            elif following and min(w.y0 for w in following) - row[start].y1 <= 3 * height:
                left = row[start].x0 - height
                right = row[end].x0 - height if end < len(row) else float("inf")
                words = [w for w in following if left <= w.x0 and w.x1 <= right]
                if not words or abs(words[0].x0 - row[start].x0) > 2 * height:
                    continue
            raw = "".join(w.text for w in words)
            if shape(field, raw) and fields[field] in (None, raw):
                cells.append(Cell(fields, field, raw, words))
    cells = [c for c in cells if labels[c.field] == 1]
    if not any(fields[c.field] is None for c in cells):
        return cells
    # A null can mean conflicting owners or an explicit mask. Require the
    # primary transcript's own role binding before restoring a discarded value.
    transcript = "\n".join(" ".join(w.text for w in row) for row in rows)
    # A redacted page can contain the same digits in a second role or
    # an unrelated reference. Leave missing fields alone on such a page.
    if re.search(r"[*Xx•●█]{2,}|[0-9][*•●█…]|[*•●█…][0-9]", transcript):
        return [c for c in cells if fields[c.field] is not None]
    primary = account_evidence(transcript)
    return [
        c
        for c in cells
        if fields[c.field] is not None
        or getattr(primary, "sender" if c.field == "z_rachunku" else "recipient") == c.original
    ]
