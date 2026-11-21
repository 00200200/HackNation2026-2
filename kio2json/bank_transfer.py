"""Bank-transfer confirmation -> przelew_bankowy."""

import re
from dataclasses import dataclass

from stdnum import iban

from .common import DATE, squash, to_iso
from .receipt_layout import booking_heading

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\w/|*])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?![\w/|*])")
SENDER_LABEL = (
    r"(?:rachunek (?:nadawcy|zleceniodawcy|obciążany)|z rachunku|(?:dane )?(?:nadawc[ay]|zleceniodawc[ay]|płatnik))"
)
RECIPIENT_LABEL = r"(?:rachunek (?:odbiorcy|beneficjenta|uznawany)|na rachunek|(?:dane )?(?:odbiorc[ay]|beneficjent|adresat(?: przelewu)?))"
ACCOUNT_LABEL = re.compile(
    rf"(?:(?P<sender>{SENDER_LABEL})|(?P<recipient>{RECIPIENT_LABEL})|(?P<generic>konto|rachunek))\b", re.IGNORECASE
)
STRICT_ACCOUNT_LABEL = re.compile(r"rachunek (nadawcy|odbiorcy):", re.IGNORECASE)
ACCOUNT_VALUE = re.compile(rf"(?:{ACCOUNT_RE.pattern}|(?<!\w)(?:\*{{4,}}|[Xx]{{3,}}|[—–-])(?!\w))")

MONEY = r"(?<![\d.,])(?:\d{1,3}(?:[ .\u00a0]\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?![.,]?\d)"
AMOUNT_LABEL = r"(?:kwota(?: (?:operacji|przelewu|transakcji|zaksięgowana))?|wartość)"
DATE_LABEL = r"data (?:operacji|transakcji|realizacji|wykonania|księgowania|obciążenia|zlecenia)"
REFERENCE_LABEL = r"(?:nr ref\.?|numer (?:referencyjny|transakcji)|identyfikator (?:operacji|transakcji))(?: operacji)?"
TITLE_LABEL = r"(?:tytułem|tytu[łl](?: (?:przelewu|operacji))?|opis)"
FIELD_LABEL = rf"(?:{AMOUNT_LABEL}|{DATE_LABEL}|{REFERENCE_LABEL}|{TITLE_LABEL})"
GENERIC_LABEL = r"[^\W\d_][\w /().-]{0,55}:"
# A known undelimited field must match the full label word, never a prefix of a title.
BOUNDARY_RE = re.compile(
    rf"^(?:{GENERIC_LABEL}|{FIELD_LABEL}(?!\w)|(?:status|waluta|typ operacji|kanał|tryb|nadawca|odbiorca|"
    r"zleceniodawca|beneficjent|płatnik|adresat przelewu|dane (?:nadawcy|odbiorcy)|rachunek|"
    r"data (?:wystawienia|wydruku|stempla|sporządzenia)|opłata(?:/prowizja)?(?=\s*[\d.:]|$))\b|[-*]{3,}|bank nie ponosi\b|dokument wygenerowany\b|potwierdzenie ma charakter\b)",
    re.IGNORECASE,
)
AMOUNT_DATE_ROW_RE = re.compile(
    rf"^{AMOUNT_LABEL}[ \t]+{DATE_LABEL}[ \t]*\n[ \t]*(?:PLN\s*)?[−-]?[ \t]*({MONEY})(?:\s*(?:PLN|zł))?\s+({DATE})",
    re.IGNORECASE | re.MULTILINE,
)
PADDING = r"[\s.:]*"
AMOUNT_RE = re.compile(rf"^{AMOUNT_LABEL}{PADDING}(?:PLN\s*)?[−-]?[ \t]*({MONEY})", re.IGNORECASE | re.MULTILINE)
OPERATION_DATE_RE = re.compile(rf"^{DATE_LABEL}{PADDING}({DATE})", re.IGNORECASE | re.MULTILINE)
REFERENCE_RE = re.compile(rf"^(?i:{REFERENCE_LABEL}){PADDING}([A-Z]*\d[A-Z0-9/\-]{{5,}})", re.MULTILINE)
TITLE_LABEL_RE = re.compile(rf"^{TITLE_LABEL}\b\s*:?\s*(.*)$", re.IGNORECASE)
# Bank letters attest a dated debit and a completed payment in one sentence.
LETTER_RE = re.compile(
    rf"^Bank potwierdza,? że w dniu ({DATE}) z rachunku\b(?:(?!\n\s*{GENERIC_LABEL}).)*?"
    rf"\bwykonano przelew(?: \w+)? w kwocie ({MONEY})",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)


BANK_ACCOUNT = re.compile(r"(?<![\w/?*])(?:PL\s?)?([0-9?]{2}(?:[ \n]?[0-9?]{4}){6})(?![\w/?*])")


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


def booking_form(text: str) -> bool:
    return any(booking_heading(line) for line in text.splitlines()) or bool(re.search(r"(?im)^data obciążenia\b", text))


@dataclass(frozen=True)
class AccountEvidence:
    sender: str | None
    recipient: str | None
    distinct_numbers: int
    masked_pair: bool

    def checked_ocr_numbers(self) -> "AccountEvidence":
        return AccountEvidence(
            validated_account(self.sender) if self.sender else None,
            validated_account(self.recipient) if self.recipient else None,
            self.distinct_numbers,
            self.masked_pair,
        )


