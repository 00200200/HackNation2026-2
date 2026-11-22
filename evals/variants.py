"""Run the keyless CLI on bounded chunks of generated synthetic cases."""

import hashlib
import json
import os
import random
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict
from itertools import batched, islice
from pathlib import Path

from evals.metrics import Counts, score_doc, summarise
from evals.variant_cases import NEGATIVES, PROFILES, SEED, generate


def schedule(n, seed):
    rng = random.Random(seed)
    for cycle in range((n + 59) // 60):
        cases = list(range(1, 61))
        profiles = list(PROFILES)
        negatives = list(NEGATIVES) * 10
        rng.shuffle(cases)
        rng.shuffle(profiles)
        rng.shuffle(negatives)
        for i, case in enumerate(cases):
            yield cycle * 60 + i, case, profiles[(i + cycle) % len(profiles)], negatives[i]


def evaluate_variants(n, data, cmd, destination, baseline, seed=SEED):
    from evals.run import git_state, run_app

    env = {**os.environ, "KIO_LLM_BASE_URL": "", "KIO_LLM_MODEL": "", "KIO_LLM_API_KEY": ""}
    env.pop("KIO_OCR_ENGINE", None)
    env.pop("KIO_CLASSES_DIR", None)
    groups = defaultdict(list)
    all_docs = []
    digest = hashlib.sha256()
    elapsed = 0
    for chunk in batched(islice(schedule(n, seed), n), 5):
        with tempfile.TemporaryDirectory(prefix="hn-variants-") as tmp:
            root = Path(tmp)
            references = []
            for index, source, profile, negative in chunk:
                case = f"case_{index + 1:05}"
                folder = root / "input" / case
                folder.mkdir(parents=True)
                docs = generate(data / f"przyklad_{source:02}", index, seed, profile, negative)
                for ordinal, (group, gold, pdf) in enumerate(docs, 1):
                    stem = f"dokument_{ordinal:02}"
                    (folder / f"{stem}.pdf").write_bytes(pdf)
                    digest.update(hashlib.sha256(pdf).digest())
                    digest.update(hashlib.sha256(json.dumps(gold, sort_keys=True).encode()).digest())
                    references.append((group, case, stem, gold))
            out = root / "output"
            out.mkdir()
            seconds, error = run_app(cmd, root / "input", out, env=env)
            if error:
                raise ValueError(f"variant extraction failed: {error}")
            elapsed += seconds
            for group, case, stem, gold in references:
                doc = score_doc(case, stem, out / case / f"{stem}.json", gold)
                groups[group].append(doc)
                all_docs.append(doc)
        print(f"Scored {len(all_docs) // 4}/{n} cases", flush=True)
    summary = summarise(all_docs)
    fields = defaultdict(Counts)
    for doc in all_docs:
        for path, counts in doc.by_field.items():
            fields[path].add(counts)
    commit, dirty = git_state()
    report = {
        "seed": seed,
        "cases": n,
        "docs": len(all_docs),
        "dataset_sha256": digest.hexdigest(),
        "commit": commit,
        "dirty": dirty,
        "chunk_cases": 5,
        "seconds_per_doc": elapsed / len(all_docs),
        **summary,
        "per_field": {k: {**asdict(v), "f1": v.f1} for k, v in sorted(fields.items())},
        "per_variant": {},
        "negative_families": {},
    }
    for group, docs in sorted(groups.items()):
        if group in NEGATIVES:
            report["negative_families"][group] = {"docs": len(docs), "empty": sum(d.empty_output for d in docs)}
        else:
            part = summarise(docs)
            totals = Counter(doc.gold_class for doc in docs)
            correct = Counter(doc.gold_class for doc in docs if doc.pred_class == doc.gold_class)
            report["per_variant"][group] = {
                "docs": len(docs),
                "routing_by_class": {
                    label: {"correct": correct[label], "total": n} for label, n in sorted(totals.items())
                },
                **{k: part[k] for k in ("micro_f1", "per_class_f1", "counts")},
            }
    report["weakest_first"] = sorted(report["per_variant"], key=lambda k: report["per_variant"][k]["micro_f1"])
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    passed = report["outputs_complete"] == 1
    if baseline:
        reference = json.loads(baseline.read_text())
        if reference["dataset_sha256"] != report["dataset_sha256"]:
            raise ValueError("variant baseline describes different generated documents")
        for key in ("micro_f1", "negatives_empty"):
            if report[key] < reference[key]:
                print(f"{key} regressed: {reference[key]:.4f} -> {report[key]:.4f}", file=sys.stderr)
                passed = False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    print(f"UZP micro F1 {report['micro_f1']:.4f}; weakest first: {', '.join(report['weakest_first'])}")
    return 0 if passed else 1
