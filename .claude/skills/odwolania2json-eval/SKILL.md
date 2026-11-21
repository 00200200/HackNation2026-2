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
make eval-real                                          # local corpus, override with HN_REAL_CORPUS
uv run python -m evals.run --corpus "$corpus" --detail-out "$corpus/detail-latest.json"
uv run python -m evals.field_report --corpus "$corpus" --force-ocr --errors
uv run pytest -q tests/test_eval_metrics.py              # metric code only
```

The app is called with the jury's contract: `--cmd` or `ODW_CMD` (default
`uv run python -m kio2json --input {input} --output {output}`). The eval
copies each case to `input/<case>/dokument_NN.pdf` in shuffled order, so the app cannot classify by file name, and
reads `output/<case>/dokument_NN.json`. `ODW_TIMEOUT_S` bounds the run (default 3600 s). Exit code 1 when a
required metric fails or is unknown.

Each training run writes `evals/results/latest.json` (commit it: it is the "own quality test results" deliverable) and
`.git/eval-latest.json`, which the pre-push hook reads. Results carry per-document TP/FP/FN, so look at the worst
documents and fields before changing prompts.

Set `corpus` to the local corpus root. Each `cases/<case_id>/<name>.pdf` needs a matching
`gold/<case_id>/<name>.json`, including an empty file for each unrelated PDF. Use `--pred DIR` to read
`DIR/<case_id>/<name>.json` from a previous extraction. Corpus mode writes aggregates to
`evals/results/corpus-latest.json` and leaves the training gate alone. Use `--detail-out` outside the repository
for document-level counts. An empty corpus or a missed target gives exit code 1. Targets with no applicable
documents, such as negative handling on an all-positive corpus, are skipped. The field report can print private document values to the terminal with `--errors`.

## F1 definition (`evals/metrics.py`)

The organizer has not published the formula: **UNCONFIRMED**, ask at the UZP stand and update `metrics.py` and
this section when they answer. Working definition:

- Each JSON is flattened to `(path, value)` leaf pairs; list indices become `[]`, so lists compare as multisets.
- Values are normalised: whitespace and case; numbers by value (`10000.00 == 10000`); identifier fields (`krs`,
  `nip`, `regon`, `pesel`, `na_rachunek`, `z_rachunku`) as digits only, string or number. Types (`"3" != 3`) and
  format rules from the schema comments (ISO dates, `YYYY/BZP########`, TED `NNNNNN-YYYY`, `czynnosc_opis` exactly
  as in the dictionary) are **not** normalised away: the product must emit them.
- `null` leaves count: null where gold is null is a hit; an invented value is a FP and a FN. Never fill a field the
  document does not state (FAQ 6). `micro_f1_non_null` shows the variant that ignores gold-null fields.
- Negative document: gold is empty, every predicted pair is a FP. Missing/invalid output: every gold pair is a FN.
- The micro-F1 is pooled over all documents. `holdout_51_60` (full run) reports the same on cases 51–60.
- `macro_f1_documents` averages F1 over documents with at least one predicted or reference leaf.
  An invented field on a negative gives that document zero.
- `macro_f1_classes` averages the field-level F1 scores for the target classes with reference or predicted fields.
  A wrong class incurs missed fields in the reference class and spurious fields in the predicted class.
  `macro_f1_class_count` gives the number of classes in the mean and `per_class_f1` names them.
- `macro_f1_fields` gives each distinct leaf path the same weight. Match values within each document,
  pool TP/FP/FN for each path across documents, then average the path scores. An empty average is JSON null.

## Metrics and targets

| Results key | Meaning | Target |
|---|---|---|
| `micro_f1` | pooled field-level F1, all documents incl. negatives | ≥ `ODW_F1_TARGET` (0.90 default; **team target**, the jury has no threshold, only a ranking) |
| `outputs_complete` | every input PDF has a valid JSON (or an empty file) in the right place | 1.00 |
| `negatives_empty` | negatives returned as an empty file | 1.00 |
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
  `.git/eval-latest.json` exists, the hook blocks a product push whose commit has no clean eval run.
- Failing metric on a normal push: the hook warns, the `judge` agent decides PASS or BLOCK (a drop in `micro_f1`
  against the last committed results, or any negative not empty, is BLOCK).
- Submission push (`HN_FINAL=1 git push`): full run on that commit, every required metric passing, `coverage_ok`.
- Emergency only: `HN_SKIP_EVAL=1 git push`, and tell the team.
