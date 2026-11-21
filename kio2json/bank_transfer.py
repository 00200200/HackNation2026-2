"""Bank-transfer confirmation -> przelew_bankowy."""

import re

from .common import DATE, DATE_RE, squash, to_iso

# 26-digit Polish account number, optionally 'PL'-prefixed, grouped or wrapped across lines.
ACCOUNT_RE = re.compile(r"(?<![\d])(?:PL\s?)?(\d{2}(?:[ \n]?\d{4}){6})(?!\d)")
SENDER_RE = re.compile(r"nadawc|zleceniodawc|płatnik|obciąż|z rachunku")
RECIPIENT_RE = re.compile(r"odbiorc|beneficjent|adresat|uznawan|na rachunek")

MONEY = r"(?<![\d.,])(?:\d{1,3}(?:[ .\u00a0]\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?![.,]?\d)"
AMOUNT_LABEL = r"(?:kwota(?: (?:operacji|przelewu|transakcji|zaksięgowana))?|wartość)"
DATE_LABEL = r"data (?:operacji|transakcji|realizacji|wykonania|księgowania|obciążenia|zlecenia)"
REFERENCE_LABEL = r"(?:nr ref\.?|nr transakcji(?: w [^:\n]{1,55}(?=:))?|numer (?:referencyjny|transakcji)|identyfikator (?:operacji|transakcji))(?: operacji)?"
TITLE_LABEL = r"(?:tytułem|tytu[łl](?: (?:przelewu|operacji))?|opis)"
FIELD_LABEL = rf"(?:{AMOUNT_LABEL}|{DATE_LABEL}|{REFERENCE_LABEL}|{TITLE_LABEL})"
GENERIC_LABEL = r"[^\W\d_][\w /().-]{0,55}:"
# A known undelimited field must match the full label word, never a prefix of a title.
BOUNDARY_RE = re.compile(
    rf"^(?:{GENERIC_LABEL}|{FIELD_LABEL}(?!\w)|(?:waluta|typ operacji|kanał|tryb|nadawca|odbiorca|"
    r"zleceniodawca|beneficjent|płatnik|adresat przelewu|dane (?:nadawcy|odbiorcy)|rachunek|"
    r"data (?:wystawienia|wydruku|stempla|sporządzenia)|opłata(?:/prowizja)?(?=\s*[\d.:]|$))\b|[-*]{3,}|bank nie ponosi\b|dokument wygenerowany\b|potwierdzenie ma charakter\b)",
    re.IGNORECASE,
)
STATUS_SCOPE = r"(?:operacji|transakcji|przelewu|realizacji|dyspozycji|zlecenia|płatności)"
STATE_WORD = r"(?:przelew\s+)?(?:oczek|odrzu|anul|zrealiz|wykon|zaksięgow|wstrzym|nie|w realizacji)"
STATUS = re.compile(
    rf"^(?:(?:status|stan)(?: +{STATUS_SCOPE})?(?:[ \t]*[:.][ .:\t]*|[ \t]+(?={STATE_WORD}))"
    rf"|status(?: +{STATUS_SCOPE})?[ \t]+(?=\S+$))(?P<value>[^\s.:].*)$",
    re.IGNORECASE,
)
PADDING = r"[\s.:]*"
AMOUNT_RE = re.compile(rf"^{AMOUNT_LABEL}{PADDING}(?:PLN\s*)?[−-]?[ \t]*({MONEY})", re.IGNORECASE | re.MULTILINE)
OPERATION_DATE_RE = re.compile(rf"^({DATE_LABEL}){PADDING}({DATE})", re.IGNORECASE | re.MULTILINE)
REFERENCE_RE = re.compile(
    rf"^(?i:{REFERENCE_LABEL}){PADDING}((?=[A-Z0-9/_.-]*\d)[A-Z0-9][A-Z0-9/_-]*(?:\.[A-Z0-9/_-]+)*)", re.MULTILINE
)
TITLE_LABEL_RE = re.compile(rf"^{TITLE_LABEL}\b\s*:?\s*(.*)$", re.IGNORECASE)
# Bank letters attest a dated debit and a completed payment in one sentence.
LETTER_RE = re.compile(
    rf"^Bank potwierdza,? że w dniu ({DATE}) z rachunku\b(?:(?!\n\s*{GENERIC_LABEL}).)*?"
    rf"\bwykonano przelew(?: \w+)? w kwocie ({MONEY})",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)

