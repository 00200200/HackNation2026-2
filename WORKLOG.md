# Worklog

Shared state of the project. Rules: `CLAUDE.md` → Worklog.

## Now

The integration branch combines real-layout appeal, grant and transfer rules with a configurable
OpenAI-compatible model engine. The default CLI and GUI run locally with the three endpoint
variables unset. Keyed runs can use a second OCR reading and recover a failed document with local rules.

The opt-in small-model profile uses Mistral’s regional API, compact source spans and bounded PDF workers. [Provider comparison](docs/small-model-providers.md)

## Last eval

The measured Ministral 3B profile uses the integrated rules, evidence-gated routing, selective native gap filling and first-charge verification. Against the rules at `eabbb31`, it raised strict micro F1 on the 91-PDF development pool from .5858 to .7146. A fresh 150-PDF CLI run took 335.64 seconds and scored .7208 micro F1 on its 91-PDF development subset. All 196 organizer training outputs matched the rules byte for byte in keyed and keyless runs. [Per-field results and timing](evals/results/small-model.json)

The full synthetic run matched 196/196 CLI outputs against the baseline by path, class and bytes,
including 16 empty negatives. The field report matched all 2,316 fields. Training micro F1 and the
cases 51–60 regression score were both 1.000. [Full training run](evals/results/latest.json)

These runs used local rules with the three endpoint variables unset. The two local datasets contain real documents and use whole-case splits. Corpus 1 contributes all 39 development PDFs, including its previously evaluated split. Corpus 2 contributes 39 development PDFs from 14 cases. Its 60 test PDFs are reserved for the merged system. The organizer supplied a separate set of 30 labelled scans, ten per target class, in revision `0b360a9`.

| Dataset | PDFs | Micro F1 | Macro F1 by class | Appeal | Power of attorney | Transfer | Correct routes (appeal / power / transfer) | Empty negatives | Wall s/PDF |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Local corpus 1, all | 39 | 0.6307 | 0.6607 | 0.6016 | 0.9189 | 0.4615 | 12/13 / 6/6 / 4/9 | 11/11 | 7.39 |
| Local corpus 2, dev | 39 | 0.6045 | 0.5662 | 0.6008 | 0.9462 | 0.1515 | 12/13 / 5/5 / 1/10 | 11/11 | 6.33 |
| Organizer scans | 30 | 0.6852 | 0.6023 | 0.6123 | 1.0000 | 0.1944 | 9/10 / 10/10 / 2/10 | n/a | 3.69 |

[Grant development measurements](evals/results/poa-development.json) · [Organizer scan aggregate](evals/results/organizer-scans.json)

## Next

| Item | Owner |
|---|---|
| Obtain an EU/EEA-only processing commitment for Mistral or deploy the same weights within the EEA | Deployment |
| Score corpus 2 test once after the class rules and small-model profile are integrated | Coordinator |
| Improve receipt routing and recover damaged party names on development inputs | Open |
| Confirm the organizer’s F1 formula and Stage II weights with UZP | Open |

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

- 21.11.2026 · Codex · Added native span output for small models, local source validation and a bounded parallel CLI. Verified the native schema on the quantized local model and both regional API releases.

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
- 21.11.2026 · Codex · Recovered appeal parties from detached labels and joint lists, scoped counsel to the appellant, and extracted procurement and first-charge facts from prose. Product `ee3c8ca`.

- 21.11.2026, local model evaluation checkpoint. The organizer registry supports five extraction modes and first-page model routing. The rules baseline scored 0.4444 micro-F1 on 22 dev PDFs, routed 11/15 positives and kept 7/7 negatives empty. The local model run and keyed default selection are pending.
- 21.11.2026 · Codex · Merged the GUI baseline through `ac78d2d` into the OCR branch. Added unreadable-scan diagnostics, signature ownership checks, labelled account evidence, a RapidOCR worker deadline, and a checksum-verified local model source.
- 21.11.2026 · Codex · Integrated the corpus and macro-F1 harness from `3210643`. The OCR comparison uses the frozen extraction rules from `865b1ea`.
- 21.11.2026 · Codex · Measured T0, T1, T1 with PNG input, R and TR on the dev cases. The hybrid gain was 0.0133, below the 0.0300 gate. Selected `tesseract-dpi` and kept RapidOCR optional.
- 21.11.2026 · Codex · Restored detached receipt rows, checked booked debit accounts, and bound numbered grantors to signing officers. Recorded development and held-out aggregate metrics in the draft PR for `feat/real-poa-transfers`.

