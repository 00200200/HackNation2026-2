"""Build Pydantic output models from class fields, and normalize extracted scalar values."""

import re

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, create_model

from .bank_transfer import ACCOUNT_RE
from .class_config import OutputField
from .common import DATE, MONTHS, to_iso

SCALARS = {"string": str, "number": float, "integer": int, "boolean": bool}
ADAPTERS = {name: TypeAdapter(kind, config=ConfigDict(allow_inf_nan=False)) for name, kind in SCALARS.items()}


# An evidence span and a labelled capture use the same grammar and normalization.
ENGLISH_MONTHS = "January February March April May June July August September October November December".lower().split()
MONTH_WORD = re.compile(r"\b(?:" + "|".join(ENGLISH_MONTHS) + r")\b", re.IGNORECASE)
# Consume the complete numeric token before validating grouping, so a malformed
# amount cannot be split into a smaller valid amount during a citation search.
NUMBER_TOKEN = re.compile(
    r"(?<![\w.,+−-])(?:[+−-][ \u00a0\u202f]*)?"
    r"\d++(?:[ \u00a0\u202f]\d++|\.\d{3}(?!\d))*+(?:[.,]\d++)*+(?:[eE][+-]?\d++)?(?!\w)"
)
MONEY_FORMAT = re.compile(
    r"(?:(?P<sign>[+−-])[ \u00a0\u202f]*)?(?P<whole>\d{1,3}(?:[ .\u00a0\u202f]\d{3})+|\d+)(?:[.,](?P<fraction>\d{1,2}))?"
)
SPANS = {
    "iso_date": re.compile(rf"(?<!\w)(?:{DATE}|\d{{1,2}}\s+{MONTH_WORD.pattern}\s+\d{{4}})(?!\w)", re.IGNORECASE),
    "money": NUMBER_TOKEN,
    "account_number": re.compile(rf"(?<!\w){ACCOUNT_RE.pattern}(?!\w)", re.IGNORECASE),
    "nip": re.compile(r"(?<![\w-])(?<!\d[ ])(?:PL\s?)?(\d(?:[ \-]?\d){9})(?!\w|[ -]\d)", re.IGNORECASE),
    "krs": re.compile(r"(?<!\w)(?:nr\s*)?(\d{10})(?!\w)", re.IGNORECASE),
    "regon": re.compile(r"(?<!\w)(\d{14}|\d{9})(?!\w)"),
    "pesel": re.compile(r"(?<!\w)([0-9]{11})(?!\w)"),
}


def normalize(name: str, raw):
    if raw is None:
        return None
    if name == "money":
        if type(raw) in (float, int):
            return raw
        match = MONEY_FORMAT.fullmatch(str(raw).strip())
        if not match:
            return None
        whole = re.sub(r"[.\s]", "", match["whole"])
        sign = "-" if match["sign"] in ("-", "−") else ""
        return f"{sign}{whole}.{match['fraction'] or '0'}"
    match = SPANS[name].fullmatch(str(raw).strip())
    if not match:
        return None
    if name == "iso_date":
        date_text = MONTH_WORD.sub(lambda m: MONTHS[ENGLISH_MONTHS.index(m[0].lower())], match[0])
        return to_iso(date_text)
    return re.sub(r"[\s-]", "", match[1])


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
        return ADAPTERS[field.type].validate_python(value)
    except ValidationError:
        return None


def cited_value(field: OutputField, raw, quote: str, text: str):
    """Require an entire source token inside one verbatim occurrence of this citation."""
    value = scalar_value(field, raw)
    quote_start = text.find(quote)
    if value is None or not quote.strip() or quote_start == -1:
        return None
    numeric = field.type in ("integer", "number")
    if field.normalizer:
        pattern = SPANS[field.normalizer]
    elif numeric:
        pattern = NUMBER_TOKEN
    else:
        words = str(value).split()
        if not words:
            return None
        copied = r"\s+".join(re.escape(word) for word in words)
        pattern = re.compile(rf"(?<!\w){copied}(?!\w)", re.IGNORECASE)

    for span in pattern.finditer(text):
        # Source matches are ordered. Advance past occurrences too short to
        # contain this match, including when the same quote occurs more than once.
        if span.end() > quote_start + len(quote):
            quote_start = text.find(quote, span.end() - len(quote))
            if quote_start == -1:
                break
        # Identifier grammars capture the number separately from optional PL or nr prefixes.
        value_start = span.start(1) if span.lastindex else span.start()
        if value_start < quote_start:
            continue
        if field.normalizer:
            supported = scalar_value(field, span[0])
        elif numeric:
            supported = scalar_value(field, span[0].replace(",", ".").replace("−", "-"))
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
