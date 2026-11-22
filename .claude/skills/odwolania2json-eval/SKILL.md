---
name: odwolania2json-eval
description: "How the Odwołania2json jury scores the product (field-level F1 on a hidden set of real KIO cases) and how we reproduce it on the organizer's training data: data layout, the I/O contract the eval drives, the F1 definition, metrics and targets, quick and full runs, and the pre-push eval gate. Use when changing classification, OCR, extraction, prompts, schemas or the model, before every push of product code, and before submitting."
---

# Odwołania2json eval: score like the jury

Sources: `docs/task/BRIEF.md` (task details PDF, FAQ v1.0, organizer README, read 21.11.2026). Stage I is decided
**only** by F1 on a hidden test set of real cases; in stage II F1 is still 50%. Every change to the extraction path
is judged by this eval, not by eyeballing one document.

## Data

`data/uzp` is a committed copy of https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 (source commit in
`data/uzp/UPSTREAM`). The organizer was still fixing gold files on 21.11.2026: run `make data` before a full run,
check `git diff data/uzp`, commit it, and compare F1 only between runs on the same data commit.

- `data/uzp/dane/przyklad_01..60/`: `odwolanie.pdf`, `pelnomocnictwo.pdf`, `potwierdzenie_przelewu.pdf` and gold
  `odwolanie.json`, `pelnomocnictwo.json`, `przelew.json`. The training cases are synthetic; the test set is real
  (different layouts, scans). Do not tune to their quirks.
- Negatives (gold = empty `.json`): `data/uzp/dane/negatywne/` and the extra PDF in `przyklad_04`, `_10`, `_24`, `_37`.
- Schemas with per-field rules in `//` comments: `data/uzp/oczekiwane-json/`; the 1–12 action dictionary:
  `czynnosc_powod_id_dict.md`.

## Commands

```bash
uv run python -m evals.run --quick                       # przyklad_01-05, _24 + 3 negatives; before a push
uv run python -m evals.run                               # all 60 cases + all negatives; before submitting
uv run python -m evals.run --pred output/                # score an existing output tree (original file names)
make eval-real HN_REAL_CORPUS=/path/to/corpus HN_REAL_SPLIT=dev   # HN_REAL_CORPUS is required
uv run python -m evals.run --corpus "$corpus" --split test
uv run python -m evals.run --corpus "$corpus" --split dev --detail-out "$corpus/dev-detail.json"
uv run python -m evals.field_report --corpus "$corpus" --split dev --force-ocr --errors
uv run pytest -q tests/test_eval_metrics.py              # metric code only
```

The app is called with the jury's contract: `--cmd` or `ODW_CMD` (default
`uv run python -m kio2json --input {input} --output {output}`). The eval
copies each case to `input/<case>/dokument_NN.pdf` in shuffled order, so the app cannot classify by file name, and
reads `output/<case>/dokument_NN.json`. `ODW_TIMEOUT_S` bounds the run (default 3600 s). Exit code 1 when a
required metric fails or is unknown.

A completed training run writes `evals/results/latest.json` (commit it: it is the "own quality test results" deliverable) and
`.git/eval-latest.json`, which the pre-push hook reads. Results carry per-document TP/FP/FN, so look at the worst
documents and fields before changing prompts.

Training mode checks the selected cases and filenames against the committed organizer inventory in `data/uzp/dane`,
including mixed-case negatives and the three fixed quick-mode negatives. An override with `--data` uses the same layout.
Commit a reviewed organizer data refresh before evaluating the new inventory.

Set `corpus` to the local corpus root. Each `cases/<case_id>/<name>.pdf` needs a matching
`gold/<case_id>/<name>.json`, including an empty file for each unrelated PDF. Use `--pred DIR` to read
`DIR/<case_id>/<name>.json` from a previous extraction. Corpus mode writes aggregates to
`evals/results/corpus-latest.json` and leaves the training gate alone.
`make eval-real` needs `HN_REAL_CORPUS` and fails with a message when it is unset. Set `HN_REAL_SPLIT` to `dev`, `test`, or `all` (default).
The optional `--detail-out` file must be outside every checkout of this repository and its Git metadata.
On test splits, corpus I/O failures report an error count and type on the console.
Invalid inputs, an empty selection and extractor failures exit 2 before writing results or the training gate.
Both commands validate selected PDF pages and their text layers and read every reference as UTF-8 JSON, even when scoring saved predictions.
A zero-byte corpus reference labels a negative. The three named organizer references must each contain fields for the expected class. A bad prediction misses all gold leaves and counts as incomplete.
For a negative prediction to meet the team target, its file must contain `{}` (the JSON writer appends a newline). A missed target gives exit code 1. Targets with no applicable documents, such as negative handling on an all-positive corpus, are skipped.