- 21.11.2026 · Codex · Scoped the OCR rules on `feat/ocr-engine` to recognized text after the review of `c222716`. Added document-level checks for unreadable scans and regression tests for mixed PDFs.
- 21.11.2026 · Codex · Added a native PDF snapshot from `3210643` to check the new page-provenance rules in `2a500e4`. All 175 cases match, including 24 that differed at `c222716`. The ordinary CLI still matches class, path and bytes on all 196 organizer PDFs.
- 21.11.2026 · Codex · After `f1aa51b`, fixed spelled-out page counters and recognition of scanned bodies inside wide margins. The default-engine recheck is recorded in `evals/results/ocr-engines.json` under `provenance_check`, with the dev harness aggregate in [the frozen OCR report](https://github.com/00200200/HackNation2026-2/blob/5c4eff29d5872d64845ec533a3df0af9ba174740/evals/results/corpus-latest.json).
- 21.11.2026 · Codex · Repaired receipt role, date and identifier precedence and grant ownership. Added a 237-document native comparison against the integration base and recorded paired development scores and one held-out measurement on PR #20.
- 21.11.2026 · Codex · Preserved execution dates and completed receipts with status fields or complaint notices. Compared 42 additional native documents with integration base `e051dfa` and preserved internal periods in printed transaction references.

- 21.11.2026 · Codex · Merged the default explicit-DPI OCR engine at `b0a640f`. Before the appeal review fixes, dev micro F1 was 0.6944 and appeal F1 was 0.7811. Added regression coverage for filing evidence, party and counsel ownership, procurement labels and the first dated act.
- 21.11.2026 · Codex · Merged OCR page provenance through `5c4eff2` into the appeal fixes. Verified 155 invented differential inputs and 175 native PDFs against integration base `3210643`, with each intentional correction recorded by input and field. All 196 training PDFs retained the same routing, paths and bytes, and all 873 tests passed.

- 21.11.2026 · Merged the OCR integration at `e051dfa` and selected model-first extraction with rules filling gaps and model routing on rule rejection. On 22 dev PDFs, DeepSeek Flash with two OCR readings scored 0.6951 micro-F1 against 0.4356 for rules.
- 21.11.2026 · Codex · Integrated PRs #20, #18 and #22, verified training byte parity and measured both dev corpora at `d177cbc7`. Refreshed organizer revision `0b360a9` in `cf98ef3` and verified synthetic training and the dedicated scan evaluation at `8d79e66`.

- 21.11.2026 · Codex · Merged integrated rules at `21737c1`. The Ministral profile now checks the document’s own heading before fallback routing, limits native gap calls to missing parties or payment facts, and can verify the first allegation in one short request. On corpus 2 dev, eight targeted requests added four correct fields in a paired comparison.
- 21.11.2026 · Codex · Fixed the execution-date regression reported on PR #23, added three native receipts with baseline outputs, and recognized three additional completed payment statuses. All 196 training files matched the baseline byte for byte at `ee6c36e`. The clean training run scored 1.000 micro F1 and the 30 organizer scans scored 0.5633 micro F1.

- 21.11.2026 · Codex · Recovered officers, multiple appointments and register digits on scanned grants, and named signers from embedded certificates on real grants. All 10 organizer grants matched exactly in rules-only mode.

- 21.11.2026 · Codex · Synced the small-model branch with main at `5297660`, including scanned grant extraction and the bank execution-date rules.
- 21.11.2026 · Codex · Verified training on the clean merge `fb08cd7` and on `main` at `5297660`. Both scored 1.000 micro F1 and produced identical paths and bytes for all 196 PDFs, including all 16 empty negative outputs.

- 21.11.2026 · Codex · Verified the merge at `fb08cd7` against `main` at `5297660`. The keyless CLI matched all 196 training outputs by path and bytes, with micro F1 1.000. On 30 organizer scans, both scored 0.6852 micro F1. Main took 9.65 s/PDF with default settings. The first branch run timed out in Polish OCR on the last PDF. The completed branch retry at `37d6352` used `OMP_THREAD_LIMIT=1` and took 3.69 s/PDF.
- 21.11.2026 · Codex · Required the dated execution statement to name the payment. Added the reviewer's copy-of-receipt case, an archival request and a transfer executed before booking. All 196 training outputs at `36afcb7` matched the baseline byte for byte, and full training scored 1.000 micro F1. The organizer scan run exhausted shared disk space while writing the 30th output. The table retains the earlier scan measurement.
- 21.11.2026 · Codex · Merged main through `791dd00`. On the reviewer’s invented PDFs, the regional rules-first profile recovered the date, amount, transaction reference and title on four completed receipts, and the printed full attorney name on three grants. Five negative controls stayed empty. The previous corpus measurements document the earlier product revisions.
