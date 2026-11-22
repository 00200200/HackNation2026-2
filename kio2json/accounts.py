"""Recognize printed IBANs and domestic Polish NRBs without inventing a prefix."""

import re
from collections import defaultdict

from stdnum import iban, numdb

# stdnum publishes the SWIFT registry notation for each country's BBAN.
_BBANS = {code: info["bban"] for _, code, _, info, _ in numdb.get("iban").prefixes}
IBAN_COUNTRIES = frozenset(_BBANS)
_COUNTRY = "(?i:" + "|".join(_BBANS) + ")"
_PREFIX_AT_END = re.compile(r"(?<!\w)([A-Za-z])([\s.-]*)([A-Za-z])[\s.-]+\Z")
_WORD_AT_END = re.compile(r"\s+(?=[A-Za-z]{2,}\Z)[A-Za-z]*[a-z][A-Za-z]*\Z")


def account_pattern(digits: str, letters: str, mixed: str) -> re.Pattern:
    countries = defaultdict(list)
    for code, bban in _BBANS.items():
        # "4!a6!n8!n" describes four letters followed by fourteen digits.
        kinds = "".join(kind * int(size) for size, kind in re.findall(r"(\d+)!([nac])", bban))
        countries[kinds].append(code)
    classes = {"n": digits, "a": letters, "c": mixed}
    branches = []
    for kinds, codes in countries.items():
        # The PDF text layer can insert a gap between any two characters,
        # including the letters of the country code or BBAN.
        body = "".join(r"\s*" + classes[kind] for kind in "nn" + kinds)
        country = "(?i:" + "|".join(code[0] + r"\s*" + code[1] for code in codes) + ")"
        branches.append(country + body)
    bare = r"\s*".join([digits] * 26)
    branches.append(rf"(?<!\b{_COUNTRY}\s){bare}")
    # A short numeric group on the same row is a continuation unless it
    # starts an entire second account in a neighbouring table column.
    end = rf"(?![\w/?|*\-])(?![^\S\n]+(?!{bare}(?!\w))[0-9]{{1,4}}(?=\s|$))"
    return re.compile(r"(?<![\w/?|*\-])((?-i:" + "|".join(branches) + "))" + end)


ACCOUNT_RE = account_pattern("[0-9]", "[A-Za-z]", "[A-Za-z0-9]")
OCR_ACCOUNT_RE = account_pattern("[0-9?]", "[A-Za-z?]", "[A-Za-z0-9?]")


def has_detached_country(before: str) -> bool:
    """Recognize a detached IBAN prefix before a potential domestic suffix."""
    prefix = _PREFIX_AT_END.search(before)
    if not prefix:
        return False
    code = prefix[1] + prefix[3]
    return bool(prefix[2]) or code.upper() in IBAN_COUNTRIES


def complete_account_match(match: re.Match, group: int = 1) -> bool:
    raw = match[group]
    if raw[0].isdigit() and has_detached_country(match.string[: match.start(group)]):
        return False
    # A word following a short free-form BBAN may belong to the next field.
    # The checksum distinguishes that reading from a printed all-letter group.
    return not _WORD_AT_END.search(raw) or valid_account(raw)


def account_matches(text: str):
    return (m for m in ACCOUNT_RE.finditer(text) if complete_account_match(m))


def normalize_account(raw: str) -> str | None:
    """Normalize a complete, structurally plausible account, including its printed prefix."""
    compact = "".join(raw.split())
    return compact if ACCOUNT_RE.fullmatch(compact) else None


def valid_account(raw: str) -> bool:
    account = normalize_account(raw)
    if not account:
        return False
    number = "PL" + account if account.isdigit() else account.upper()
    return number[2:4] == iban.calc_check_digits(number)


def account_identity(account: str) -> str:
    """Compare two printed forms of the same account, including a Polish NRB."""
    return account.upper().removeprefix("PL")
