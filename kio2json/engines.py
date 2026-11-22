"""Run configured text-to-dict extractors and fill gaps from later engines."""

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
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


def merged_path(fields: dict, candidate: dict, merged: dict, path: str) -> str | None:
    """Where a later reading's value sits right after its merge, or None if its row was not merged.

    This follows `fill`: the record keeps its own rows in order, takes a whole list it lacked, and joins a later
    row to its one row with the same identity when that identity is also unique in the later reading.
    """
    field, source, target, parts = None, candidate, merged, []
    for key, index in trace.PATH_PARTS.findall(path):
        if not index:
            field = (fields if field is None else field.fields or {}).get(key)
            if field is None or not isinstance(source, dict) or not isinstance(target, dict):
                return None
            source, target = source.get(key), target.get(key)
            parts.append(f".{key}" if parts else key)
            continue
        row = int(index)
        if not isinstance(source, list) or not isinstance(target, list) or row >= len(source):
            return None
        if target is source:  # The merge took this reading's whole list.
            final = row
        elif field.match_by and (name := identity(source[row], field.match_by)) is not None:
            matches = [i for i, other in enumerate(target) if identity(other, field.match_by) == name]
            if [identity(other, field.match_by) for other in source].count(name) != 1 or len(matches) != 1:
                return None
            final = matches[0]
        else:
            return None
        source, target, field = source[row], target[final], field.items
        parts.append(f"[{final}]")
    return "".join(parts)


def settle_checks(fields: dict, values: dict, rejected: list[dict], held: dict) -> None:
    """Return held "warn" readings to fields still empty, then report the failed checks the record still shows.

    Kept values are checked again where the merged record holds them. A rejected value, already placed at its
    merged path, is reported while that place stays empty.
    """
    for path, (candidate, value) in held.items():
        if trace.lookup(values, path, missing=MISSING) is None:
            trace.assign(values, path, value)
            # The trace finds the producing engine through its candidate.
            trace.assign(candidate, path, value)
    kept = [warning for warning in check_record(fields, deepcopy(values)) if warning["action"] == "warn"]
    for warning in rejected:
        final = trace.lookup(values, warning["field"], missing=MISSING)
        if (final is None or final is MISSING) and warning not in kept:
            kept.append(warning)
    trace.note_warnings(kept)


def missing_core_fields(record: dict) -> bool:
    """A missing party or transaction detail warrants a second reading of a rule-routed document.

    The organizer's record shape decides which details count; any other record has none.
    """
    if "Odwolujacy" in record:
        return not all(any(row.get("nazwa") for row in record[key]) for key in ("Odwolujacy", "Zamawiajacy"))
    if "mocodawca" in record:
        principals = (row["data"] for row in record["mocodawca"])
        return not (
            any(party.get("nazwa") or party.get("imie_nazwisko") for party in principals)
            and any(person.get("imie_nazwisko") for person in record["pelnomocnicy"])
        )
    if "przelew_bankowy" in record:
        payment = record["przelew_bankowy"]
        return any(payment[key] is None for key in ("kwota", "data_operacji", "tytul", "na_rachunek", "z_rachunku"))
    return False


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
    rejected = []
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
        if engine == "llm" and check_core_fields and not missing_core_fields(values):
            if definition.checked:
                settle_checks(definition.fields, values, rejected, held)
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
        # A failed check empties the value, so a later engine can fill it. A value the field keeps
        # ("warn") is held aside too, and returns only if no later engine supplies a valid one.
        found = check_record(definition.fields, candidate) if definition.checked else []
        for warning in found:
            path = warning["field"]
            # A list row can be merged by identity into another position, so only values outside lists are held.
            if warning["action"] == "warn" and "[" not in path:
                # The first engine's reading is the one returned if no engine passes the check.
                held.setdefault(path, (candidate, warning["value"]))
                trace.assign(candidate, path, None)
        if values is None:
            merged = candidate
        else:
            merged = {
                k: fill(f, values.get(k), candidate.get(k), fill_empty=fill_empty) for k, f in definition.fields.items()
            }
        # Merged rows keep their place, so a rejected value is located in the record right after its merge.
        for warning in found:
            path = (
                warning["field"]
                if values is None
                else merged_path(definition.fields, candidate, merged, warning["field"])
            )
            if warning["action"] == "null" and path is not None:
                rejected.append(warning | {"field": path})
        values = merged
    if definition.profile.mode == "RL" and definition.id == "power_of_attorney":
        for principal in values["mocodawca"]:
            owner = principal["data"]
            if owner["typ"] == "osoba_prawna":
                # A person's name belongs to an individual grantor or signer.
                owner["imie_nazwisko"] = None
    if definition.checked:
        settle_checks(definition.fields, values, rejected, held)
    if definition.engines == ["python"]:
        # Python extractors own their normalization and serialization order.
        return values
    if definition.profile.mode == "V":
        from .model_validation import validate_fields

        values = validate_fields(definition, values)
    return definition.output_model.model_validate(values).model_dump(by_alias=True)
