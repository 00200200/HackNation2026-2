"""Classify by the document's own heading and transaction evidence."""

import re

from rapidfuzz.distance import Levenshtein

from . import bank_transfer, power_of_attorney
from .accounts import account_identity, account_matches, valid_account
from .appeal_charges import FILING
from .common import DATE, to_iso
from .ocr_accounts import AccountEvidence, account_evidence
from .ocr_booking import INTERLEAVED_DEBIT, ORDER_TYPE
from .receipt_layout import booking_heading

UNRELATED_HEADING = re.compile(
    r"^(?:wyrok|postanowienie|w imieniu rzeczypospolitej polskiej|faktura|wyciąg(?: bankowy| z rachunku| nr| okresowy)|historia (?:operacji|rachunku|transakcji)|wezwanie|prośba|wniosek|"
    r"prosimy o|proszę o|instrukcja|zamówienie|oferta handlowa)\b",
    re.IGNORECASE,
)
CONFIRMATION = (
    r"(?:potwierdzenie|dowód|zaświadczenie)\s+(?:(?:o\s+)?(?:wykonaniu|wykonania|realizacji|zaksięgowania)\s+)?(?:polecenia\s+)?"
    r"(?:przelewu|transakcji|operacji(?: bankowej)?)\b"
)
CONFIRMATION_HEADING = re.compile(
    rf"^(?:dotyczy:\s*|(?-i:[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ &.-]+)\s+)?{CONFIRMATION}", re.IGNORECASE
)
DEBIT_DETAILS = re.compile(r"^przelew z rachunku\s*[-–—]?\s+szczegóły transakcji zrealizowanej\b", re.IGNORECASE)
EXECUTED = re.compile(
    r"^(?:status[\s.:]*)?(?:przelew\s+)?(?:zrealizowan[yaoe]|wykonan[yaoe]|zaksięgowan[yaoe])\b", re.IGNORECASE
)
COMPLETED_STATUS = re.compile(r"(?:rozliczon|zakończon|zapłacon)[ayeo]\.?", re.IGNORECASE)
BANK_FIELDS = re.compile(
    r"\b(?:kwot[ayęą]|wartość|(?:nr|numer|identyfikator) (?:transakcji|operacji)|"
    r"data (?:operacji|księgowania|transakcji|obciążenia)|rachun(?:ek|ku)|IBAN|nadawc[ay]|odbiorc[ay]|beneficjent\w*)\b",
    re.IGNORECASE,
)
PAYMENT_DETAILS = re.compile(rf"\b(?:{CONFIRMATION}|szczeg[óo][łl]y (?:przelewu|transakcji|operacji)\b)", re.IGNORECASE)
ATTACHMENT_REFERENCE = re.compile(
    r"\b(?:załącz\w*|w załączeniu|przesył\w*|przedkład\w*|dołącz\w*|kopia)\b", re.IGNORECASE
)
LIST_MARKER = re.compile(r"^(?:\(?\d{1,3}[.)]|[-–—•])(?:\s+|$)")
PRINTED_AMOUNT = re.compile(r"\b\d+(?:[.,]\d{2})?[ \t]*(?:PLN|zł|EUR)\b", re.IGNORECASE)
PAYMENT_COPY = re.compile(
    r"kopia potwierdzenia (?:przelewu|płatności|transakcji|operacji(?: bankowej)?)", re.IGNORECASE
)
PAYMENT_RECORD = re.compile(
    r"przelew(?: (?:krajowy|zagraniczny|bankowy|natychmiastowy|wewnętrzny|wychodzący|przychodzący))?"
    r"|potwierdzenie płatności",
    re.IGNORECASE,
)
REQUEST_REFERENCE = re.compile(r"wniosek (?:nr\.?|numer)\s*:?\s*(?=[\w./-]*\d)[\w/-]+", re.IGNORECASE)
EXECUTION_ATTESTATION = re.compile(
    r"bank (?:potwierdza|poświadcza|zaświadcza) (?:wykonanie|realizację|zaksięgowanie) "
    r"(?:przelewu|płatności|transakcji|operacji)\.?",
    re.IGNORECASE,
)


