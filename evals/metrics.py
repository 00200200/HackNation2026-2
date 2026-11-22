"""Field-level F1 for Odwołania2json outputs, following UZP's rules in issue #59.

A present match is TP, a present wrong or extra value is FP, a missing value is FN,
and both absent is TN (outside F1). Five long strings accept similarity >= 0.80.
UZP has not specified the similarity function. We use RapidFuzz normalized Levenshtein.
List entries are assigned one-to-one within their parent by matching field content.
Micro pools counts within documents, macro averages defined document, class or field scores.

The secondary strict metric preserves the historical normalized leaf multisets, including
null hits and a double penalty (FP + FN) for a wrong value. Both metrics compare the letters and
digits of account numbers as printed after removing whitespace. A zero-byte gold file labels a
negative, whose expected output is `{}` with an optional line ending.
"""

import json
import re
import stat
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz.distance import Levenshtein

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
    tn: int = 0

    def add(self, other: "Counts") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.tn += other.tn

    @property
    def f1(self) -> float | None:
        denom = 2 * self.tp + self.fp + self.fn
        return None if denom == 0 else 2 * self.tp / denom


def compare_strict(
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


FUZZY_PATHS = {
    "Odwolujacy[].nazwa",
    "Odwolujacy[].pelnomocnik.nazwa",
    "Zamawiajacy[].nazwa",
    "przelew_bankowy.tytul",
    "ZamowieniePubliczne.tytul",
}
PRINTED_IDS = {
    "krs",
    "nip",
    "regon",
    "pesel",
    "numer_bzp",
    "numer_ted",
    "numer_postepowania",
    "numer_transakcji",
}


def matches(pred, gold, path: str) -> bool:
    key = path.rsplit(".", 1)[-1].removesuffix("[]")
    if key in ACCOUNT_KEYS:
        return isinstance(pred, str) and isinstance(gold, str) and normalise(pred, key) == normalise(gold, key)
    if key in PRINTED_IDS:
        if type(pred) not in (int, str) or type(gold) not in (int, str):
            return False
        return "".join(str(pred).split()) == "".join(str(gold).split())
    if isinstance(pred, str) and isinstance(gold, str):
        left, right = normalise(pred), normalise(gold)
        if path in FUZZY_PATHS:
            return Levenshtein.normalized_similarity(left, right) >= 0.80
        return left == right
    if type(pred) in (int, float) and type(gold) in (int, float):
        return pred == gold
    return type(pred) is type(gold) and pred == gold


def list_events(pred: list, gold: list, path: str):
    # Canonical order gives equal-scoring assignments stable per-field diagnostics.
    def order(item):
        return json.dumps(item, sort_keys=True)

    pred, gold = sorted(pred, key=order), sorted(gold, key=order)
    used_pred, used_gold = set(), set()
    if pred and gold:
        # Only field-level list scoring needs this dev dependency. The jury batch checks exact JSON.
        from munkres import linear_sum_assignment

        candidates = [[list(field_events(p, g, path)) for g in gold] for p in pred]
        # First maximize TP, then pair remaining present values at the same field as wrong.
        bound = 1 + sum(max(len(pair) for pair in row) for row in candidates)
        weights = [
            [sum(bound if event == "tp" else int(event == "wrong") for _, event in pair) for pair in row]
            for row in candidates
        ]
        rows, columns = linear_sum_assignment(weights, maximize=True)
        for i, j in zip(rows, columns):
            used_pred.add(i)
            used_gold.add(j)
            yield from candidates[i][j]
    for i, value in enumerate(pred):
        if i not in used_pred:
            yield from field_events(value, None, path)
    for j, value in enumerate(gold):
        if j not in used_gold:
            yield from field_events(None, value, path)


def field_events(pred, gold, path: str):
    if isinstance(pred, (list, dict)) and gold is not None and not isinstance(gold, (list, dict)):
        yield path, "wrong"
    elif isinstance(gold, (list, dict)) and pred is not None and type(pred) is not type(gold):
        yield from field_events(pred, None, path)
        yield from field_events(None, gold, path)
    elif isinstance(pred, dict) or isinstance(gold, dict):
        pred, gold = pred or {}, gold or {}
        for key in pred.keys() | gold.keys():
            yield from field_events(pred.get(key), gold.get(key), f"{path}.{key}" if path else key)
    elif isinstance(pred, list) or isinstance(gold, list):
        yield from list_events(pred or [], gold or [], f"{path}[]")
    elif pred is None:
        yield path, "tn" if gold is None else "fn"
    elif gold is None:
        yield path, "fp"
    else:
        yield path, "tp" if matches(pred, gold, path) else "wrong"


def compare(pred: dict | None, gold: dict, *, by_field: dict[str, Counts] | None = None) -> Counts:
    fields = by_field if by_field is not None else {}
    total = Counts()
    for path, event in field_events(pred or {}, gold, ""):
        count = fields.setdefault(path, Counts())
        attribute = "fp" if event == "wrong" else event
        setattr(count, attribute, getattr(count, attribute) + 1)
        setattr(total, attribute, getattr(total, attribute) + 1)
    return total


@dataclass
class DocResult:
    case: str
    file: str
    gold_class: str
    pred_class: str | None
    counts: Counts
    counts_strict: Counts
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
        compare_strict(pred, gold),
        compare_strict(pred, gold, skip_gold_nulls=True),
        empty_output,
        errors,
        by_field,
    )


def summarise(docs: list[DocResult]) -> dict:
    total, strict, non_null = Counts(), Counts(), Counts()
    per_class = {name: Counts() for name in CLASSES}
    per_field: defaultdict[str, Counts] = defaultdict(Counts)
    for d in docs:
        total.add(d.counts)
        strict.add(d.counts_strict)
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
        "micro_f1_strict": strict.f1,
        "counts_strict": {"tp": strict.tp, "fp": strict.fp, "fn": strict.fn},
        "macro_f1_documents": _ratio(sum(document_scores), len(document_scores)),
        "macro_f1_classes": _ratio(sum(class_scores.values()), len(class_scores)),
        "macro_f1_class_count": len(class_scores),
        "macro_f1_fields": _ratio(sum(field_scores), len(field_scores)),
        "micro_f1_non_null": non_null.f1,
        "per_class_f1": class_scores,
        "classification_accuracy": _ratio(sum(d.pred_class == d.gold_class for d in positives), len(positives)),
        "negatives_empty": _ratio(sum(d.empty_output for d in negatives), len(negatives)),
        "outputs_complete": _ratio(sum(not d.errors for d in docs), len(docs)),
        "counts": {"tp": total.tp, "fp": total.fp, "fn": total.fn, "tn": total.tn},
    }


def _ratio(hits: float, n: int) -> float | None:
    return None if n == 0 else hits / n
