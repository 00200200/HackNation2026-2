"""Named field checks that a class TOML declares, applied to extracted records."""

from datetime import date
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from stdnum import iban
from stdnum.pl import nip, pesel, regon

if TYPE_CHECKING:
    from .class_config import OutputField

CHECKSUMS = {"nip": nip.is_valid, "regon": regon.is_valid, "pesel": pesel.is_valid}


def iban_valid(value: str) -> bool:
    """A residue check also accepts 00 for 97, so compare the printed check digits as well."""
    account = "".join(str(value).split())
    if not account[:2].isalpha():
        account = "PL" + account
    return iban.is_valid(account) and account[2:4] == iban.calc_check_digits(account)


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def fits(self, field_type: str) -> bool:
        return field_type == "string"


class Checksum(Check):
    """Polish registry numbers and IBAN accounts; a bare 26-digit account is read as Polish."""

    name: Literal["nip", "regon", "pesel", "iban"]

    def accepts(self, value) -> bool:
        return iban_valid(value) if self.name == "iban" else CHECKSUMS[self.name](value)


class DateRange(Check):
    """Inclusive bounds for an ISO date produced by the iso_date normalizer."""

    name: Literal["date_range"]
    min: date | None = None
    max: date | None = None

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.min is None and self.max is None:
            raise ValueError("date_range needs min, max or both")
        if self.min and self.max and self.min > self.max:
            raise ValueError("date_range min is after max")
        return self

    def accepts(self, value) -> bool:
        try:
            day = date.fromisoformat(value)
        except (TypeError, ValueError):
            return False
        return (self.min is None or self.min <= day) and (self.max is None or day <= self.max)


class OneOf(Check):
    """The value must equal one of the listed values of the field's own type."""

    name: Literal["one_of"]
    values: list[bool | int | float | str] = Field(min_length=1)

    def fits(self, field_type: str) -> bool:
        kinds = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}[field_type]
        # bool is an int subtype, so a boolean list must not satisfy a numeric field.
        return all(isinstance(v, kinds) and (field_type == "boolean") == isinstance(v, bool) for v in self.values)

    def accepts(self, value) -> bool:
        return value in self.values


def _named(value):
    return {"name": value} if isinstance(value, str) else value


Validator = Annotated[Checksum | DateRange | OneOf, Field(discriminator="name"), BeforeValidator(_named)]


def declares_checks(field: "OutputField") -> bool:
    children = [*(field.fields or {}).values(), *([field.items] if field.items else [])]
    return bool(field.validators) or any(declares_checks(child) for child in children)


def check_record(fields: dict[str, "OutputField"], record: dict) -> list[dict]:
    """Apply each field's checks in place and return one warning per failed value."""
    warnings = []
    for key, field in fields.items():
        if key in record:
            record[key] = _checked(field, record[key], key, warnings)
    return warnings


def _checked(field: "OutputField", value, path: str, warnings: list[dict]):
    if value is None:
        return None
    if field.type == "object":
        for key, child in field.fields.items():
            if key in value:
                value[key] = _checked(child, value[key], f"{path}.{key}", warnings)
        return value
    if field.type == "list":
        return [_checked(field.items, item, f"{path}[{i}]", warnings) for i, item in enumerate(value)]
    for check in field.validators:
        if not check.accepts(value):
            warnings.append({"field": path, "check": check.name, "value": value, "action": field.on_invalid})
            return None if field.on_invalid == "null" else value
    return value