# Compare Polish cues after folding, while keeping the original text for value extraction.
POLISH_FOLD = str.maketrans("ąćęłńóśźż", "acelnoszz")
COVER_HEADING = re.compile(r"^pismo przewodnie\b", re.IGNORECASE)
OTHER_FILING = re.compile(
    r"^(?:odpowiedz na odwolanie|(?:zgloszenie )?przystapieni[ea] do postepowania|"
    r"(?:odwolanie|wypowiedzenie|cofniecie) pelnomocnictwa|pelnomocnictwo (?:zostalo )?(?:odwolane|cofniete|wypowiedziane|wygaslo)|"
    r"spis zalacznikow)\b"
)
APPEAL_TITLE = re.compile(r"^odwolanie (?:do|w sprawie|wobec|od|na)\b")
KIO = r"(?:krajow\w* izb\w* odwolawcz\w*|kio)\b"
APPEAL_CUES = (
    rf"^(?:do (?:prezesa )?|prezes ){KIO}",
    r"^(?:niniejszym )?(?:wnosze|wnosimy|skladam|skladamy) (?:niniejsze )?odwolanie\b",
    r"^(?:odwolujacy|(?:wykonawca|podmiot) wnoszacy odwolanie)\b",
    r"^(?:zarzut(?:y| nr \d+)?|zadania|wnioski odwolujacego|zaskarzona czynnosc)\b",
)
GRANT_TITLE = re.compile(
    r"(?:pelnomocnictwo|upowaznienie|umocowanie)(?: (?:procesowe|szczegolne|ogolne|rodzajowe))?"
    r"(?: (?:do reprezentowania|do udzialu|dla)\b[^.!?]*)?"
)
GRANT_CUES = (
    r"^(?:niniejszym )?(?:udzielam(?:y)?|upowazniam(?:y)?|ustanawiam(?:y)?)\b",
    r"^(?:mocodawc[ay]|udzielajacy pelnomocnictwa)\b",
    r"(?:do reprezentowania|w charakterze pelnomocnika|^pelnomocni(?:k|cy)\b)",
)
PAYMENT_TITLE = re.compile(
    r"^(?:(?:bankowe|elektroniczne) )?(?:potwierdzenie|dowod|zaswiadczenie|poswiadczenie) (?:bankowe )?(?:(?:o )?"
    r"(?:wykonani[aeu]|realizacji|zaksiegowania|zrealizowania) )?(?:polecenia )?(?:transakcji|platnosci|operacji|przelewu)\b"
    r"|^(?:szczegoly|dane) (?:zrealizowan|wykonan|zaksiegowan)(?:ej|ego) (?:transakcji|platnosci|operacji|przelewu)\b"
)


# Bank exports can name the document, the action and its state in separate fields.
BANK_DOCUMENT = re.compile(
    r"^(?:(?:bankow[eya]|elektroniczn[eya]) )?(?:potwierdzenie|dowod|poswiadczenie|zaswiadczenie|"
    r"wydruk|szczegoly|dokument|informacja|raport|zestawienie)\b"
)
PAYMENT_SUBJECT = re.compile(r"\b(?:przelew|platnos|operacj|transakcj|obciazeni|dyspozycj)\w*")
ATTESTS_PAYMENT = re.compile(r"\b(?:potwierdzeni|dowod|poswiadczeni|zaswiadczeni|zaksiegowan|zrealizowan|wykonan)\w*")
ORDER_OR_COPY = re.compile(
    r"\b(?:kopi|archiw|wniosk|pros[bz]|przyjeci|zlozeni|anulowan|odrzucon|zaplanowan|"
    r"niezrealizowan|niewykonan|dyspozycji do realizacji|do akceptacji)\w*"
)

CURRENCY_VALUE = re.compile(
    rf"(?im)^(?:(?:kwota|wartosc|suma)\b[^:\n]{{0,35}}:[ \t]*)?"
    rf"(?:pln[ \t]*{bank_transfer.MONEY}|{bank_transfer.MONEY}[ \t]*(?:pln|zl|eur))[ \t]*$"
)


SETTLEMENT_CAPTION = re.compile(
    r"(?:potwierdzenie|poswiadczenie|dowod|zaswiadczenie) (?:wykonania|realizacji|zaksiegowania|rozliczenia)"
)


