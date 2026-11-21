"""Field-level F1 for Odwołania2json outputs.

The organizer has not published how F1 is computed (UNCONFIRMED). Working definition:
- Every JSON is flattened to (path, value) pairs over its leaves; list indices become `[]`, so lists are compared
  as multisets and item order does not matter.
- `null` leaves count as pairs: predicting null where gold has null is a hit, a value where gold has null is a
  false positive plus a false negative. `micro_f1_non_null` reports the variant that ignores gold-null fields.
- Values are normalised before comparison: whitespace and case; numbers by value (`200 == 200.0`); identifier
  fields (KRS, NIP, REGON, PESEL) as digits only. Account numbers retain every printed character except whitespace.
  Types and formats are not normalised away:
  `"3" != 3`, `2026-03-21 != 20260321`, `123456-2026 != 1234562026`.
- A zero-byte gold file labels a negative. Its expected prediction is `{}` with an optional trailing
  line ending. Every predicted pair on a negative is a false positive.
- A missing or unreadable prediction scores as all gold pairs missed.
- Micro F1 pools counts across documents. Macro document F1 averages documents with any gold or predicted leaf.
- Macro class F1 averages pooled F1 for each of the three target classes with reference or predicted fields.
  A misrouted document misses the reference class's fields and adds false positives to the predicted class.
- Macro field F1 averages the pooled F1 of each distinct reference or predicted leaf path.
- All matches are made within a document. An empty average is undefined (JSON null).
"""

import json
import re
import stat
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CLASSES = {
    "odwolanie": "OdwolanieKIO",
    "pelnomocnictwo": "mocodawca",
    "przelew": "przelew_bankowy",
}
NEGATIVE = "negatywny"


def reject_json_constant(token: str):
    raise ValueError("invalid JSON number")


