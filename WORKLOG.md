# Worklog

Shared state of the project. Rules: `CLAUDE.md` → Worklog.

## Now

- Task brief, FAQ and details PDF in `docs/task/`; organizer repo copied into `data/uzp` (`make data` refreshes);
  template example in `input/case1`.
- Eval harness (`evals/`, field-level F1 on the training cases, working definition) with tests.
  `evals/field_report.py` adds a per-field error table and an OCR stress run (`--force-ocr`).
- On `feat/config-driven-classes`, the CLI reads class definitions from `config/classes/`.
  The jury classes use their existing Python extractors. A disabled participation form demonstrates
  config-only routing and labelled fields. Pydantic AI structured extraction and null-field fallback
  have offline tests. The CLI still uses pdfplumber and Polish Tesseract, with per-PDF errors on stderr.
- Research notes on OCR, schema extraction and Polish legal NLP: `docs/kio-extraction-research.md`.
- Claude Code setup: skills `hacknation-judging`, `odwolania2json-eval`, `build`, `verify`, `humanizer`;
  agents `judge`, `builder`, `reviewer`, `researcher`; pre-push hook in `.githooks/`.

## Last eval

21.11.2026, full mode, rule-based baseline (`evals/results/latest.json`): `micro_f1` 1.000, cases 51-60 1.000,
`classification_accuracy` 1.000, `negatives_empty` 1.000. Training data (synthetic). The rules were written with
sight of these documents, cases 53-60 included, so this is a regression check and the 51-60 figure is not an
unseen-case estimate for this baseline.

## Next

| Item | Owner |
|---|---|
| OCR challenger: Tesseract vs a pip-installable engine (PP-OCRv6) on `evals.field_report --force-ocr` | — |
| OCR-tolerant rules: account checksum repair, `0.0.` → `o.o.`, signers without dotted lines | — |
| Real-layout appeals: small reference set from real KIO appeals; coordinate-aware rules vs a grounded model call | — |
| Measure accuracy and latency of the config-selected LLM on real layouts once the EU model endpoint is available | — |
| Transparency output: source page, quoted text and rule per field | — |
| GUI: upload, run, source and JSON side by side | — |
| Ask the UZP stand: F1 formula, stage II weights (README 50/50 vs PDF 50/30/20) | — |

## Decisions

- 21.11.2026: Python 3.13, uv, pydantic-ai 2.71.0. Cases 51–60 are the holdout for prompt work.
- 21.11.2026: rules first. Every training target PDF has a text layer and the rules match all reference JSONs, so
  an OCR or model change has to beat this baseline in the eval. The baseline's rules have seen cases 51-60; a fresh case split is needed to measure generalization for work that builds on these rules.
- 21.11.2026: use the date and act stated together in the first charge. When its heading lacks a date, use
  the introductory sentence describing the dated act. In cases 01–39 that sentence supplies the reference reason.
- 21.11.2026: unrelated documents get an empty file (UNCONFIRMED with UZP; `evals.metrics` also accepts `{}`).
- 21.11.2026: file, module and identifier names are English; Polish only in the organizer's JSON keys and file stems.
- 21.11.2026: delegated work and reviews (pre-commit review, pre-push judge) go to Codex workers through
  `/orchestrator`, not to Claude subagents.

## Log

- 21.11.2026 · Claude · brief, eval harness, judge/eval skills, pre-push hook · f6db304
- 21.11.2026 · Claude · stricter F1 normalisation (types, formats), invented test fixture, organizer data copied into the repo (UZP e8b7a67)
- 21.11.2026 · Claude · rule-based baseline `kio2json`, field report, data refresh to UZP 7590db8 (reason 6 description is now `Odpowiedzi/wyjaśnienia do SWZ`); full eval `micro_f1` 1.000 on training data
- 21.11.2026 · Codex · fixed OCR failure reporting, payment and party roles, first-charge dates and field-report matching. Added regressions with invented fixtures. Extraction fixes in `0ecd41c`.
- 21.11.2026 · Codex · Configured routing and three extraction engines in `00a84f2`. The fourth class uses only TOML. All 196 synthetic corpus outputs matched baseline `4deb354` byte for byte. The field report found zero errors across 2,316 fields.
- 21.11.2026 · Codex · Bound transfer values, appeal facts, grantors and signers to their document sections. Added invented regression cases, replaced the organizer identifier in the normalization test and checked 40 fresh adversarial inputs. Transfer and appeal changes in `aaa8057` and `a10b5ad`.