SINGLE_PAYMENT_SUBJECT = re.compile(
    r"(?:(?:karta|wydruk|wyciag|metryka|zapis|szczegoly|dane|dokument) )?"
    r"(?:przelew(?:u)?|transakcj[ai]|operacj[ai]|platnosc[i]?)"
    r"(?: (?:bankow|krajow|zagraniczn|wychodzac|przychodzac)(?:a|y|ej|ego))?"
)


def _settlement_caption(line: str, following: str) -> bool:
    """A form can name the payment and attest its execution in separate heading segments."""
    parts = re.split(r"\s+[-–—/|·]\s+", line)
    if len(parts) == 1:
        parts.append(following)
    return len(parts) == 2 and any(
        SETTLEMENT_CAPTION.fullmatch(caption) and SINGLE_PAYMENT_SUBJECT.fullmatch(subject)
        for caption, subject in (parts, reversed(parts))
    )


DETAIL_CAPTION = re.compile(
    r"(?:szczegoly|dane) (operacji|transakcji|zlecenia|dyspozycji)(?: (?:bankowej|platniczej|przelewu))?"
)


def _payment_card(first: str, folded: str, amount: float | None, day: str | None) -> bool:
    """Require account, value and settlement evidence even when no exact receipt title matches."""
    lines = folded.splitlines()
    titles = []
    split_caption = False
    detail = None
    bank_header = False
    for index, line in enumerate(lines[:10]):
        if re.search(r"\b(?:zalacznik|w zalaczeniu|przedkladam|przesylam)\w*", line):
            return False
        if ORDER_OR_COPY.search(line) or re.match(r"^(?:dyspozycja|polecenie|zlecenie)\b", line):
            return False
        # Only the opening heading (optionally following its issuer) owns this assertion.
        if index == 0 or (index == 1 and bank_header):
            split_caption |= _settlement_caption(line, lines[index + 1] if index + 1 < len(lines) else "")
            detail = DETAIL_CAPTION.fullmatch(line) or detail
        bank_header |= bool(re.match(r"^(?:[a-z-]+ ){0,2}bank\b", line))
        if (BANK_DOCUMENT.match(line) or PAYMENT_SUBJECT.match(line)) and PAYMENT_SUBJECT.search(line):
            if re.search(r"\b(?:zlecenia|zlecenie|przyjet\w*|rejestracji|autoryzacji|do realizacji)\b", line):
                return False
            titles.append(line)
    if not (titles or bank_header or split_caption or detail) or not (
        amount is not None or CURRENCY_VALUE.search(folded)
    ):
        return False
    accounts = bank_transfer.ANCILLARY_ACCOUNT.sub("", bank_transfer.normalize_account_spacing(first))
    numbers = {account_identity("".join(m[1].split())) for m in account_matches(accounts)}
    if len(numbers) != 2:
        return False
    roles = bank_transfer.printed_accounts(accounts)
    if None in roles.values():
        return False
    references = len(bank_transfer.REFERENCE_RE.findall(first))
    identified_detail = detail and references == 1 and (PRINTED_AMOUNT.search(first) or CURRENCY_VALUE.search(folded))
    if split_caption or identified_detail:
        # An unfamiliar caption can also appear on a list of transactions. Require
        # one dated amount and explicitly bound, distinct debit and credit cells.
        amount_count = len(bank_transfer.AMOUNT_RE.findall(first)) + len(bank_transfer.WHOLE_AMOUNT_RE.findall(first))
        # A requested order date can precede settlement. Require its actual booking or execution.
        date_suffixes = ("księgowania", "obciążenia", "wykonania")
        if not detail or detail[1] in {"operacji", "transakcji"}:
            date_suffixes += ("operacji", "transakcji", "realizacji", "płatności")
        return bool(
            amount is not None
            and day is not None
            and any(
                match[1].casefold().endswith(date_suffixes) and to_iso(match[2]) == day
                for match in bank_transfer.OPERATION_DATE_RE.finditer(first)
            )
            and amount_count == 1
            and references <= 1
            and set(roles) == {"sender", "recipient"}
            and account_identity(roles["sender"]) != account_identity(roles["recipient"])
        )
    booked = any(
        m[1].casefold().endswith(("księgowania", "wykonania", "obciążenia")) and to_iso(m[2])
        for m in bank_transfer.OPERATION_DATE_RE.finditer(first)
    )
    attestation = any(ATTESTS_PAYMENT.search(title) for title in titles)
    sender, recipient = bank_transfer._accounts(accounts)
    reference = bool(bank_transfer.REFERENCE_RE.search(first))
    bound_pair = bool(sender and recipient and account_identity(sender) != account_identity(recipient))
    if not titles:
        return bool(bank_header and booked and reference and bound_pair)
    corroboration = sum(
        (
            day is not None,
            reference,
            bound_pair,
        )
    )
    return (attestation or booked) and corroboration >= 1