# Only an affirmative, dated execution statement can outrank a printed posting date.
COMPLETED_PAYMENT = r"(?:wykonano|zrealizowano)"
PAYMENT_NOUN = r"(?:przelew|transakcję|operację|płatność)"
EXECUTION_DAY_RE = re.compile(
    rf"^(?:bank (?:potwierdza|zaświadcza),? że\s+)?(?:"
    rf"(?:w dniu|dnia)\s+(?P<before>{DATE})\s+(?:z rachunku\s+(?:nr\.?\s+)?{ACCOUNT_RE.pattern}\s+)?"
    rf"{COMPLETED_PAYMENT}\s+{PAYMENT_NOUN}\b|"
    rf"(?:{PAYMENT_NOUN}\s+)?{COMPLETED_PAYMENT}"
    rf"(?:\s+{PAYMENT_NOUN})?\s+(?:w dniu|dnia)\s+(?P<after>{DATE}))",
    re.IGNORECASE | re.MULTILINE,
)


def _legacy_accounts(text: str) -> tuple[str | None, str | None]:
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
        if BOUNDARY_RE.match(value) or STATUS.match(value):
            return None
        parts = [value]
        for following in lines[index + 1 :]:
            if BOUNDARY_RE.match(following.strip()) or STATUS.match(following.strip()):
                break
            parts.append(following)
        title = squash(re.sub(r"(?<=\w-)\n(?=\w)", "", "\n".join(p.strip() for p in parts)))
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


# Printed role fields apply to both text and scans. Only the OCR adapter repairs digits.
ROLE_NOUN = r"(?:rachun(?:ek|ku)|kont[oa]|IBAN)"
DIRECT_ROLE = re.compile(
    rf"(?im)^(?:(?:(?:numer|nr\.?)\s+)?{ROLE_NOUN}\s+)?"
    r"(?:(?P<sender>nadawc[ay]|zleceniodawc[ay]|płatnik(?:a)?|obciąż(?:an|on)[ey]|źródłow[ey]|z (?:rachunku|konta))"
    r"|(?P<recipient>odbiorc[ay]|beneficjent(?:a)?|uznawan[ey]|docelow[ey]|na (?:rachunek|konto)))\b"
)
MASK = re.compile(r"(?i)(?:PL[ \t]*)?(?=[0-9x* .-]*[x*])[0-9x*][0-9x* .-]{2,}[0-9x*]")
PARTY_SECTION = re.compile(r"(?i)^(?:dane\s+|rachunek\s+|konto\s+)?(właściciel\w*|posiadacz\w*|kontrahent\w*)\b")
EXECUTION = re.compile(
    r"\b(?:obciąży(?:liśmy|łem|ła|ł)|obciążono|przekaza(?:liśmy|no|ła|ł)|przela(?:liśmy|no|ła|ł)|"
    r"(?:wykona|zrealizowa|zaksięgowa)(?:liśmy|no|ła|ł))\b",
    re.IGNORECASE,
)
NEGATED_PAYMENT = re.compile(
    # Require a direct assertion by the bank or an impersonal refusal. A conditional,
    # historical note or complaint instruction elsewhere in the receipt cannot veto it.
    r"^(?:(?:bank\s+)?(?:oświadcz|potwierdz|poświadcz|zaświadcz|informuj)\w*(?:,?\s+że\s+|:\s*))?"
    rf"(?:(?:w dniu\s+)?{DATE}\s+)?(?:bank\s+)?nie\s+"
    + EXECUTION.pattern
    + r"\s+(?:(?:zlecon\w*|tego|tej|środk\w*|na|z)\s+){0,2}(?:przelew|transakcj|operacj|płatnoś|dyspozycj|rachun|kont|środk)\w*",
    re.IGNORECASE,
)
ATTESTATION = re.compile(r"\b(?:poświadcz|potwierdz|zaświadc|dowód)\w*", re.IGNORECASE)
PROSE_ACCOUNT = re.compile(
    rf"(?i)(?:(?P<sender>obciąży\w*|obciążono|z)\s+(?:{ROLE_NOUN})|"
    rf"(?P<recipient>na)\s+(?:{ROLE_NOUN}))\s+(?:nr\.?\s+)?{ACCOUNT_RE.pattern}"
)


