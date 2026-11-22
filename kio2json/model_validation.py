"""Format and checksum filters for already grounded model fields (mode V)."""

import re
from decimal import Decimal

from stdnum.pl import nip, pesel, regon

from .accounts import valid_account
from .class_config import DocumentClass, OutputField
from .output_schema import normalize

NOTICE_FORMATS = {
    "numer_bzp": re.compile(r"[0-9]{4}/BZP[0-9]{8}(?:/[0-9]{2})?"),
    "numer_ted": re.compile(r"[0-9]{6}-[0-9]{4}"),
}

IDENTIFIER_CHECKS = {
    "account_number": valid_account,
    "nip": nip.is_valid,
    "pesel": pesel.is_valid,
    "regon": regon.is_valid,
}


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
        if (check := IDENTIFIER_CHECKS.get(field.normalizer)) and not check(value):
            return None
    if appeal and key in NOTICE_FORMATS and not NOTICE_FORMATS[key].fullmatch(value):
        return None
    return value


def validate_fields(definition: DocumentClass, values: dict) -> dict:
    """Copy the grounded record and replace invalid leaves with null without generating new values."""
    return {
        k: _validate(definition.fields[k], k, value, appeal=definition.id == "appeal") for k, value in values.items()
    }