def _cue_score(text: str, cues: tuple[str, ...]) -> int:
    return sum(bool(re.search(cue, text, re.MULTILINE)) for cue in cues)


# A "stan" field can also describe a balance or another bank-specific state.
# It vetoes a confirmation only when the value actually describes a pending or failed payment.
NONEXECUTED_STATE = re.compile(
    r"^(?:przelew\s+)?(?:oczekuj|czeka|planowan|przyjęt\w* do realizacji|do wysłania|odrzucon|odmow[ay]\b|"
    r"odmówion|anulowan|wstrzyman|zaplanowan|częściowo (?:wykon|zrealiz|zaksięgow|rozlicz|zapłac)|"
    r"nie\s*(?:został[ao]?\s+)?(?:wykon|opłac|zrealiz|zaksięgow|zatwierdz|rozlicz)|"
    r"w (?:realizacji|toku|przygotowaniu)|do (?:realizacji|akceptacji|autoryzacji|podpisu))",
    re.IGNORECASE,
)


REFUSAL_REASON = re.compile(r"^(?:powód|przyczyna) (?:odrzucenia|odmowy|anulowania)\s*:\s*(.+)$", re.IGNORECASE)


PAYMENT_OUTCOME = re.compile(rf"^wynik (?:{bank_transfer.STATUS_SCOPE})\s*:\s*(.+)$", re.IGNORECASE)


DETACHED_STATUS = re.compile(rf"(status|stan)(?: (?:{bank_transfer.STATUS_SCOPE}|wykonania))?[ :.|–-]*", re.IGNORECASE)


CLOCK_TIME = r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?"
STATUS_TIMESTAMP = re.compile(
    rf"[ ,]+(?:(?P<day>{bank_transfer.DATE})(?:[ T,]+{CLOCK_TIME})?|{CLOCK_TIME})$", re.IGNORECASE
)


def _completed_state(value: str) -> bool:
    value = value.rstrip(" .")
    stamp = STATUS_TIMESTAMP.search(value)
    if stamp and (not stamp["day"] or to_iso(stamp["day"])):
        value = value[: stamp.start()]
    return bool(EXECUTED.fullmatch(value) or COMPLETED_STATUS.fullmatch(value))


def _status_lines(lines: list[str]):
    """A detached status cell has the same meaning as its inline form."""
    for index, line in enumerate(lines):
        label = DETACHED_STATUS.fullmatch(line)
        if label:
            if index + 1 < len(lines):
                value = lines[index + 1].strip(" |–-")
                state_word = EXECUTED.match(value) or COMPLETED_STATUS.match(value) or NONEXECUTED_STATE.match(value)
                if (
                    value
                    and (state_word or not bank_transfer.BOUNDARY_RE.match(value))
                    and not DETACHED_STATUS.fullmatch(value)
                ):
                    yield f"{label[1]}: {value}"
            continue
        yield line


def _nonexecuted(lines: list[str]) -> bool:
    for line in _status_lines(lines):
        reason = REFUSAL_REASON.match(line)
        if reason:
            value = reason[1].strip(" .:–—-").casefold()
            if re.search(r"\w", value) and value not in {"brak", "nie dotyczy", "n/d", "n/dot", "n/a", "nd"}:
                return True
        outcome = PAYMENT_OUTCOME.match(line)
        if outcome and NONEXECUTED_STATE.match(outcome[1]):
            return True
        state = bank_transfer.STATUS.match(line)
        if state is None:
            continue
        value = state["value"].rstrip(" .")
        if _completed_state(value):
            continue
        if (
            line.casefold().startswith("status")
            or NONEXECUTED_STATE.match(value)
            or EXECUTED.match(value)
            or COMPLETED_STATUS.match(value)
        ):
            return True
    return False


