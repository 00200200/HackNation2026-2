# Worklog

Shared state of the project. Rules: `CLAUDE.md` → Worklog.

## Now

- Task brief, FAQ and details PDF in `docs/task/`; organizer repo copied into `data/uzp` (`make data` refreshes);
  template example in `input/case1`.
- App: `kio2json/`, default jury classes use rule-based extraction. CLI `python -m kio2json --input input --output output`;
  content-based classification with a rejection path; regex and line-layout extraction per class; pdfplumber text
  with wheel-packaged Tesseract for blank or page-number-only text layers. Installation fetches and verifies the
  language models. Set `KIO_OCR_ENGINE=rapidocr` to use the optional RapidOCR v6 group. Both engines run offline
  and return word boxes in PDF points on request. Branch `feat/ocr-engine`.
- The eval harness scores training cases and local paired PDF/JSON corpora. It reports micro F1 and macro F1 by
  document, represented class and field. Both layouts support per-field errors and OCR stress runs (`--force-ocr`).
  Private detail files must be outside all worktrees and Git metadata. Input or extraction failures stop evaluation
  before it writes results or the training gate. Malformed and missing predictions count as misses.
- The CLI reads class definitions from `config/classes/`.
  The jury classes select the baseline content classifier and their Python extractors by dotted path.
  A disabled participation form demonstrates config-only routing and labelled fields. The optional
  model engine checks each complete source value against its own verbatim quote and reports endpoint failures per PDF.
- The Polish Shiny viewer and CLI share per-document parsing and diagnostics. The viewer compares PDF pages with their JSON and downloads a ZIP in case folders.
- Research notes on OCR, schema extraction and Polish legal NLP: `docs/kio-extraction-research.md`.
- Claude Code setup: skills `hacknation-judging`, `odwolania2json-eval`, `build`, `verify`, `humanizer`;
  agents `judge`, `builder`, `reviewer`, `researcher`; pre-push hook in `.githooks/`.

## Last eval

21.11.2026, full clean training run with packaged OCR (source commit in `evals/results/latest.json`): `micro_f1` 1.000, cases 51-60 1.000,
`classification_accuracy` 1.000, `negatives_empty` 1.000. Training data (synthetic). The rules were written with
sight of these documents, cases 53-60 included, so this is a regression check and the 51-60 figure is not an
unseen-case estimate for this baseline.

The merged forced-OCR field report scored 0.897 on 196 synthetic PDFs. Strict F1 on 17 real dev scans was
0.331 with Tesseract and 0.419 with RapidOCR v6. Natural dev F1 on 20 PDFs was 0.3864 and 0.4588, respectively.

21.11.2026, local real corpus. The all-corpus row comes from `00626a5`. The dev and test scores below
were first measured at `79eef2a` after the baseline merge. The latest test run records its commit in
`evals/results/corpus-latest.json`.
All three target classes entered each class average. Every PDF had an output and every negative was empty.

| Split | Cases | PDFs | Micro F1 | Macro by document | Macro by class | Macro by field | Positive classification accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| All | 20 | 37 | 0.4025 | 0.3327 | 0.3681 | 0.3978 | 0.7778 |
| Dev | 13 | 20 | 0.4323 | 0.3427 | 0.3676 | 0.3910 | 0.7143 |
| Test | 7 | 17 | 0.3481 | 0.2285 | 0.2445 | 0.3478 | 0.6154 |

Both splits missed the team’s micro F1 and classification targets. Compared with the earlier split runs at
`f93b908`, micro F1 fell from 0.4352 on dev and 0.3675 on test.

## Next

| Item | Owner |
|---|---|
| Real-layout appeals: small reference set from real KIO appeals; coordinate-aware rules vs a grounded model call | — |
| Measure accuracy and latency of the config-selected LLM on real layouts once the EU model endpoint is available | — |
| Transparency output: source page, quoted text and rule per field | — |
| Ask the UZP stand: F1 formula, stage II weights (README 50/50 vs PDF 50/30/20) | — |

## Decisions

- 21.11.2026: use the tesserocr wheel, Polish fast model and an English reread of ambiguous e-mail tokens. The
  model-data wheel verifies the upstream SHA-256 checksums at install time.
- 21.11.2026: Python 3.13, uv, pydantic-ai 2.71.0. Cases 51–60 are the holdout for prompt work.
- 21.11.2026: rules first. Every training target PDF has a text layer and the rules match all reference JSONs, so
  an OCR or model change has to beat this baseline in the eval. The baseline's rules have seen cases 51-60; a fresh case split is needed to measure generalization for work that builds on these rules.
