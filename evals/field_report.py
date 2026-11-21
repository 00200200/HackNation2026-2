"""Per-field error report: uv run python -m evals.field_report [--holdout | --corpus DIR] [--force-ocr] [--errors]

`evals.run` gives the headline F1. This report runs the pipeline in-process on the selected
documents and shows which fields fail. Two differences from `evals.metrics`:
- list items are paired one-to-one inside their parent before fields are compared, so a signer
  attached to the wrong principal is an error (the headline metric compares lists as multisets);
- `--force-ocr` ignores the PDF text layer and reads every page with OCR, to measure what OCR costs.
A wrong value costs one false positive and one false negative; null counts as a value.
"""

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from contextlib import nullcontext
from pathlib import Path
from typing import TextIO

from munkres import linear_sum_assignment

from evals.metrics import NEGATIVE, doc_class
from evals.run import DATA, HOLDOUT, corpus_io_errors, external_detail_path, load_cases, load_corpus, private_output
from kio2json.pipeline import process_pdf

_ABSENT = object()  # a field or list item that one side does not have


def normalized(value):
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip(" .,;").casefold()
    return value


def principal_name(item):
    if isinstance(item, dict) and isinstance(item.get("data"), dict):
        return normalized(item["data"].get("nazwa"))
    return None


def compare_list(gold, predicted, path, mode):
    pairs = {}
    if gold and predicted:
        scores = []
        for left in gold:
            row = []
            for right in predicted:
                left_name, right_name = principal_name(left), principal_name(right)
                if left_name and right_name and left_name != right_name:
                    row.append((0, 0, False))
                    continue
                fields = compare(left, right, path, mode=mode)
                hits = sum(field["status"] == "ok" for field in fields)
                # Maximize matching leaves; use normalized hits to break strict ties.
                row.append(
                    (hits, sum(field["ok_normalized"] for field in fields), bool(left_name and left_name == right_name))
                )
            scores.append(row)
        # Lexicographic priorities for the whole assignment: identity, strict (or normalized)
        # hits, then normalized tie-breaks. One unit outweighs every possible lower-level hit.
        bound = 1 + sum(max((score[1] for score in row), default=0) for row in scores)
        weights = [[(identity * bound + hits) * bound + ties for hits, ties, identity in row] for row in scores]
        rows, columns = linear_sum_assignment(weights, maximize=True)
        pairs = {i: j for i, j in zip(rows, columns) if weights[i][j]}

    records = []
    for i, left in enumerate(gold):
        right = predicted[pairs[i]] if i in pairs else _ABSENT
        records.extend(compare(left, right, path, mode=mode))
    matched = set(pairs.values())
    for j, right in enumerate(predicted):
        if j not in matched:
            records.extend(compare(_ABSENT, right, path, mode=mode))
    return records


