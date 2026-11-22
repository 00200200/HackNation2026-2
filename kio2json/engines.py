"""Run configured text-to-dict extractors and fill gaps from later engines."""

from collections import Counter
from collections.abc import Callable
from functools import partial

from . import trace
from .class_config import DocumentClass, OutputField
from .model_pages import AlternateOCR
from .output_schema import scalar_value
from .validators import check_record

MISSING = object()


def labelled(field: OutputField, text: str, *, item: bool = False):
    """A list pattern captures each item; child labels search only inside its captured text."""
    if field.type == "list":
        if field.pattern is None:
            return None if field.nullable else []
        return [labelled(field.items, m[1], item=True) for m in field.pattern.finditer(text) if m[1] is not None]
    if field.pattern:
        match = field.pattern.search(text)
        if not match or match[1] is None:
            return None
        text = match[1]
    if field.type == "object":
        return {key: labelled(child, text) for key, child in field.fields.items()}
    if field.pattern or item:
        return scalar_value(field, text.strip() or None)
    return None


def identity(record, path: str):
    for key in path.split("."):
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return record


def gaps(field: OutputField, value, *, fill_empty: bool = False) -> bool:
    if value is None or (fill_empty and field.type == "list" and not value):
        return True
    if field.type == "object":
        return any(gaps(child, value.get(key), fill_empty=fill_empty) for key, child in field.fields.items())
    if field.match_by:
        return any(
            identity(row, field.match_by) is not None and gaps(field.items, row, fill_empty=fill_empty) for row in value
        )
    return False


def fill(field: OutputField, primary, fallback, *, fill_empty: bool = False):
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    if fill_empty and field.type == "list" and not primary:
        return fallback
    if field.type == "object":
        return {k: fill(f, primary.get(k), fallback.get(k), fill_empty=fill_empty) for k, f in field.fields.items()}
    if field.match_by:
        # Match unique identities on both sides. Positional merging can assign a signer to the wrong principal.
        primary_ids = [identity(row, field.match_by) for row in primary]
        counts = Counter(primary_ids)
        index = {}
        for row in fallback:
            key = identity(row, field.match_by)
            index[key] = row if key not in index else None
        return [
            fill(field.items, row, index.get(key), fill_empty=fill_empty)
            if key is not None and counts[key] == 1
            else row
            for row, key in zip(primary, primary_ids, strict=True)
        ]
    return primary


def bind_engine(
    name: str, definition: DocumentClass, model=None, *, alternate: AlternateOCR | None = None
) -> Callable[[str], dict]:
    if name == "python":
        return definition.extractor
    if name == "labelled_fields":
        return lambda text: {key: labelled(field, text) for key, field in definition.fields.items()}
    from .llm import extract_llm

    if alternate:
        return partial(extract_llm, definition, model=model, alternate_pages=alternate.read_all())
    return partial(extract_llm, definition, model=model)


def missing_core_fields(class_id: str, record: dict) -> bool:
    """A missing party or transaction detail warrants a second reading of a rule-routed document."""
    if class_id == "appeal":
        return not all(any(row.get("nazwa") for row in record[key]) for key in ("Odwolujacy", "Zamawiajacy"))
    if class_id == "power_of_attorney":
        principals = (row["data"] for row in record["mocodawca"])
        return not (
            any(party.get("nazwa") or party.get("imie_nazwisko") for party in principals)
            and any(person.get("imie_nazwisko") for person in record["pelnomocnicy"])
        )
    payment = record["przelew_bankowy"]
    return any(payment[key] is None for key in ("kwota", "data_operacji", "tytul", "na_rachunek", "z_rachunku"))


def extract(
    definition: DocumentClass,
    text: str,
    *,
    model=None,
    ocr_python: Callable[[], dict] | None = None,
    alternate: AlternateOCR | None = None,
    model_text: str | None = None,
    first_page: str | None = None,
    check_core_fields: bool = False,
) -> dict:
    values = None
    failed = []
    held = {}
    trace.note("declared_fields", definition.fields)
    fill_empty = definition.profile.mode in ("RL", "LR")
    for engine in definition.engines:
        if values is not None and not any(
            gaps(f, values.get(k), fill_empty=fill_empty) for k, f in definition.fields.items()
        ):
            break
        source = model_text if engine == "llm" and model_text is not None else text
        if (
            engine == "llm"
            and definition.id == "appeal"
            and definition.profile.keyed
            and definition.profile.mode == "RL"
        ):
            from .charge_model import ChargeSettings, focus_charge

            charge_focus = ChargeSettings().charge_focus
            if charge_focus:
                focus_charge(values["OdwolanieKIO"], source, model=model)
                if charge_focus == "only":
                    break
        if engine == "llm" and check_core_fields and not missing_core_fields(definition.id, values):
            return values
        if engine == "python" and ocr_python is not None:
            candidate = ocr_python()
        else:
            candidate = bind_engine(engine, definition, model, alternate=alternate)(source)
        if engine == "python":
            # A field added to a Python class's TOML, with a label pattern, is read after the extractor.
            for key, field in definition.fields.items():
                if key not in candidate and field.pattern is not None:
                    candidate[key] = labelled(field, text)
        if engine == "python" and definition.profile.keyed and definition.profile.mode == "RL" and first_page:
            from .llm import OutputSettings

            if definition.id in {"appeal", "bank_transfer"} and OutputSettings().output in {"schema", "spans"}:
                from .doubtful_values import reassess

                reassess(definition.id, candidate, first_page, model=model)
        trace.note_candidate(engine, candidate)
        if definition.checked:
            # A failed check empties the value, so a later engine can fill it. A value the field keeps
            # ("warn") is held aside too, and returns only if no later engine supplies a valid one.
            found = check_record(definition.fields, candidate)
            failed += found
            for warning in found:
                if warning["action"] == "warn":
                    held.setdefault(warning["field"], warning["value"])
                    trace.assign(candidate, warning["field"], None)
        if values is None:
            values = candidate
        else:
            values = {
                k: fill(f, values.get(k), candidate.get(k), fill_empty=fill_empty) for k, f in definition.fields.items()
            }
    if definition.profile.mode == "RL" and definition.id == "power_of_attorney":
        for principal in values["mocodawca"]:
            owner = principal["data"]
            if owner["typ"] == "osoba_prawna":
                # A person's name belongs to an individual grantor or signer.
                owner["imie_nazwisko"] = None
    for path, value in held.items():
        if trace.lookup(values, path, missing=MISSING) is None:
            trace.assign(values, path, value)
    if failed:
        # Report a failed check while the final record still holds that reading, or keeps the emptied place.
        kept = []
        for warning in failed:
            final = trace.lookup(values, warning["field"], missing=MISSING)
            emptied = warning["action"] == "null" and final is None
            if (emptied or final == warning["value"]) and warning not in kept:
                kept.append(warning)
        trace.note_warnings(kept)
    if definition.engines == ["python"]:
        # Python extractors own their normalization and serialization order.
        return values
    if definition.profile.mode == "V":
        from .model_validation import validate_fields

        values = validate_fields(definition, values)
    return definition.output_model.model_validate(values).model_dump(by_alias=True)
