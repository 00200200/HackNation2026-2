"""Per-field error report: uv run python -m evals.field_report [--holdout] [--force-ocr] [--errors]

`evals.run` gives the headline F1. This report runs the pipeline in-process on the same training
documents and shows which fields fail. Two differences from `evals.metrics`:
- list items are paired one-to-one inside their parent before fields are compared, so a signer
  attached to the wrong principal is an error (the headline metric compares lists as multisets);
- `--force-ocr` ignores the PDF text layer and reads every page with OCR, to measure what OCR costs.
A wrong value costs one false positive and one false negative; null counts as a value.
"""

import argparse
import itertools
import re
import time
from collections import Counter, defaultdict

from evals.metrics import NEGATIVE, doc_class
from evals.run import DATA, HOLDOUT, load_cases
from kio2json.pipeline import process_pdf

_ABSENT = object()  # a field or list item that one side does not have


def normalized(value):
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip(" .,;").casefold()
    return value


def compare(gold, predicted, path: str = "") -> list[dict]:
    """Field records with status ok | wrong | missing (not predicted) | spurious (not in reference)."""
    containers = (dict, list)
    both_present = gold is not _ABSENT and predicted is not _ABSENT
    if (
        both_present
        and isinstance(gold, containers) != isinstance(predicted, containers)
        or (both_present and isinstance(gold, containers) and type(gold) is not type(predicted))
    ):
        # A dict where a list or scalar belongs: nothing lines up, so count both sides in full.
        return compare(gold, _ABSENT, path) + compare(_ABSENT, predicted, path)
    if isinstance(gold, dict) or isinstance(predicted, dict):
        gold = gold if isinstance(gold, dict) else {}
        predicted = predicted if isinstance(predicted, dict) else {}
        records = []
        for key in dict.fromkeys([*gold, *predicted]):
            child = f"{path}.{key}" if path else key
            records += compare(gold.get(key, _ABSENT), predicted.get(key, _ABSENT), child)
        return records
    if isinstance(gold, list) or isinstance(predicted, list):
        gold = gold if isinstance(gold, list) else []
        predicted = predicted if isinstance(predicted, list) else []
        # Pair items so that the number of correct fields is maximal. Lists here hold a few
        # items, so trying every assignment is cheap. Pairs with nothing in common stay unpaired.
        size = max(len(gold), len(predicted))
        agreement = [
            [sum(r["status"] == "ok" for r in compare(g, p, path)) for p in predicted] + [0] * (size - len(predicted))
            for g in gold
        ]
        best = max(
            itertools.permutations(range(size), len(gold)),
            key=lambda order: sum(agreement[i][j] for i, j in enumerate(order)),
            default=(),
        )
        records, paired = [], set()
        for i, j in enumerate(best):
            if agreement[i][j] > 0:
                paired.add(j)
                records += compare(gold[i], predicted[j], path)
            else:
                records += compare(gold[i], _ABSENT, path)
        for j, item in enumerate(predicted):
            if j not in paired:
                records += compare(_ABSENT, item, path)
        return records
    if gold is _ABSENT and predicted is _ABSENT:
        return []
    if predicted is _ABSENT:
        status = "missing"
    elif gold is _ABSENT:
        status = "spurious"
    else:
        status = (
            "ok"
            if gold == predicted
            and type(gold) is type(predicted)
            or (isinstance(gold, (int, float)) and isinstance(predicted, (int, float)) and gold == predicted)
            else "wrong"
        )
    return [
        {
            "field": path,
            "gold": None if gold is _ABSENT else gold,
            "predicted": None if predicted is _ABSENT else predicted,
            "status": status,
            "ok_normalized": status == "ok" or (status == "wrong" and normalized(gold) == normalized(predicted)),
        }
    ]