def account_evidence(text: str) -> AccountEvidence:
    """Bind complete numbers or masks to their printed field or ordered table column."""
    numbers = set()
    bank = booking_form(text)

    def compact(match: re.Match) -> str:
        number = "".join(match[1].split())
        numbers.add(number)
        if bank:
            return validated_account(number) or "?"
        return number

    source = text
    text = (BANK_ACCOUNT if bank else ACCOUNT_RE).sub(compact, text)
    # Preserve inline columns and the two explicit account clauses in bank letters.
    text = re.sub(rf"(?:(?<=[\d*:—–-])|(?<=XXX))[ \t]+(?={ACCOUNT_LABEL.pattern})", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b(z rachunku|na rachunek) nr (?=\d{26}\b)", r"\n\1 ", text)
    values = {"sender": set(), "recipient": set(), "generic": set()}
    declared = set()
    strict = []
    roles = []
    table = False
    cells = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label = ACCOUNT_LABEL.match(line)
        if label:
            roles, cells = [], []
            participant = not label[0].casefold().startswith(("konto", "rachunek", "na rachunek", "z rachunku"))
            count = 0
            while label:
                role = label.lastgroup
                declared.add(role)
                if role not in roles:
                    roles.append(role)
                count += 1
                line = line[label.end() :].lstrip(" :")
                label = ACCOUNT_LABEL.match(line)
            table = count > 1
            if STRICT_ACCOUNT_LABEL.match(raw.strip()) and ACCOUNT_VALUE.fullmatch(line):
                strict.append((roles[0], line))
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
        and sum(value.startswith("*") for _, value in strict) == 1
        and any(number and iban.is_valid("PL" + number) for number in (sender, recipient))
    )
    if bank and DEBIT_ROW.search(source):
        sender, recipient = _debit_accounts(source)
    return AccountEvidence(sender, recipient, len(numbers), masked_pair)


def _accounts(text: str) -> tuple[str | None, str | None]:
    accounts = account_evidence(text)
    return accounts.sender, accounts.recipient


def _amount(raw: str) -> float | None:
    # The configured output schema also imports the routing evidence type.
    from .output_schema import normalize

    amount = normalize("money", raw)
    return float(abs(amount)) if amount is not None else None


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
        title = squash(re.sub(r"(?<=-)\n(?=\w)", "", "\n".join(p.strip() for p in parts)))
        quoted = re.match(r"„(.+?)”", title)
        return quoted.group(1) if quoted else title or None
    return None


def _field_text(text: str) -> str:
    # PDF table columns may share a physical line. An empty title before a new
    # label also has a boundary even when only one space survives extraction.
    text = re.sub(r"\([^()]*\)", lambda match: squash(match[0]), text)
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


# On a posted debit, the account holder pays the counterparty. Keep the value
# date separate from the booking date directly below its column heading.
DEBIT_ROW = re.compile(
    rf"(?im)^[^\n]*?data księgowania[ \t]+kwota[ \t]*\n"
    rf"(?:{DATE}[ \t]+)?(\d{{2}}[.]\d{{2}}[.]?\d{{4}})(?:[ \t]+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?"
    rf"[ \t]+[−-]({MONEY})[ \t]*(?:PLN|zł)\b"
)


def _debit_accounts(text: str) -> tuple[str | None, str | None]:
    sections = re.split(r"(?im)^.*?\bdane kontrahenta\w*[^\n]*\n", text, maxsplit=1)
    if len(sections) != 2:
        return None, None
    owner = re.search(r"(?i)\bIBAN [^:\n]{0,35}rachunku\s*:\s*" + ACCOUNT_RE.pattern, text)
    holders = list(ACCOUNT_RE.finditer(sections[0]))
    payer = owner if owner else holders[0] if len(holders) == 1 else None
    beneficiary = list(BANK_ACCOUNT.finditer(sections[1].splitlines()[0])) if sections[1].splitlines() else []
    return (
        validated_account(re.sub(r"\s", "", payer[1])) if payer else None,
        validated_account(re.sub(r"\s", "", beneficiary[0][1])) if len(beneficiary) == 1 else None,
    )


def transaction_values(text: str) -> tuple[float | None, str | None]:
    text = _field_text(text)
    debit = DEBIT_ROW.search(text)
    if debit:
        day = re.sub(r"^(\d{2}[.]\d{2})(\d{4})$", r"\1.\2", debit[1])
        return _amount(debit[2]), to_iso(day)
    row = AMOUNT_DATE_ROW_RE.search(text)
    if row:
        return _amount(row[1]), to_iso(row[2])
    letter = LETTER_RE.search(text)
    if letter:
        return _amount(letter[2]), to_iso(letter[1])
    amount = AMOUNT_RE.search(text)
    date = re.search(rf"(?im)^data (?:operacji|transakcji){PADDING}({DATE})", text) or OPERATION_DATE_RE.search(text)
    return _amount(amount[1]) if amount else None, to_iso(date[1]) if date else None


def extract(text: str, *, accounts: AccountEvidence | None = None) -> dict:
    accounts = accounts or account_evidence(text)
    amount, day = transaction_values(text)
    text = _field_text(text)
    reference = re.search(r"(?im)^dzienny numer transakcji[ .:\t]+(\d+)\b", text) or REFERENCE_RE.search(text)
    if not reference:
        reference = re.search(r"(?im)^r[ea]f[ea]r[ea]ncj[ae] banku[^\n]*\n([A-Z0-9/-]*\d[A-Z0-9/-]*)\b", text)
    return {
        "przelew_bankowy": {
            "data_operacji": day,
            "kwota": amount,
            "na_rachunek": accounts.recipient,
            "numer_transakcji": reference.group(1) if reference else None,
            "tytul": _title(text),
            "z_rachunku": accounts.sender,
        }
    }
