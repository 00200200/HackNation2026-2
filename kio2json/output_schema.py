"""Build Pydantic output models from class fields, and normalize extracted scalar values."""

import re
from decimal import Decimal, InvalidOperation

from babel.numbers import NumberFormatError, list_currencies, parse_decimal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, create_model

from .class_config import OutputField
from .common import DATE, MONTHS, to_iso

SCALARS = {"string": str, "number": float, "integer": int, "boolean": bool}
ADAPTERS = {name: TypeAdapter(kind, config=ConfigDict(allow_inf_nan=False)) for name, kind in SCALARS.items()}


# An evidence span and a labelled capture use the same grammar and normalization.
ENGLISH_MONTHS = "January February March April May June July August September October November December".lower().split()
MONTH_WORD = re.compile(r"\b(?:" + "|".join(ENGLISH_MONTHS) + r")\b", re.IGNORECASE)
MONTH_NAMES = "|".join([*ENGLISH_MONTHS, *MONTHS])
DATE_FORMAT = re.compile(rf"(?:{DATE}|\d{{1,2}}\s+(?:{MONTH_NAMES})\s+\d{{4}})", re.IGNORECASE)
SPACE = r"[^\S\r\n]"
GROUP_MARKS = ".,_'’ \t\xa0\u2009\u202f"
# An amount with cents followed by a full date is a common two-column PDF row.
COLUMN_BREAK = rf"(?<=[.,]\d{{2}})(?={SPACE}++{DATE_FORMAT.pattern}(?!\w))"
JOINED_DIGITS = rf"(?!{COLUMN_BREAK})[{re.escape(GROUP_MARKS)}-]++"
# Consume a whole run before checking its shape. A fixed-width search would
# rediscover a valid-looking suffix inside an overlong or malformed token.
DATE_TOKEN = re.compile(rf"\d++(?:(?:{JOINED_DIGITS}|\s+(?:{MONTH_NAMES})\s+)\d++)*+", re.IGNORECASE)
ID_TOKEN = re.compile(r"(?:(?<!\w)(?P<prefix>PL|nr)[^\S\r\n]*)?(?P<digits>[0-9]++(?:[\s-]++[0-9]++)*+)", re.IGNORECASE)
ID_LENGTHS = {"nip": {10}, "krs": {10}, "regon": {9, 14}, "pesel": {11}, "account_number": {26}}

CURRENCY_CODES = "|".join(sorted(list_currencies()))
CURRENCY = rf"(?:{CURRENCY_CODES}|zł|[$¢£¤¥\u20a0-\u20cf])"
NUMBER_RUN = rf"\d++(?:{JOINED_DIGITS}\d++)*+(?:[eE][+-]?\d++)?"
NUMBER_TOKEN = re.compile(
    rf"(?P<outer_sign>[+−-]{SPACE}*)?(?:(?<!\w){CURRENCY}{SPACE}*)?"
    rf"(?P<sign>[+−-]{SPACE}*)?(?P<digits>{NUMBER_RUN})(?:{SPACE}*{CURRENCY}(?!\w))?",
    re.IGNORECASE,
)
GROUP_TO_COMMA = str.maketrans(dict.fromkeys(GROUP_MARKS, ","))


def money_value(match: re.Match[str]) -> Decimal | None:
    if match["outer_sign"] and match["sign"]:
        return None
    digits = match["digits"]
    # A final dot/comma with one or two digits denotes cents. Babel checks
    # thousands grouping strictly after mapping the printed marks to one locale.
    fraction = re.search(r"[.,](\d{1,2})$", digits)
    whole = digits[: fraction.start()] if fraction else digits
    canonical = whole.translate(GROUP_TO_COMMA)
    if fraction:
        if fraction[0][0] in whole:
            return None
        canonical += "." + fraction[1]
    if not re.fullmatch(r"[0-9,]+(?:\.[0-9]{1,2})?", canonical):
        return None
    try:
        amount = parse_decimal(canonical, locale="en_US", strict=True)
    except (NumberFormatError, InvalidOperation):
        return None
    sign = (match["outer_sign"] or match["sign"] or "").strip()
    return amount.copy_negate() if sign in ("−", "-") else amount