def f1(records: list[dict], key: str = "strict") -> tuple[float, float, float]:
    correct = sum(r["status"] == "ok" if key == "strict" else r["ok_normalized"] for r in records)
    predicted = sum(r["status"] != "missing" for r in records)
    expected = sum(r["status"] != "spurious" for r in records)
    precision = correct / predicted if predicted else 0.0
    recall = correct / expected if expected else 0.0
    return precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--holdout", action="store_true", help="only the holdout cases 51-60")
    parser.add_argument("--force-ocr", action="store_true", help="ignore the PDF text layer and OCR every page")
    parser.add_argument("--errors", action="store_true", help="list every field error")
    args = parser.parse_args()

    cases = load_cases(DATA, quick=False)
    if args.holdout:
        cases = {case: documents for case, documents in cases.items() if case in HOLDOUT}
    confusion = Counter()
    by_class = defaultdict(list)
    exact = Counter()
    counts = Counter()
    seconds = []
    for case, documents in cases.items():
        for name, gold in documents.items():
            started = time.perf_counter()
            try:
                _, predicted = process_pdf(DATA / case / name, force_ocr=args.force_ocr)
            except Exception as error:  # noqa: BLE001 - a damaged PDF scores as an empty prediction
                print(f"{case}/{name}: not processed ({type(error).__name__}: {error})")
                predicted = {}
            seconds.append(time.perf_counter() - started)
            gold_class, predicted_class = doc_class(gold), doc_class(predicted)
            confusion[(gold_class, predicted_class)] += 1
            # A misrouted document loses all its reference fields and adds the fields it invented.
            records = compare(gold, predicted if predicted_class == gold_class else {})
            if predicted_class != gold_class:
                records += compare({}, predicted)
            for record in records:
                record["document"] = f"{case}/{name}"
            by_class[gold_class] += records
            exact[gold_class] += all(r["status"] == "ok" for r in records)
            counts[gold_class] += 1

    classes = ["odwolanie", "pelnomocnictwo", "przelew", NEGATIVE]
    print(
        f"cases={len(cases)}  documents={len(seconds)}  force_ocr={args.force_ocr}  "
        f"mean {sum(seconds) / len(seconds):.2f} s/doc, max {max(seconds):.2f} s"
    )

    print("\nRouting (rows: reference, columns: predicted)")
    print(f"{'':18}" + "".join(f"{c:>18}" for c in classes))
    for reference in classes:
        print(f"{reference:18}" + "".join(f"{confusion[(reference, c)]:>18}" for c in classes))

    print(f"\n{'class':18}{'docs':>6}{'exact docs':>12}{'fields':>8}{'P':>8}{'R':>8}{'F1':>8}{'F1 norm.':>10}")
    everything = []
    for name in classes:
        records = by_class[name]
        everything += records
        precision, recall, score = f1(records)
        print(
            f"{name:18}{counts[name]:>6}{exact[name]:>12}{len(records):>8}"
            f"{precision:>8.3f}{recall:>8.3f}{score:>8.3f}{f1(records, 'normalized')[2]:>10.3f}"
        )
    precision, recall, score = f1(everything)
    print(
        f"{'ALL (micro)':18}{len(seconds):>6}{sum(exact.values()):>12}{len(everything):>8}"
        f"{precision:>8.3f}{recall:>8.3f}{score:>8.3f}{f1(everything, 'normalized')[2]:>10.3f}"
    )

    print(f"\n{'field':58}{'n':>5}{'ok':>5}{'wrong':>7}{'missing':>9}{'spurious':>10}")
    for name in classes:
        per_field = defaultdict(Counter)
        for record in by_class[name]:
            per_field[record["field"]][record["status"]] += 1
        for field, status in per_field.items():
            print(
                f"{name + ': ' + field:58}{sum(status.values()):>5}{status['ok']:>5}"
                f"{status['wrong']:>7}{status['missing']:>9}{status['spurious']:>10}"
            )

    if args.errors:
        print("\nErrors")
        for record in everything:
            if record["status"] != "ok":
                print(
                    f"{record['document']} | {record['field']} | {record['status']}"
                    f" | gold={record['gold']!r} | predicted={record['predicted']!r}"
                )


if __name__ == "__main__":
    main()