def _debit_printout(text: str) -> bool:
    if bank_transfer.description_debit(text):
        return bool(re.search(r"(?im)^data księgowania\b", text))
    return bool(
        re.search(r"(?im)^typ transakcji[ :]+przelew z rachunku\b", text)
        and re.search(rf"(?im)^kwota[ :]+[−-]{bank_transfer.MONEY}", text)
    )


def _executed_order_printout(text: str) -> bool:
    if not re.search(r"(?im)^przelew(?: [\w-]+){0,3} szczegóły przelewu przyjętego do realizacji[ \t]*$", text):
        return False
    # An order's requested day may be in the future. Require the separate
    # execution field and a print timestamp on or after that execution day.
    executed = re.findall(rf"(?im)^data realizacji przelewu[ :]+({DATE})[ \t]*$", text)
    printed = re.findall(rf"(?im)^data wydruku[ :]+({DATE})(?=\s|$)", text)
    if len(executed) != 1 or len(printed) != 1:
        return False
    day, issued = to_iso(executed[0]), to_iso(printed[0])
    return bool(day and issued and day <= issued)


def incomplete_booking_scan(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines()]
    if _nonexecuted(lines) or any(UNRELATED_HEADING.match(line) for line in lines):
        return False
    confirmation = any(
        CONFIRMATION_HEADING.match(line.lstrip(" |/–-")) or DEBIT_DETAILS.match(line) or booking_heading(line, ocr=True)
        for line in lines
    )
    order = ORDER_TYPE.search(text) or INTERLEAVED_DEBIT.search(text)
    if order and re.search(r"(?im)^dane zleceniodawcy\b", text):
        return True
    return bool(
        (confirmation or order or _debit_printout(text) or bank_transfer.executed_letter(text))
        and (BANK_FIELDS.search(text) or bank_transfer.completed_value_block(text))
    )


def resembles_appeal_heading(page: str) -> bool:
    return any(
        Levenshtein.distance("".join(row.split()).upper(), "ODWOŁANIE", score_cutoff=1) <= 1
        for row in page.splitlines()
    )


def _confirms_execution(line: str) -> bool:
    state = bank_transfer.STATUS.match(line)
    if state:
        return _completed_state(state["value"])
    return bool(EXECUTION_ATTESTATION.fullmatch(line))


