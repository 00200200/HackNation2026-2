"""Field-level F1 for Odwołania2json outputs.

The organizer has not published how F1 is computed (UNCONFIRMED). Working definition:
- Every JSON is flattened to (path, value) pairs over its leaves; list indices become `[]`, so lists are compared
  as multisets and item order does not matter.
- `null` leaves count as pairs: predicting null where gold has null is a hit, a value where gold has null is a
  false positive plus a false negative. `micro_f1_non_null` reports the variant that ignores gold-null fields.
- Values are normalised (whitespace, case, number formatting) before comparison.
- A negative document has an empty gold file: every predicted pair is a false positive.
- A missing or unreadable prediction scores as all gold pairs missed.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

CLASSES = {
    "odwolanie": "OdwolanieKIO",
    "pelnomocnictwo": "mocodawca",
    "przelew": "przelew_bankowy",
}
NEGATIVE = "negatywny"


def load_json(path: Path) -> dict | None:
    """Empty file -> {}; missing or invalid file -> None."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def doc_class(data: dict | None) -> str | None:
    if data is None:
        return None
    if not data:
        return NEGATIVE
    for name, key in CLASSES.items():
        if key in data:
            return name
    return "unknown"


def normalise(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return f"{float(value):.2f}".rstrip("0").rstrip(".")
    text = re.sub(r"\s+", " ", str(value)).strip().casefold()
    if re.fullmatch(r"[\d\s-]+", text):  # account numbers, NIP, PESEL written with spaces or dashes
        text = re.sub(r"[\s-]", "", text)
    return text


def flatten(data: object, path: str = "") -> Counter:
    pairs: Counter = Counter()
    if isinstance(data, dict):
        for key, value in data.items():
            pairs += flatten(value, f"{path}.{key}" if path else key)
    elif isinstance(data, list):
        for item in data:
            pairs += flatten(item, f"{path}[]")
    else:
        pairs[(path, normalise(data))] += 1
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


def compare(pred: dict | None, gold: dict, skip_gold_nulls: bool = False) -> Counts:
    gold_pairs = flatten(gold)
    pred_pairs = flatten(pred) if pred is not None else Counter()
    if skip_gold_nulls:
        null_paths = {p for p, v in gold_pairs if v == "null"}
        gold_pairs = Counter({k: n for k, n in gold_pairs.items() if k[0] not in null_paths})
        pred_pairs = Counter({k: n for k, n in pred_pairs.items() if k[0] not in null_paths})
    tp = sum((gold_pairs & pred_pairs).values())
    return Counts(tp, sum(pred_pairs.values()) - tp, sum(gold_pairs.values()) - tp)


@dataclass
class DocResult:
    case: str
    file: str
    gold_class: str
    pred_class: str | None
    counts: Counts
    counts_non_null: Counts
    errors: list[str] = field(default_factory=list)


def score_doc(case: str, file: str, pred_path: Path, gold: dict) -> DocResult:
    pred = load_json(pred_path)
    errors = [] if pred is not None else ["missing or invalid JSON"]
    return DocResult(
        case,
        file,
        doc_class(gold) or NEGATIVE,
        doc_class(pred),
        compare(pred, gold),
        compare(pred, gold, skip_gold_nulls=True),
        errors,
    )


def summarise(docs: list[DocResult]) -> dict:
    total, non_null = Counts(), Counts()
    per_class: dict[str, Counts] = {}
    for d in docs:
        total.add(d.counts)
        non_null.add(d.counts_non_null)
        per_class.setdefault(d.gold_class, Counts()).add(d.counts)
    negatives = [d for d in docs if d.gold_class == NEGATIVE]
    positives = [d for d in docs if d.gold_class != NEGATIVE]
    return {
        "micro_f1": total.f1,
        "micro_f1_non_null": non_null.f1,
        "per_class_f1": {name: c.f1 for name, c in sorted(per_class.items()) if name != NEGATIVE},
        "classification_accuracy": _ratio(sum(d.pred_class == d.gold_class for d in positives), len(positives)),
        "negatives_empty": _ratio(sum(d.pred_class == NEGATIVE for d in negatives), len(negatives)),
        "outputs_complete": _ratio(sum(not d.errors for d in docs), len(docs)),
        "counts": {"tp": total.tp, "fp": total.fp, "fn": total.fn},
    }


def _ratio(hits: int, n: int) -> float | None:
    return None if n == 0 else hits / n
