"""Run configured text-to-dict extractors and fill gaps from later engines."""

from collections import Counter
from collections.abc import Callable
from functools import partial

from .class_config import DocumentClass, OutputField
from .model_pages import AlternateOCR
from .output_schema import scalar_value


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


def extract(
    definition: DocumentClass,
    text: str,
    *,
    model=None,
    ocr_python: Callable[[], dict] | None = None,
    alternate: AlternateOCR | None = None,
    model_text: str | None = None,
) -> dict:
    values = None
    fill_empty = definition.profile.mode in ("RL", "LR")
    for engine in definition.engines:
        if values is not None and not any(
            gaps(f, values.get(k), fill_empty=fill_empty) for k, f in definition.fields.items()
        ):
            break
        if engine == "python" and ocr_python is not None:
            candidate = ocr_python()
        else:
            source = model_text if engine == "llm" and model_text is not None else text
            candidate = bind_engine(engine, definition, model, alternate=alternate)(source)
        if values is None:
            values = candidate
        else:
            values = {
                k: fill(f, values.get(k), candidate.get(k), fill_empty=fill_empty) for k, f in definition.fields.items()
            }
    if definition.engines == ["python"]:
        # Python extractors own their normalization and serialization order.
        return values
    if definition.profile.mode == "V":
        from .model_validation import validate_fields

        values = validate_fields(definition, values)
    return definition.output_model.model_validate(values).model_dump(by_alias=True)
