"""Turn scored documents into the variants report: per-class and per-field F1, tag slices, weak spots, worst documents."""

from collections import Counter, defaultdict

from evals.metrics import NEGATIVE, Counts, DocResult, flatten, summarise

MIN_SLICE_DOCS = 5


def doc_errors(d: DocResult) -> int:
    # Fieldless negatives can fail routing or the empty-object convention without any field errors.
    failed_output = d.pred_class != d.gold_class or (d.gold_class == NEGATIVE and not d.empty_output)
    return max(d.counts.fp + d.counts.fn, int(failed_output))


def by_field(docs: list[DocResult]) -> dict[str, dict]:
    total: defaultdict[str, Counts] = defaultdict(Counts)
    for d in docs:
        for path, counts in d.by_field.items():
            total[path].add(counts)
    rows = {path: {"f1": c.f1, "tp": c.tp, "fp": c.fp, "fn": c.fn} for path, c in total.items()}
    return dict(sorted(rows.items(), key=lambda kv: (1 if kv[1]["f1"] is None else kv[1]["f1"], kv[0])))


def confusion(docs: list[DocResult]) -> dict[str, dict[str, int]]:
    """How many documents of each reference class the app routed to each class; `None` means it wrote no output."""
    table: defaultdict[str, Counter] = defaultdict(Counter)
    for d in docs:
        table[d.gold_class][str(d.pred_class)] += 1
    return {gold: dict(sorted(row.items())) for gold, row in sorted(table.items())}


def misrouted(docs: list[DocResult], tags: dict) -> list[dict]:
    """Every document the app put in another class than its reference (`None`: no output), with how it was rendered."""
    return [
        {
            "case": d.case,
            "file": d.file,
            "class": d.gold_class,
            "predicted_class": d.pred_class,
            "tags": tags[(d.case, d.file)],
        }
        for d in docs
        if d.pred_class != d.gold_class
    ]


def slices(
    docs: list[DocResult], tags: dict[tuple[str, str], dict[str, str]], min_docs: int = MIN_SLICE_DOCS
) -> list[dict]:
    """One row per (medium, tag, value): F1 of the documents that carry the tag value. Text and scans are kept apart."""
    groups: defaultdict[tuple[str, str, str], list[DocResult]] = defaultdict(list)
    for d in docs:
        doc_tags = tags[(d.case, d.file)]
        for key, value in doc_tags.items():
            if key not in {"medium", "source"}:
                groups[(doc_tags["medium"], key, value)].append(d)
    rows = []
    for (medium, key, value), members in groups.items():
        if len(members) < min_docs:
            continue
        counts = Counts()
        for d in members:
            counts.add(d.counts)
        rows.append(
            {
                "medium": medium,
                "tag": key,
                "value": value,
                "docs": len(members),
                "micro_f1": counts.f1,
                "fp": counts.fp,
                "fn": counts.fn,
                "perfect_docs": sum(doc_errors(d) == 0 for d in members),
            }
        )
    return sorted(rows, key=lambda r: (1 if r["micro_f1"] is None else r["micro_f1"], -r["docs"], r["tag"], r["value"]))


def field_diffs(gold: dict, pred: dict | None, limit: int = 12) -> list[dict]:
    """Expected and predicted values (normalised as the scorer sees them) of the fields that differ."""
    expected, got = flatten(gold), flatten(pred or {})
    missing, extra = expected - got, got - expected
    rows = []
    for path, value in sorted(missing):
        rows.append({"field": path, "expected": value, "got": sorted(v for p, v in extra if p == path)})
    rows += [{"field": p, "expected": None, "got": [v]} for p, v in sorted(extra) if p not in {m for m, _ in missing}]
    return rows[:limit]


def worst_docs(docs: list[DocResult], tags: dict, golds: dict, preds: dict, limit: int = 25) -> list[dict]:
    worst = sorted((d for d in docs if doc_errors(d)), key=doc_errors, reverse=True)[:limit]
    return [
        {
            "case": d.case,
            "file": d.file,
            "class": d.gold_class,
            "predicted_class": d.pred_class,
            "errors": doc_errors(d),
            "differences": field_diffs(golds[(d.case, d.file)], preds[(d.case, d.file)]),
            "tags": tags[(d.case, d.file)],
        }
        for d in worst
    ]


def build_report(docs: list[DocResult], tags: dict, golds: dict, preds: dict, min_docs: int = MIN_SLICE_DOCS) -> dict:
    by_medium = {
        medium: {"docs": len(part), **summarise(part)}
        for medium in ("text", "scan")
        if (part := [d for d in docs if tags[(d.case, d.file)]["medium"] == medium])
    }
    negative_families = defaultdict(list)
    for doc in docs:
        if kind := tags[(doc.case, doc.file)].get("neg_kind"):
            negative_families[kind].append(doc)
    return {
        "negative_families": {
            kind: {"docs": len(group), "empty": sum(doc.empty_output for doc in group)}
            for kind, group in sorted(negative_families.items())
        },
        "summary": summarise(docs),
        "confusion": confusion(docs),
        "misrouted": misrouted(docs, tags),
        "by_medium": by_medium,
        "by_field": by_field(docs),
        "slices": slices(docs, tags, min_docs),
        "worst_docs": worst_docs(docs, tags, golds, preds),
    }