def compare(gold, predicted, path: str = "", *, mode: str = "strict") -> list[dict]:
    """Field records with status ok | wrong | missing (not predicted) | spurious (not in reference)."""
    containers = (dict, list)
    both_present = gold is not _ABSENT and predicted is not _ABSENT
    if (
        both_present
        and isinstance(gold, containers) != isinstance(predicted, containers)
        or (both_present and isinstance(gold, containers) and type(gold) is not type(predicted))
    ):
        # A dict where a list or scalar belongs: nothing lines up, so count both sides in full.
        return compare(gold, _ABSENT, path, mode=mode) + compare(_ABSENT, predicted, path, mode=mode)
    if isinstance(gold, dict) or isinstance(predicted, dict):
        gold = gold if isinstance(gold, dict) else {}
        predicted = predicted if isinstance(predicted, dict) else {}
        records = []
        for key in dict.fromkeys([*gold, *predicted]):
            child = f"{path}.{key}" if path else key
            records += compare(gold.get(key, _ABSENT), predicted.get(key, _ABSENT), child, mode=mode)
        return records
    if isinstance(gold, list) or isinstance(predicted, list):
        gold = gold if isinstance(gold, list) else []
        predicted = predicted if isinstance(predicted, list) else []
        return compare_list(gold, predicted, path, mode)
    if gold is _ABSENT and predicted is _ABSENT:
        return []
    if predicted is _ABSENT:
        status = "missing"
    elif gold is _ABSENT:
        status = "spurious"
    else:
        numeric = type(gold) in (int, float) and type(predicted) in (int, float)
        compatible = type(gold) is type(predicted) or numeric
        equal = normalized(gold) == normalized(predicted) if mode == "normalized" else gold == predicted
        status = "ok" if compatible and equal else "wrong"
    return [
        {
            "field": path,
            "gold": None if gold is _ABSENT else gold,
            "predicted": None if predicted is _ABSENT else predicted,
            "status": status,
            "ok_normalized": status == "ok"
            or (
                status == "wrong"
                and isinstance(gold, str)
                and isinstance(predicted, str)
                and normalized(gold) == normalized(predicted)
            ),
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--holdout", action="store_true", help="only the holdout cases 51-60")
    source.add_argument("--corpus", type=Path, help="paired cases/ and gold/ directories")
    parser.add_argument(
        "--split", choices=("dev", "test", "all"), help="case partition in corpus SPLIT.json (default all)"
    )
    parser.add_argument(
        "--detail-out", type=external_detail_path, help="write document diagnostics to this private file"
    )
    parser.add_argument("--force-ocr", action="store_true", help="ignore the PDF text layer and OCR every page")
    parser.add_argument("--errors", action="store_true", help="list every field error")
    args = parser.parse_args()

    with corpus_io_errors(parser, args.corpus):
        if (args.detail_out or args.split) and not args.corpus:
            parser.error("--detail-out and --split require --corpus")
        split = args.split or "all"
        includes_test = args.corpus and split != "dev" and (args.corpus / "SPLIT.json").is_file()
        if includes_test and args.errors and not args.detail_out:
            parser.error("--errors on test cases requires --detail-out outside the repository")
        data = args.corpus / "cases" if args.corpus else DATA
        try:
            cases = load_corpus(args.corpus, split) if args.corpus else load_cases(data, quick=False)
        except ValueError as exc:
            parser.error(str(exc))
        except OSError as exc:
            if args.corpus:
                raise
            parser.error(str(exc))
        if args.holdout:
            cases = {case: documents for case, documents in cases.items() if case in HOLDOUT}
        output = (
            private_output(args.detail_out) if args.detail_out else nullcontext(None if includes_test else sys.stdout)
        )
        with output as diagnostics:
            print_report(cases, data, force_ocr=args.force_ocr, errors=args.errors, diagnostics=diagnostics)


def print_report(cases: dict, data: Path, *, force_ocr: bool, errors: bool, diagnostics: TextIO | None) -> None:
    processing_errors = Counter()
    confusion = Counter()
    by_class = defaultdict(list)
    normalized_by_class = defaultdict(list)
    exact = Counter()
    counts = Counter()
    seconds = []
    for case, documents in cases.items():
        for name, gold in documents.items():
            started = time.perf_counter()
            try:
                _, predicted = process_pdf(data / case / name, force_ocr=force_ocr)
            except Exception as error:  # noqa: BLE001 - a damaged PDF scores as an empty prediction
                if diagnostics is not sys.stdout:
                    processing_errors[type(error).__name__] += 1
                if diagnostics is not None:
                    print(f"{case}/{name}: not processed ({type(error).__name__}: {error})", file=diagnostics)
                predicted = {}
            seconds.append(time.perf_counter() - started)
            gold_class, predicted_class = doc_class(gold), doc_class(predicted)
            confusion[(gold_class, predicted_class)] += 1
            # A misrouted document loses all its reference fields and adds the fields it invented.
            if predicted_class == gold_class:
                records = compare(gold, predicted)
                normalized_by_class[gold_class].extend(compare(gold, predicted, mode="normalized"))
            else:
                records = compare(gold, {}) + compare({}, predicted)
                normalized_by_class[gold_class].extend(records)
            for record in records:
                record["document"] = f"{case}/{name}"
            by_class[gold_class] += records
            exact[gold_class] += all(r["status"] == "ok" for r in records)
            counts[gold_class] += 1

    for error_type, count in sorted(processing_errors.items()):
        print(f"document processing errors={count} ({error_type})", file=sys.stderr)
    if not seconds:
        print(f"cases={len(cases)}  documents=0")
        return
    classes = ["odwolanie", "pelnomocnictwo", "przelew", NEGATIVE]
    if "unknown" in counts or any(predicted == "unknown" for _, predicted in confusion):
        classes.append("unknown")
    print(
        f"cases={len(cases)}  documents={len(seconds)}  force_ocr={force_ocr}  "
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
            f"{precision:>8.3f}{recall:>8.3f}{score:>8.3f}{f1(normalized_by_class[name])[2]:>10.3f}"
        )
    normalized_all = [record for records in normalized_by_class.values() for record in records]
    precision, recall, score = f1(everything)
    print(
        f"{'ALL (micro)':18}{len(seconds):>6}{sum(exact.values()):>12}{len(everything):>8}"
        f"{precision:>8.3f}{recall:>8.3f}{score:>8.3f}{f1(normalized_all)[2]:>10.3f}"
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

    if errors and diagnostics is not None:
        print("\nErrors", file=diagnostics)
        for record in everything:
            if record["status"] != "ok":
                print(
                    f"{record['document']} | {record['field']} | {record['status']}"
                    f" | gold={record['gold']!r} | predicted={record['predicted']!r}",
                    file=diagnostics,
                )


if __name__ == "__main__":
    main()