def _printed_role_cells(text: str):
    for match in DIRECT_ROLE.finditer(text):
        end = text.find("\n", match.end())
        value = text[match.end() : end if end >= 0 else None].lstrip(" \t:")
        if not value and end >= 0:
            value = text[end + 1 :].partition("\n")[0].strip()
        account = ACCOUNT_RE.fullmatch(value)
        if account:
            yield match.lastgroup, "".join(account[1].split()), False
        elif MASK.fullmatch(value):
            explicit_account = re.search(ROLE_NOUN, match[0], re.IGNORECASE)
            yield match.lastgroup, None, bool(explicit_account and re.search(r"\d", value))


def partial_account_mask(text: str, role: str) -> bool:
    # A part-visible mask must belong to the missing account, including when the
    # value occupies the following line. A masked participant name is insufficient.
    cells = {(number, partial) for label, number, partial in _printed_role_cells(text) if label == role}
    return cells == {(None, True)}


def _payment_lines(text: str):
    """Keep assertions, preserving breaks at titles, questions and conditional text."""
    lines = text.splitlines()
    in_title = False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if TITLE_LABEL_RE.match(line):
            in_title = True
        elif BOUNDARY_RE.match(line):
            in_title = False
        conditional = i and re.search(r"\b(?:jeśli|jeżeli|gdy|gdyby|o ile)\b[^.!?;]*$", lines[i - 1], re.IGNORECASE)
        yield "" if in_title or conditional or line.endswith("?") else line


def payment_denied(text: str) -> bool:
    return any(NEGATED_PAYMENT.match(line) for line in _payment_lines(text))


def executed_letter(text: str) -> bool:
    return bool(ATTESTATION.search(text) and EXECUTION.search(text) and not payment_denied(text))


TABLE_HEADER = re.compile(rf"(?i)\b(?:{DATE_LABEL}|data waluty|{AMOUNT_LABEL})\b")
TABLE_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
SIGNED_MONEY = re.compile(rf"(?:PLN[ \t]*)?([−-]?)({MONEY})(?:[ \t]*(?:PLN|zł))?", re.IGNORECASE)


def _posted_row(text: str) -> tuple[str, dict[str, str]] | None:
    lines = text.splitlines()
    records = []
    for index, line in enumerate(lines[:-1]):
        headers = list(TABLE_HEADER.finditer(line))
        if len(headers) < 2 or TABLE_HEADER.sub("", line).strip(" \t|:"):
            continue
        if not any(h[0].lower().startswith("data ") for h in headers):
            continue
        if not any(not h[0].lower().startswith("data ") for h in headers):
            continue
        # Each header determines the type of the corresponding cell; ignore an optional clock in date cells.
        for row in lines[index + 1 :]:
            row = TABLE_TIME.sub("", row).strip(" \t|")
            fields = {}
            amount = None
            for h in headers:
                key = h[0].casefold()
                token = (DATE_RE if key.startswith("data ") else SIGNED_MONEY).match(row)
                if not token:
                    break
                if key.startswith("data "):
                    fields[key] = token[0]
                else:
                    amount = token[1] + token[2]
                row = row[token.end() :].lstrip(" \t|")
            else:
                if not row and amount is not None:
                    records.append((amount, fields))
                    continue
            break
    return records[0] if len(records) == 1 else None


def _participant_accounts(text: str) -> dict[str, str]:
    candidates = {}
    role = None
    for line in text.splitlines():
        line = line.strip()
        section = PARTY_SECTION.match(line)
        if section:
            role = "recipient" if section[1].casefold().startswith("kontrahent") else "sender"
        elif (
            DIRECT_ROLE.match(line)
            or TABLE_HEADER.search(line)
            or (BOUNDARY_RE.match(line) and not re.match(rf"(?i)^(?:{ROLE_NOUN}|numer rachunku|nr rachunku)\b", line))
        ):
            role = None
        if role:
            for number in ACCOUNT_RE.finditer(line):
                candidates.setdefault(role, set()).add("".join(number[1].split()))
    return {role: next(iter(values)) for role, values in candidates.items() if len(values) == 1}


def printed_accounts(text: str) -> dict[str, str | None]:
    cells = {}
    for label, value, _ in _printed_role_cells(text):
        cells.setdefault(label, set()).add(value)
    roles = {label: next(iter(values)) if len(values) == 1 else None for label, values in cells.items()}
    posted = _posted_row(text)
    if posted and posted[0].startswith(("-", "−")):
        for role, value in _participant_accounts(text).items():
            roles.setdefault(role, value)
    if executed_letter(text):
        mentions = {}
        for m in PROSE_ACCOUNT.finditer(text):
            role = "sender" if m["sender"] else "recipient"
            mentions.setdefault(role, set()).add("".join(m[3].split()))
        for role, values in mentions.items():
            if len(values) == 1:
                roles.setdefault(role, next(iter(values)))
    return roles