def read_object(path: Path, *, reference: bool = False) -> tuple[dict, bool]:
    """Return the parsed object and whether the text matches the negative output convention."""
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("expected a regular JSON file")
    try:
        text = path.read_text(encoding="utf-8", newline="")
        if reference and text == "":
            return {}, False
        data = json.loads(text, parse_constant=reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError("a selected reference is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("a selected reference must be a JSON object")  # noqa: TRY004 - invalid file contents
    return data, text in ("{}", "{}\n", "{}\r\n")


def load_reference(path: Path) -> dict:
    data, _ = read_object(path, reference=True)
    return data


def load_prediction(path: Path) -> tuple[dict | None, bool]:
    """An unreadable or malformed prediction is incomplete and misses the reference leaves."""
    try:
        return read_object(path)
    except (OSError, ValueError):
        return None, False


def doc_class(data: dict | None) -> str | None:
    if data is None:
        return None
    if not data:
        return NEGATIVE
    for name, key in CLASSES.items():
        if key in data:
            return name
    return "unknown"


# Identifier fields: compared as digits only, whatever the type (the schema example has PESEL as a number,
# the gold files as a string) and however the document spaces or dashes them.
IDENTIFIER_KEYS = {"krs", "nip", "regon", "pesel"}
ACCOUNT_KEYS = {"na_rachunek", "z_rachunku"}


def normalise(value: object, key: str = "") -> str:
    """Comparable form of a leaf. Types stay distinct (`"3"` != `3`), and formats such as ISO dates or TED numbers
    are kept as written; only whitespace and case are ignored, plus spacing inside identifier fields."""
    if value is None:
        return "null"
    if key in ACCOUNT_KEYS and isinstance(value, str):
        return "account:" + "".join(value.split())
    if key in IDENTIFIER_KEYS and isinstance(value, int | str) and re.fullmatch(r"[\d\s-]+", str(value).strip()):
        return "id:" + re.sub(r"[\s-]", "", str(value))
    if isinstance(value, bool):
        return f"bool:{value}".lower()
    if isinstance(value, int):
        return f"num:{value}"
    if isinstance(value, float):
        return "num:" + f"{value:.2f}".rstrip("0").rstrip(".")
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def flatten(data: object, path: str = "") -> Counter:
    pairs: Counter = Counter()
    if isinstance(data, dict):
        for key, value in data.items():
            pairs += flatten(value, f"{path}.{key}" if path else key)
    elif isinstance(data, list):
        for item in data:
            pairs += flatten(item, f"{path}[]")
    else:
        pairs[(path, normalise(data, path.rsplit(".", 1)[-1].removesuffix("[]")))] += 1
    return pairs


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: "Counts") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def f1(self) -> float | None:
        denom = 2 * self.tp + self.fp + self.fn
        return None if denom == 0 else 2 * self.tp / denom


def compare(
    pred: dict | None, gold: dict, skip_gold_nulls: bool = False, *, by_field: dict[str, Counts] | None = None
) -> Counts:
    gold_pairs = flatten(gold)
    pred_pairs = flatten(pred) if pred is not None else Counter()
    if skip_gold_nulls:
        null_paths = {p for p, v in gold_pairs if v == "null"}
        gold_pairs = Counter({k: n for k, n in gold_pairs.items() if k[0] not in null_paths})
        pred_pairs = Counter({k: n for k, n in pred_pairs.items() if k[0] not in null_paths})
    hits = gold_pairs & pred_pairs
    if by_field is not None:
        for pair in gold_pairs.keys() | pred_pairs.keys():
            counts = by_field.setdefault(pair[0], Counts())
            counts.add(Counts(hits[pair], pred_pairs[pair] - hits[pair], gold_pairs[pair] - hits[pair]))
    tp = hits.total()
    return Counts(tp, sum(pred_pairs.values()) - tp, sum(gold_pairs.values()) - tp)


@dataclass
class DocResult:
    case: str
    file: str
    gold_class: str
    pred_class: str | None
    counts: Counts
    counts_non_null: Counts
    empty_output: bool
    errors: list[str] = field(default_factory=list)
    by_field: dict[str, Counts] = field(default_factory=dict)


def score_doc(case: str, file: str, pred_path: Path, gold: dict) -> DocResult:
    pred, empty_output = load_prediction(pred_path)
    errors = [] if pred is not None else ["missing or invalid JSON"]
    by_field = {}
    return DocResult(
        case,
        file,
        doc_class(gold) or NEGATIVE,
        doc_class(pred),
        compare(pred, gold, by_field=by_field),
        compare(pred, gold, skip_gold_nulls=True),
        empty_output,
        errors,
        by_field,
    )


def summarise(docs: list[DocResult]) -> dict:
    total, non_null = Counts(), Counts()
    per_class = {name: Counts() for name in CLASSES}
    per_field: defaultdict[str, Counts] = defaultdict(Counts)
    for d in docs:
        total.add(d.counts)
        non_null.add(d.counts_non_null)
        if d.gold_class == d.pred_class:
            if d.gold_class in per_class:
                per_class[d.gold_class].add(d.counts)
        else:
            if d.gold_class in per_class:
                per_class[d.gold_class].fn += d.counts.tp + d.counts.fn
            if d.pred_class in per_class:
                per_class[d.pred_class].fp += d.counts.tp + d.counts.fp
        for path, counts in d.by_field.items():
            per_field[path].add(counts)
    negatives = [d for d in docs if d.gold_class == NEGATIVE]
    positives = [d for d in docs if d.gold_class != NEGATIVE]
    document_scores = [score for d in docs if (score := d.counts.f1) is not None]
    class_scores = {name: score for name, counts in per_class.items() if (score := counts.f1) is not None}
    field_scores = [score for counts in per_field.values() if (score := counts.f1) is not None]
    return {
        "micro_f1": total.f1,
        "macro_f1_documents": _ratio(sum(document_scores), len(document_scores)),
        "macro_f1_classes": _ratio(sum(class_scores.values()), len(class_scores)),
        "macro_f1_class_count": len(class_scores),
        "macro_f1_fields": _ratio(sum(field_scores), len(field_scores)),
        "micro_f1_non_null": non_null.f1,
        "per_class_f1": class_scores,
        "classification_accuracy": _ratio(sum(d.pred_class == d.gold_class for d in positives), len(positives)),
        "negatives_empty": _ratio(sum(d.empty_output for d in negatives), len(negatives)),
        "outputs_complete": _ratio(sum(not d.errors for d in docs), len(docs)),
        "counts": {"tp": total.tp, "fp": total.fp, "fn": total.fn},
    }


def _ratio(hits: float, n: int) -> float | None:
    return None if n == 0 else hits / n
