"""Format and checksum filters for already grounded model fields (mode V)."""

import re
from datetime import date
from decimal import Decimal

from .class_config import DocumentClass, OutputField
from .output_schema import normalize

NOTICE_FORMATS = {
    "numer_bzp": re.compile(r"[0-9]{4}/BZP[0-9]{8}(?:/[0-9]{2})?"),
    "numer_ted": re.compile(r"[0-9]{6}-[0-9]{4}"),
}


def _weighted(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True))


def _valid_identifier(kind: str, number: str) -> bool:
    # The common normalizers have already checked digit counts and the canonical representation.
    if kind == "account_number":
        # Compute the two Polish IBAN check digits with PL (25, 21) followed by two zeros.
        return int(number[:2]) == 98 - int(number[2:] + "252100") % 97
    if kind == "nip":
        return _weighted(number[:-1], (6, 5, 7, 2, 3, 4, 5, 6, 7)) % 11 == int(number[-1])
    if kind == "regon":
        parent_check = _weighted(number[:8], (8, 9, 2, 3, 4, 5, 6, 7)) % 11 % 10
        if len(number) == 9 or parent_check != int(number[8]):
            return parent_check == int(number[8])
        local_check = _weighted(number[:-1], (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)) % 11 % 10
        return local_check == int(number[-1])
    if kind == "pesel":
        encoded_month = int(number[2:4])
        centuries = (1900, 2000, 2100, 2200, 1800)
        try:
            date(centuries[encoded_month // 20] + int(number[:2]), encoded_month % 20, int(number[4:6]))
        except ValueError:
            return False
        return -_weighted(number[:-1], (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)) % 10 == int(number[-1])
    return True  # KRS has no check digit.


def _validate(field: OutputField, key: str, value, *, appeal: bool):
    if value is None:
        return None
    if field.type == "list":
        return [_validate(field.items, key, item, appeal=appeal) for item in value]
    if field.type == "object":
        return {k: _validate(field.fields[k], k, entry, appeal=appeal) for k, entry in value.items()}
    if field.normalizer == "money":
        if type(value) not in (int, float):
            return None
        amount = Decimal(str(value))
        return value if amount.is_finite() and amount.as_tuple().exponent >= -2 else None
    if field.normalizer:
        if normalize(field.normalizer, value) != value:
            return None
        if field.normalizer != "iso_date" and not _valid_identifier(field.normalizer, value):
            return None
    if appeal and key in NOTICE_FORMATS and not NOTICE_FORMATS[key].fullmatch(value):
        return None
    return value


def validate_fields(definition: DocumentClass, values: dict) -> dict:
    """Copy the grounded record and replace invalid leaves with null without generating new values."""
    return {
        k: _validate(definition.fields[k], k, value, appeal=definition.id == "appeal") for k, value in values.items()
    }