- 21.11.2026: use the date and act stated together in the first charge. When its heading lacks a date, use
  the introductory sentence describing the dated act. In cases 01–39 that sentence supplies the reference reason.
- 21.11.2026: unrelated documents get an empty file (UNCONFIRMED with UZP; the team checks for a zero-byte output).
- 21.11.2026: file, module and identifier names are English; the jury GUI, organizer's JSON keys and original file stems use Polish.
- 21.11.2026: delegated work and reviews (pre-commit review, pre-push judge) go to Codex workers through
  `/orchestrator`, not to Claude subagents.

## Log

- 21.11.2026 · Claude · brief, eval harness, judge/eval skills, pre-push hook · f6db304
- 21.11.2026 · Claude · stricter F1 normalisation (types, formats), invented test fixture, organizer data copied into the repo (UZP e8b7a67)
- 21.11.2026 · Claude · rule-based baseline `kio2json`, field report, data refresh to UZP 7590db8 (reason 6 description is now `Odpowiedzi/wyjaśnienia do SWZ`); full eval `micro_f1` 1.000 on training data
- 21.11.2026 · Codex · fixed OCR failure reporting, payment and party roles, first-charge dates and field-report matching. Added regressions with invented fixtures. Extraction fixes in `0ecd41c`.
- 21.11.2026 · Codex · measured CPU OCR engines, shipped pip-only offline scans and word boxes, and repaired OCR fields. Forced-image field F1 0.903, native F1 1.000. `b36ceb5`.
- 21.11.2026 · Codex · Configured routing and three extraction engines in `00a84f2`. The fourth class uses only TOML. All 196 synthetic corpus outputs matched baseline `4deb354` byte for byte. The field report found zero errors across 2,316 fields.
- 21.11.2026 · Codex · added corpus scoring and macro F1, then measured the whole-case dev and test splits at `f93b908`.
- 21.11.2026 · Codex · Bound transfer values, appeal facts, grantors and signers to their document sections. Added invented regression cases, replaced the organizer identifier in the normalization test and checked 40 fresh adversarial inputs. Transfer and appeal changes in `aaa8057` and `a10b5ad`.
- 21.11.2026 · Codex · fixed private report destinations, corpus I/O diagnostics and invalid UTF-8 scoring in `be82db0`. Re-ran full training and both real-corpus splits.
- 21.11.2026 · Codex · fixed training reference validation and selected-file enumeration after the second review of PR #9. Added regression tests for quick, full, corpus, saved predictions and field reports.
- 21.11.2026 · Codex · full training exposed an organizer PDF whose page tree PDFMiner could not find. The harness now confirms that PDFium can render such inputs before scoring them.
- 21.11.2026 · Codex · Merged baseline `90d9701` and restored its routing through TOML. All 196 CLI outputs matched that baseline byte for byte, including 16 empty files. The field report found zero errors across 2,316 fields. Added regression tests for model evidence, endpoint diagnostics, alternative evidence captures, signed grouped amounts and malformed NIPs.
- 21.11.2026 · Codex · Fixed the remaining PR #8 grounding findings from review of `002fbcb`. The model and fallback now check complete numeric runs, account and registry IDs, email addresses and references. Babel validates grouped money with attached currency. Added generated checks for clipped values and nine grouping styles.
- 21.11.2026 · Codex · Merged `90d9701` and `4b1cc42`, retained configured routing and measured both engines on dev. Final product merge `c2bf060`.
- 21.11.2026 · Codex · merged the config-driven extraction baseline (`4b1cc42`) into the evaluation branch for the final training and corpus checks.
- 21.11.2026 · Codex · added training checks for empty or mislabelled positive references. The negative output check now distinguishes a zero-byte prediction from an empty JSON object.
- 21.11.2026 · Codex · Added the local PDF viewer and start scripts for #11 in `d1c9749`. Browser uploads and ZIP downloads matched the CLI for all three document classes, a scanned appeal and an unrelated PDF.
- 21.11.2026 · Codex · Merged the GUI baseline through `ac78d2d` into the OCR branch. Added unreadable-scan diagnostics, signature ownership checks, labelled account evidence, a RapidOCR worker deadline, and a checksum-verified local model source.
- 21.11.2026 · Codex · Integrated the corpus and macro-F1 harness from `3210643`. The OCR comparison uses the frozen extraction rules from `865b1ea`.
- 21.11.2026 · Codex · Restored detached receipt rows, checked booked debit accounts, and bound numbered grantors to signing officers. Recorded development and held-out aggregate metrics in the draft PR for `feat/real-poa-transfers`.