An optional `SPLIT.json` at the corpus root gives two lists of case folder names, `dev` and `test`.
Together they must cover each case exactly once. Both commands accept `--split dev|test|all` (default `all`).
Only the selected split's gold and PDFs are scored. Inspect field errors on dev and score test by aggregates.
For a run that includes designated test cases, the field report requires an external `--detail-out` for
`--errors` and sends document diagnostics to that file.

## F1 definition (`evals/metrics.py`)

UZP published the field-counting rules on 21 November 2026. The exact string similarity function remains unconfirmed. [Organizer answers](https://github.com/00200200/HackNation2026-2/issues/59)

| Prediction | Reference | Count |
|---|---|---|
| Matching value | Present | TP |
| Wrong value | Present | FP |
| Present | Absent | FP |
| Absent | Present | FN |
| Absent | Absent | TN |

A missing field and JSON null both mean absent. Micro F1 is `2 TP / (2 TP + FP + FN)`, pooled across documents. TN contributes nothing. A wrong guess and a null each cost one error when the reference contains a value. Retain a supported, partially legible name and trim OCR noise when possible. An invented value against an absent reference costs an FP.

The evaluator uses RapidFuzz normalized Levenshtein similarity of at least 0.80 for the attorney firm, transfer title, appellant name, contracting authority name and procurement title. Other text fields require equality after whitespace and case normalization. Printed identifiers retain country prefixes, case, leading zeros and punctuation, with whitespace removed. JSON numbers compare by value.

List entries are paired one-to-one by content within each parent. The assignment maximizes matching leaves, then pairs remaining present fields. Reordering entries preserves the score, and duplicate entries consume distinct matches. Missing predictions miss all present reference values. Extra predicted values on unrelated documents are FP.

`micro_f1_strict` retains the historical score for comparison across revisions. It flattens lists to leaf multisets, includes null hits, compares accounts as printed without whitespace and uses the original normalization for other identifiers and charges FP + FN for an incorrect substitution. `micro_f1_non_null` is its historical gold-null-excluded variant.

The document, class and field macro scores average the defined UZP F1 scores of their respective groups. An empty average is JSON null. Full runs also report both micro metrics on training cases 51–60.

## Metrics and targets

| Results key | Meaning | Target |
|---|---|---|
| `micro_f1` | pooled field-level F1, all documents incl. negatives | ≥ `ODW_F1_TARGET` (0.90 default; **team target**, the jury has no threshold, only a ranking) |
| `micro_f1_strict` | historical pooled field-level F1 | reported |
| `outputs_complete` | every input PDF has a valid JSON object in the right place | 1.00 |
| `negatives_empty` | negatives returned as `{}` | 1.00 |
| `classification_accuracy` | positive documents given the right class | 1.00 |
| `seconds_per_doc` | wall time of the whole run / documents (16 GB, i7, no GPU at the jury) | reported |

Also look at `per_class_f1` and `micro_f1_non_null`. A full run passes only with `coverage_ok` (all 60 cases and
the negatives directory).

## Overfitting and honesty rules

- Cases 51–60 are the **holdout**: do not open their PDFs or gold files while writing prompts, rules or few-shot
  examples. Report the holdout F1 next to the full F1; a large gap means overfitting.
- Never copy gold values, case-specific names, numbers or account numbers into prompts, configs or code. The jury
  tests on real, unseen cases; the `judge` agent greps for this.
- Few-shot examples, if any, come from cases 01–50 only and are listed in the README.
- Numbers in the README, docs or pitch come from `evals/results/latest.json` with its commit and mode, labelled
  "training data (synthetic)". Never present them as the test-set score.

## Pre-push gate

- Product code changed (anything outside `docs/`, `data/`, Markdown, `.claude/`, `.githooks/`, `.github/`,
  `.gitignore`, `LICENSE`, `evals/results/`): commit, then run at least `--quick` on the committed state. Once
  `.git/eval-latest.json` exists, the hook requires a clean run with both metrics. Only UZP F1 has an F1 target.
- Failing metric on a normal push: the hook warns, the `judge` agent decides PASS or BLOCK (a drop in `micro_f1`
  against the last committed results, or any negative not empty, is BLOCK).
- Submission push (`HN_FINAL=1 git push`): full run on that commit, every required metric passing, `coverage_ok`.
- Emergency only: `HN_SKIP_EVAL=1 git push`, and tell the team.
