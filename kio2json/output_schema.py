"""Build Pydantic output models from class fields, and normalize extracted scalar values."""

import re

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, create_model

from .bank_transfer import ACCOUNT_RE, MONEY
from .class_config import OutputField
from .common import DATE_RE, registry_ids, to_iso

SCALARS = {"string": str, "number": float, "integer": int, "boolean": bool}
ADAPTERS = {name: TypeAdapter(kind, config=ConfigDict(allow_inf_nan=False)) for name, kind in SCALARS.items()}


def normalize(name: str, raw):
    if raw is None:
        return None
    value = str(raw).strip()
    if name == "iso_date":
        return to_iso(value) if DATE_RE.fullmatch(value) else None
    if name == "account_number":
        match = ACCOUNT_RE.fullmatch(value.upper())
        return re.sub(r"\s", "", match[1]) if match else None
    if name == "pesel":
        return value if re.fullmatch(r"[0-9]{11}", value) else None
    if name == "money":
        if type(raw) in (float, int):
            return raw
        if re.fullmatch(r"[+-]?\d+(?:[.,]\d{1,2})?", value):
            return value.replace(",", ".")
        if re.fullmatch(MONEY, value):
            return re.sub(r"[ .\u00a0]", "", value[:-3]) + "." + value[-2:]
        return None
    return registry_ids(f"{name.upper()}: {value}")[name]


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