ANCILLARY_ACCOUNT = re.compile(
    r"(?im)^(?:(?:numer|nr\.?) +)?(?:konto|konta|rachunek|rachunku)\b[^:\n\d]{0,55}"
    r"\b(?:zwrot|prowizj|opłat|archiw)\w*[^:\n\d]*[ \t:]*"
    r"(?:\n[ \t]*)?" + ACCOUNT_RE.pattern
)


def _accounts(text: str) -> tuple[str | None, str | None]:
    # Remove explicitly non-payment roles before the older two-account inference.
    text = ANCILLARY_ACCOUNT.sub("", text)
    roles = printed_accounts(text)
    sender, recipient = _legacy_accounts(text)
    return roles.get("sender", sender), roles.get("recipient", recipient)


def _unique(matches) -> str | None:
    values = set(matches)
    return next(iter(values)) if len(values) == 1 else None


PROSE_CLAUSE = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])|\n\s*\n")


def _prose_values(text: str) -> tuple[float | None, str | None]:
    if not executed_letter(text):
        return None, None
    clauses = PROSE_CLAUSE.split(text)
    amounts, days = [], []
    for clause in clauses:
        if not EXECUTION.search(clause):
            continue
        amounts.extend(re.findall(rf"(?i)\b(?:kwot[ąęy]|w kwocie|na sumę)\s+({MONEY})", clause))
        days.extend(m[0] for m in DATE_RE.finditer(clause))
    amount, day = _unique(amounts), _unique(days)
    return _amount(amount) if amount else None, to_iso(day) if day else None


def transaction_values(text: str) -> tuple[float | None, str | None]:
    fields = _field_text(text)
    amount = AMOUNT_RE.search(fields)
    money = _amount(amount[1]) if amount else None
    dates = [(m[1].casefold(), m[2]) for m in OPERATION_DATE_RE.finditer(fields)]
    posted = _posted_row(fields)
    if posted:
        raw, cells = posted
        if money is None:
            money = _amount(raw.lstrip("−-"))
        dates.extend(cells.items())
    for clause in PROSE_CLAUSE.split("\n".join(_payment_lines(fields))):
        letter = LETTER_RE.search(clause)
        if letter and len(DATE_RE.findall(letter[0])) == 1:
            dates.append(("data wykonania", letter[1]))
        for statement in EXECUTION_DAY_RE.finditer(clause):
            dates.append(("data wykonania", statement["before"] or statement["after"]))
    # Select by the meaning of the printed date, across both labelled fields and table cells.
    # A value date is not evidence of execution.
    day = None
    for labels in (
        {"data operacji", "data transakcji"},
        {"data wykonania", "data realizacji"},
        {"data księgowania", "data zlecenia"},
        {"data obciążenia"},
    ):
        day = next((parsed for label, raw in dates if label in labels and (parsed := to_iso(raw))), None)
        if day is not None:
            break
    if money is None or day is None:
        letter = LETTER_RE.search(fields)
        narrative_amount, narrative_day = (_amount(letter[2]), to_iso(letter[1])) if letter else _prose_values(fields)
        if money is None:
            money = narrative_amount
        day = day or narrative_day
    return money, day


def extract(text: str) -> dict:
    sender, recipient = _accounts(text)
    amount, day = transaction_values(text)
    fields = _field_text(text)
    reference = REFERENCE_RE.search(fields) or re.search(
        r"(?im)^referencj[ae] (?:banku|transakcji)\s*:?\s+([A-Z0-9/-]*\d[A-Z0-9/-]*)[ \t]*$", fields
    )
    title = _title(fields)
    if executed_letter(fields):
        reference = reference or re.search(
            r"(?i)\b(?:pod |z )?identyfikator(?:em)?\s+([A-Z0-9/-]*\d[A-Z0-9/-]*)\b", fields
        )
        remittance = re.search(r"(?im)\b(?:treść płatności|tytuł płatności|tytułem)\s*:\s*([^\n]+)", fields)
        if title is None and remittance:
            title = remittance[1].strip().removesuffix(".")
    reference = reference or re.search(r"(?im)^dzienny numer transakcji[ .:\t]+(\d+)\b", fields)
    return {
        "przelew_bankowy": {
            "data_operacji": day,
            "kwota": amount,
            "na_rachunek": recipient,
            "numer_transakcji": reference[1] if reference else None,
            "tytul": title,
            "z_rachunku": sender,
        }
    }