def routing_evidence(first_page: str) -> tuple[set[str], bool]:
    """Return eligible classes and whether the payment details independently confirm a transfer."""
    lines = [line.strip() for line in first_page.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if COVER_HEADING.match(line):
            return set(), False
        if UNRELATED_HEADING.match(line) or OTHER_FILING.match(line.casefold().translate(POLISH_FOLD)):
            if REQUEST_REFERENCE.fullmatch(line) and any(CONFIRMATION_HEADING.match(h) for h in lines[:i]):
                continue
            return set(), False
    labels = set()
    headings = ["".join(line.upper().split()) for line in lines]
    if "ODWOŁANIE" in headings or FILING.search(first_page):
        labels.add("appeal")
    if any(re.match(r"^PE[ŁL]NOMOCNICTWO(?:$|DO|DLA|PROCESOWE|SZCZEG[ÓO]LNE|NR)", h) for h in headings) or re.search(
        r"\b(?:udzielam(?:y)?\s+(?:niniejszego\s+)?pełnomocnictwa|upoważniam(?:y)?\b)", first_page, re.IGNORECASE
    ):
        labels.add("power_of_attorney")
    if _nonexecuted(lines) or bank_transfer.payment_denied(first_page):
        return labels, False
    # The entries below an enclosure introduction describe other documents, even when
    # OCR puts the introduction, a list marker and the receipt heading on separate lines.
    cutoff = next(
        (i for i, line in enumerate(lines) if ATTACHMENT_REFERENCE.search(line) and not PAYMENT_COPY.fullmatch(line)),
        len(lines),
    )
    lines = lines[:cutoff]
    receipt = "\n".join(lines)
    account = next(account_matches(receipt), None)
    own_lines = [
        line
        for i, line in enumerate(lines)
        if not LIST_MARKER.match(line) and not (i and LIST_MARKER.fullmatch(lines[i - 1]))
    ]
    bank_heading = any(
        CONFIRMATION_HEADING.match(line)
        or booking_heading(line, ocr=True)
        or PAYMENT_DETAILS.match(line)
        # An exported bank table can place the heading beside an account or bank label.
        or (account and PAYMENT_DETAILS.search(line))
        for line in own_lines
    )
    numbered_field = any(
        BANK_FIELDS.search(line) and re.search(r"\d", " ".join(lines[i : i + 2])) for i, line in enumerate(lines)
    )
    if not (numbered_field or account):
        return labels, False
    if not bank_heading:
        # A transaction-type title or a copy needs independent evidence that this payment was executed.
        record_heading = any(PAYMENT_COPY.fullmatch(line) or PAYMENT_RECORD.fullmatch(line) for line in own_lines)
        if not record_heading or not any(_confirms_execution(line) for line in own_lines):
            return labels, False
    sender = re.search(r"(?im)^(?:nadawca|zleceniodawca|płatnik)\s*:[ \t]*\S", receipt)
    recipient = re.search(r"(?im)^(?:odbiorca|beneficjent)\s*:[ \t]*\S", receipt)
    has_amount = PRINTED_AMOUNT.search(receipt) or bank_transfer.transaction_values(receipt)[0] is not None
    confirmed_transfer = bool(has_amount and (account or (sender and recipient)))
    if bank_heading or confirmed_transfer:
        labels.add("bank_transfer")
    return labels, confirmed_transfer


def _one_settled_record(page: str, lines: list[str]) -> bool:
    """A stacked list must actually describe a single settled transaction."""
    references = bank_transfer.REFERENCE_RE.findall(page)
    titles = [line for line in lines if bank_transfer.TITLE_LABEL_RE.match(line)]
    if len(references) > 1 or len(titles) > 1 or not (references or titles):
        return False
    amounts = [line for line in lines if bank_transfer.ledger_amount_line(line)]
    if len(amounts) != 1 or not (PRINTED_AMOUNT.search(amounts[0]) or CURRENCY_VALUE.fullmatch(amounts[0])):
        return False
    amount, day = bank_transfer.transaction_values(page)
    posted = any(
        m[1].casefold().endswith(("księgowania", "obciążenia")) and to_iso(m[2])
        for m in bank_transfer.OPERATION_DATE_RE.finditer(page)
    )
    return bool(
        amount is not None
        and (day or references)
        and (posted or any(_confirms_execution(line) for line in _status_lines(lines)))
    )


def _settled_history(page: str, accounts: AccountEvidence | None, *, require_selection: bool = False) -> bool:
    lines = [line.strip() for line in page.splitlines()]
    if any(
        COVER_HEADING.match(line)
        or (UNRELATED_HEADING.match(line) and not bank_transfer.HISTORY_HEADING.match(line))
        or OTHER_FILING.match(line.casefold().translate(POLISH_FOLD))
        for line in lines
    ) or ATTACHMENT_REFERENCE.search(page):
        return False
    section = bank_transfer.selected_history_section(page)
    if section:
        page = section
        lines = [line.strip() for line in page.splitlines()]
        accounts = account_evidence(page) if accounts is not None else None
    elif (
        require_selection
        or bank_transfer.SELECTED_HISTORY.search(page)
        or any(line.casefold().startswith("wyciąg") for line in lines)
    ):
        # A statement needs an explicit selection. Conflicting selections are ambiguous.
        return False
    if _nonexecuted(lines) or bank_transfer.payment_denied(page):
        return False
    # If an actual row table is ambiguous, its surrounding labels cannot single out a record.
    if not bank_transfer.history_debit_fields(page) and (
        bank_transfer.LEDGER_HEADER.search(page) or not _one_settled_record(page, lines)
    ):
        return False
    if accounts is None:
        roles = bank_transfer.printed_accounts(bank_transfer.normalize_account_spacing(page))
        sender, recipient = roles.get("sender"), roles.get("recipient")
    else:
        sender, recipient = accounts.sender, accounts.recipient
    return bool(sender and recipient and account_identity(sender) != account_identity(recipient))


def classify(pages: list[str], *, ocr_accounts: AccountEvidence | None = None) -> str | None:
    if not pages:
        return None
    head = "\n".join(pages[:2])
    folded = head.casefold().translate(POLISH_FOLD)
    scan_filing = ocr_accounts is not None and FILING.search(pages[0])
    transfer_heading = False
    register_heading = False
    for index, page in enumerate(pages[:2]):
        for row in page.splitlines():
            line = row.strip()
            heading = re.sub(r"\s", "", line).upper()
            cue = line.casefold().translate(POLISH_FOLD)
            if COVER_HEADING.match(line):
                # An enclosed filing needs its own evidence. Account details on an
                # enclosure do not turn a cover letter into a payment receipt.
                enclosed = classify(pages[1:2]) if index == 0 and len(pages) > 1 else None
                return enclosed if enclosed in {"appeal", "power_of_attorney"} else None
            if bank_transfer.HISTORY_HEADING.match(line):
                # Validate the selection and any competing entries across the supplied pages.
                history = _settled_history("\n".join(pages), ocr_accounts, require_selection=len(pages) > 1)
                return "bank_transfer" if history else None
            if UNRELATED_HEADING.match(line) or OTHER_FILING.match(cue):
                return None
            if re.match(r"^(?:rejestr|wykaz|spis|ewidencja)\b", line, re.IGNORECASE):
                register_heading = True
            if not register_heading and APPEAL_TITLE.match(cue) and _cue_score(folded, APPEAL_CUES) >= 2:
                return "appeal"
            if not register_heading and GRANT_TITLE.fullmatch(cue) and _cue_score(folded, GRANT_CUES) >= 2:
                return "power_of_attorney"
            if index == 0 and scan_filing:
                # Flecks at the edge of a scanned title can appear as bullets or quotes.
                if heading.strip("*•|.,„”'—–-") == "ODWOŁANIE":
                    return "appeal"
                if (
                    not register_heading
                    and Levenshtein.distance(heading, "ODWOŁANIE", score_cutoff=1) == 1
                    and re.search(r"(?im)^odwo[łl]uj[ąa]cy\s*:", page)
                    and re.search(r"(?im)^zamawiaj[ąa]cy\s*:", page)
                    and re.search(r"krajowej izby odwoławczej", page, re.IGNORECASE)
                ):
                    return "appeal"
            if Levenshtein.distance(heading, "ODWOŁANIE", score_cutoff=1) <= 1:
                party = re.search(r"odwo[łl]uj[ąa]c", head, re.IGNORECASE)
                labelled_parties = re.search(r"(?im)^(?:wykonawca|odwo[łl]uj[ąa]cy)\s*[:(]", head) and re.search(
                    r"(?im)^zamawiaj[ąa]cy\s*[:(]", head
                )
                # A grammatical word one edit away can be a register heading.
                clear_heading = heading.translate(str.maketrans({"0": "O", "L": "Ł"})) == "ODWOŁANIE"
                if clear_heading and (labelled_parties or FILING.search(head) or (heading == "ODWOŁANIE" and party)):
                    return "appeal"
                # With an ambiguous heading, require party fields and the filer's own declaration.
                if (
                    not register_heading
                    and labelled_parties
                    and re.search(r"(?im)^\s*(?:wnoszę|wnosimy|składam|składamy)\s+(?:niniejsze\s+)?odwołanie\b", head)
                ):
                    return "appeal"
            if re.fullmatch(r"PEŁNOMOCNICTWO(?:PROCESOWE|SZCZEGÓLNE)?(?:NR[.:]?[0-9][A-Z0-9./-]*)?", heading):
                return "power_of_attorney"
            if re.fullmatch(
                r"PEŁNOMOCNICTWONR[.:]?[A-Z]{1,8}[-/]\d[\dA-Z./-]*", heading
            ) and power_of_attorney.GRANT.search(head):
                return "power_of_attorney"
            if (
                CONFIRMATION_HEADING.match(line)
                or PAYMENT_TITLE.match(cue)
                or DEBIT_DETAILS.match(line)
                or (line.casefold() == "przelew z rachunku szczegóły transakcji" and _debit_printout(page))
                or booking_heading(line, ocr=index == 0 and ocr_accounts is not None)
            ):
                transfer_heading = True
                break
        if transfer_heading:
            break
    if not transfer_heading and not register_heading:
        # Without a title, require the addressee and the filer's own declaration.
        if all(re.search(p, folded, re.MULTILINE) for p in APPEAL_CUES[:2]) and _cue_score(folded, APPEAL_CUES) >= 3:
            return "appeal"
        if _cue_score(folded, GRANT_CUES) == len(GRANT_CUES):
            return "power_of_attorney"
    if not transfer_heading and power_of_attorney.has_notarial_grant(head):
        return "power_of_attorney"

    first = pages[0]
    lines = [line.strip() for line in first.splitlines()]
    if _nonexecuted(lines) or bank_transfer.payment_denied(first):
        return None
    attestation = bank_transfer.attested_payment_fields(first)
    if (
        not register_heading
        and {"kwota", "data_operacji", "z_rachunku", "na_rachunek"} <= attestation.keys()
        and account_identity(attestation["z_rachunku"]) != account_identity(attestation["na_rachunek"])
        and not ATTACHMENT_REFERENCE.search(first)
    ):
        return "bank_transfer"
    if not transfer_heading and not register_heading and bank_transfer.LEDGER_HEADER.search(first):
        return "bank_transfer" if len(pages) == 1 and _settled_history(first, ocr_accounts) else None
    letter = bank_transfer.executed_letter(first)
    debit = ocr_accounts is not None and _debit_printout(first)
    dated_order = ocr_accounts is not None and _executed_order_printout(first)
    attested = any(_confirms_execution(line) for line in _status_lines(lines))
    conventional = (
        transfer_heading or debit or letter or dated_order or attested or any(EXECUTED.match(line) for line in lines)
    )
    folded_first = first.casefold().translate(POLISH_FOLD)
    if not conventional and not PAYMENT_SUBJECT.search(folded_first) and "bank" not in folded_first:
        return None
    amount, day = bank_transfer.transaction_values(first)
    if not conventional or (amount is None and day is None):
        return "bank_transfer" if not register_heading and _payment_card(first, folded_first, amount, day) else None

    # A receipt can print NRB/IBAN in groups other than the domestic 2+6x4.
    first = bank_transfer.normalize_account_spacing(first)
    if ocr_accounts is None:
        sender, recipient = bank_transfer._accounts(first)
    else:
        sender, recipient = ocr_accounts.sender, ocr_accounts.recipient
    bound_pair = bool(sender and recipient and account_identity(sender) != account_identity(recipient))
    # A posted transaction with no confirmation title must bind both accounts,
    # its amount, and at least one independent ledger date or transaction ID.
    ledger_score = sum((amount is not None, day is not None, bool(bank_transfer.REFERENCE_RE.search(first))))
    if attested and bound_pair and amount is not None and ledger_score >= 2:
        return "bank_transfer"
    # Classic confirmations sometimes give an unlabelled pair. Preserve their routing
    # while keeping explicit commission/refund/archive accounts out of that pair.
    payment_fields = bank_transfer.ANCILLARY_ACCOUNT.sub("", first)
    candidates = {account_identity("".join(number[1].split())) for number in account_matches(payment_fields)}
    known_party = (sender or recipient) and len(
        {account_identity("".join(number[1].split())) for number in account_matches(first)}
    ) >= 2
    if (
        (bound_pair or known_party or len(candidates) >= 2)
        and (transfer_heading or "przelew" in first.casefold())
        and (transfer_heading or any(EXECUTED.match(line) for line in lines))
    ):
        return "bank_transfer"
    if amount is None or day is None:
        return None
    if bound_pair:
        return "bank_transfer"
    if transfer_heading:
        if (
            ocr_accounts is not None
            and {"sender", "recipient"} <= ocr_accounts.declared
            and re.search(rf"(?im)^{bank_transfer.REFERENCE_LABEL}[ \t]*[:.]", first)
            and any(account and valid_account(account) for account in (sender, recipient))
        ):
            return "bank_transfer"
        if (
            ocr_accounts is not None
            and bank_transfer.completed_value_block(first)
            and ocr_accounts.distinct_numbers == 2
        ):
            return "bank_transfer"
        if ocr_accounts is not None and bank_transfer.posted_party_debit(first):
            return "bank_transfer"
        if ocr_accounts is not None and ocr_accounts.masked_pair:
            return "bank_transfer"
        visible = sender or recipient
        if (
            bool(sender) != bool(recipient)
            and visible
            and valid_account(visible)
            and bank_transfer.partial_account_mask(first, "recipient" if sender else "sender")
        ):
            return "bank_transfer"
    return None