def normalize(name: str, raw):
    if raw is None:
        return None
    token = str(raw).strip()
    if name == "money":
        if type(raw) in (float, int):
            return raw
        match = NUMBER_TOKEN.fullmatch(token)
        return money_value(match) if match else None
    if name == "iso_date":
        if not DATE_FORMAT.fullmatch(token):
            return None
        return to_iso(MONTH_WORD.sub(lambda m: MONTHS[ENGLISH_MONTHS.index(m[0].lower())], token))
    match = ID_TOKEN.fullmatch(token)
    if not match:
        return None
    prefix = (match["prefix"] or "").lower()
    if prefix and prefix != {"account_number": "pl", "nip": "pl", "krs": "nr"}.get(name):
        return None
    if not re.fullmatch(r"[0-9]+(?:(?:\s+|-)[0-9]+)*", match["digits"]):
        return None
    digits = re.sub(r"[\s-]", "", match["digits"])
    return digits if len(digits) in ID_LENGTHS[name] else None


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Cited[T](SchemaModel):
    value: T
    quote: str = Field(min_length=1, description="Exact, contiguous passage supporting this value and its role.")


def scalar_value(field: OutputField, raw):
    value = normalize(field.normalizer, raw) if field.normalizer else raw
    if value is None:
        return None
    try:
        result = ADAPTERS[field.type].validate_python(value)
    except ValidationError:
        return None
    if isinstance(value, Decimal) and Decimal(str(result)) != value:
        return None
    return result


def cited_value(field: OutputField, raw, quote: str, text: str):
    """Require an entire source token inside one verbatim occurrence of this citation."""
    value = scalar_value(field, raw)
    if value is None or not quote.strip() or quote not in text:
        return None
    numeric = field.type in ("integer", "number")
    if numeric:
        pattern = NUMBER_TOKEN
    elif field.normalizer == "iso_date":
        pattern = DATE_TOKEN
    elif field.normalizer:
        pattern = ID_TOKEN
    else:
        words = str(value).split()
        if not words:
            return None
        copied = r"\s+".join(re.escape(word) for word in words)
        # Keep punctuation between word characters inside references and mailboxes.
        connector = r"[.+@/'’\-]"
        pattern = re.compile(rf"(?<!\w)(?<!\w{connector}){copied}(?!\w|{connector}\w)", re.IGNORECASE)

    for span in pattern.finditer(text):
        start, end = span.span()
        # Check boundaries *after* consuming the run, so a rejected candidate
        # cannot cause a new match to begin at its first grouping separator.
        before, after = text[max(0, start - 1) : start], text[end : end + 1]
        if before.isalnum() or after.isalnum() or "_" in (before, after):
            continue
        if numeric and before in {".", ",", "+", "-", "−"}:
            continue
        if pattern is ID_TOKEN:
            start = span.start("digits")
        elif numeric:
            start = next(span.start(k) for k in ("outer_sign", "sign", "digits") if span[k])
            end = span.end("digits")
        # Only quote occurrences containing this complete value can support it.
        if text.find(quote, max(0, end - len(quote)), start + len(quote)) == -1:
            continue
        if field.normalizer == "money":
            if money_value(span) == Decimal(str(value)):
                return value
            continue
        if field.normalizer:
            supported = normalize(field.normalizer, span[0])
        elif numeric:
            sign = (span["outer_sign"] or span["sign"] or "").strip().replace("−", "-")
            supported = scalar_value(field, sign + span["digits"].replace(",", "."))
        else:
            return value
        if supported == value:
            return value
    return None


def field_type(field: OutputField, name: str, cited: bool, allow_abstention: bool):
    if field.type == "object":
        result = record_model(field.fields, name, cited=cited, allow_abstention=allow_abstention)
    elif field.type == "list":
        result = list[field_type(field.items, name + "Item", cited, allow_abstention)]
    else:
        result = SCALARS[field.type]
        if cited:
            result = Cited[result]
    if field.nullable or (allow_abstention and field.type in SCALARS):
        result = result | None
    return result


def record_model(
    fields: dict[str, OutputField], name: str, *, cited: bool = False, allow_abstention: bool = False
) -> type[BaseModel]:
    # Aliases preserve external JSON keys, including punctuation and names reserved by BaseModel.
    members = {
        f"field_{i}": (
            field_type(field, f"{name}_{i}", cited, allow_abstention),
            Field(alias=key, description=field.instruction),
        )
        for i, (key, field) in enumerate(fields.items())
    }
    return create_model(name, __base__=SchemaModel, **members)
