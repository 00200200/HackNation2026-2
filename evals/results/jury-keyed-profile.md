# Jury profile evaluation

Release commit `45067966f858243cf2c761bf0151ab6fb789e954` combines the jury profile with main at `b2fd9c6`. Its engine fingerprint is `71b841f48a8b5fbebe9607d56e99e0e521480b8cd2f51cf922045810e0ef51e1`. Keyed runs used `ministral-3b-2512` on Mistral’s EU endpoint. The release preserves populated rule values and can request grounded evidence for eligible missing fields. Measurements were collected on 22 November 2026.

## Merged release gates

For untouched gold, the reference is exactly what the organizer committed. The second convention restores country-code prefixes visibly printed in the PDFs. UZP F1 pools field matches using the organizer’s counting rules and the project’s string comparator. Strict F1 includes null matches, compares normalized leaves and counts a wrong replacement as both a false positive and a false negative. Exact counts compare the whole JSON structure with the reference. Byte parity compares the actual serialized files from the two profiles, independently of either reference.

| Run | PDFs | UZP, untouched | Strict, untouched | Exact, untouched | UZP, printed accounts | Strict, printed accounts | Exact, printed accounts |
|---|---:|---:|---:|---:|---:|---:|---:|
| Training, rules | 196 | 0.975806 | 0.958549 | 148 | 1.000000 | 1.000000 | 196 |
| Training, keyed | 196 | 0.975806 | 0.958549 | 148 | 1.000000 | 1.000000 | 196 |
| 30 scans, one keyed batch | 30 | 1.000000 | 0.997423 | 29 | 1.000000 | 0.997423 | 29 |
| 30 scans, isolated serial | 30 | 1.000000 | 0.997423 | 29 | 1.000000 | 0.997423 | 29 |

The untouched training gold omits printed account prefixes from 48 payer and 48 payee values across 48 documents. The corrected references restore those 96 printed prefixes. All 30 scan references matched the JSON read directly from the committed Git objects.
Keyed training matched the fresh keyless main output byte for byte in **196/196 files**.
The only structural mismatch on the serial scan run was a transfer title. It matched under the UZP long-text comparator and differed under strict normalization.
Serial and batch scan outputs matched byte for byte in 30/30 files.

## Merged runtime and API use

| Run | PDFs | Wall, s | PDF p50 / p95, s | HTTP attempts | Calls/PDF | HTTP p50 / p95, s | Input / cached / output tokens | Est. USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Training, rules | 196 | 63.1 | 0.21 / 1.24 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Training, keyed | 196 | 41.9 | 0.12 / 0.78 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| 30 scans, one keyed batch | 30 | 105.4 | 4.15 / 16.58 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| 30 scans, isolated serial | 30 | 553.2 | 7.43 / 15.29 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |

PDF time covers processing in one worker. Batch wall time also includes interpreter startup, scheduling, writing and any sibling reconciliation. The serial run measures 30 separate one-PDF CLI processes with `--jobs 1` and therefore includes all 30 startups. HTTP percentiles use the nearest rank over requests. Cached tokens are part of total input. Estimated cost uses $0.11 per million uncached input or output tokens and $0.011 per million cached input tokens. It covers responses with reported usage. [Model rates](https://docs.mistral.ai/inference/pricing) · [EU regional rate](https://docs.mistral.ai/inference/regional-inference)

- Training, keyed selected 0 documents, reached HTTP for 0 and changed 0 during enrichment. Endpoint failures before / after HTTP were 0 / 0. The pipeline used rule recovery on 0.
- 30 scans, one keyed batch selected 0 documents, reached HTTP for 0 and changed 0 during enrichment. Endpoint failures before / after HTTP were 0 / 0. The pipeline used rule recovery on 0.
- 30 scans, isolated serial selected 0 documents, reached HTTP for 0 and changed 0 during enrichment. Endpoint failures before / after HTTP were 0 / 0. The pipeline used rule recovery on 0.

The keyed runs with zero API attempts exercised rule retention. Their eligible-field selector made no outbound requests.

### Post-reboot mixed150 on two vCPUs

The exact native command in `/opt/solution/RUN.md` used `--jobs 2` on rebooted Ubuntu 24.04.5 LTS, with two vCPUs and 5 GiB configured RAM (4,904 MiB usable). The local M1 host ran the project’s pinned Linux x86_64 wheels through Rosetta with Python 3.13.7. Wall time was **412.174 seconds (6 min 52 s)**. The CLI exited 0 and wrote all 150 expected JSON paths, preserving 147 repeated stems beyond the unique stems.

All 150 files matched the earlier guest’s keyless outputs byte for byte (source fingerprint `8c4b2b3f7c3b5168f7f633cb12fde5931794371c15d8a302a72a53c5bb1c7aae`). The earlier guest baseline took 1,094.077 seconds on a different source revision and run. Against the printed-account convention, UZP F1 was **1.000000**, strict F1 was **0.999472**, and 149/150 records were exact. The native subset was 120/120 exact with UZP and strict F1 of 1.000000. The scan subset was 29/30 exact with UZP 1.000000 and strict 0.997423. The post-reboot command ran without instrumentation, so HTTP counts, request percentiles, token usage and cost are unmeasured for this run.

A separate two-file smoke check used the same input stem in two folders. Both keyed (32.748 s) and genuinely keyless (13.941 s) runs exited 0 and wrote the expected transfer and empty negative JSON in their respective folders.

## Completed comparisons before the merge

The historical rules and model-first (LR) comparators use main `027e2d6`. The rules-first jury (RL) comparison uses fingerprint `0f640d6e`. The merged release was measured on public organizer gates. The spent-panel and development measurements below describe earlier snapshots. Time-limited OCR rereads can differ under load, including between the 30-scan batch and the same scans within mixed150. “Stopped on integration” means the requested run had no completed measurement when integration superseded the earlier suite. A dash denotes unavailable telemetry.

| Cohort | PDFs | Rules UZP / strict | LR UZP / strict | RL UZP / strict | Exact, rules / LR / RL |
|---|---:|---:|---:|---:|---:|
| Organizer training | 196 | 1.0000 / 1.0000 | 0.9828 / 0.9640 | 1.0000 / 1.0000 | 196 / 149 / 196 |
| Organizer scans | 30 | 0.9819 / 0.9791 | 0.8964 / 0.8440 | 0.9785 / 0.9660 | 26 / 10 / 21 |
| Mixed 150 | 150 | 1.0000 / 0.9995 | 0.9675 / 0.9375 | 0.9994 / 0.9984 | 149 / 93 / 148 |
| Layout variants | 240 | 0.9542 / 0.9295 | stopped on integration | stopped on integration | 136 / — / — |
| Synthetic cases, development | 112 | stopped on integration | stopped on integration | stopped on integration | — / — / — |
| Corpus 1, development | 22 | 0.9256 / 0.8780 | stopped on integration | 0.9221 / 0.8740 | 10 / — / 10 |
| Corpus 2, development | 39 | 0.9244 / 0.8951 | stopped on integration | stopped on integration | 22 / — / — |

Historical training and mixed150 scores above use printed-account references. Pre-merge RL training matched main’s 196 outputs byte for byte. LR scored 0.982806 UZP on those records. RL mixed150 substituted first-act ID 9 for 6 and its associated description on one appeal scan. Those two fields account for the UZP loss. The only recorded enrichment was worker completion 129 and the affected scan was input 129. The worker observer recorded aggregate changes, so this is evidence of a model-induced substitution without a field-specific before/after trace. Both standalone RL scan checks returned ID 9 on that example. The LR standalone run returned 6.

### Spent panels

Correct counts on the first-act panel are reason ID / date / complete record. Counsel counts are flag / name / firm / email / complete record. Firm uses the UZP comparator. The panels were scored on the pre-merge snapshots above.

| Slice | PDFs | Rules | LR | RL |
|---|---:|---:|---:|---:|
| First-act panel, native control | 6 | 4 / 3 / 3 | 4 / 3 / 3 | 4 / 3 / 3 |
| First-act panel, native positive | 12 | 2 / 2 / 1 | 2 / 2 / 1 | 2 / 2 / 1 |
| First-act panel, scan control | 6 | 4 / 3 / 3 | 4 / 3 / 3 | 4 / 3 / 3 |
| First-act panel, scan positive | 12 | 2 / 2 / 1 | 2 / 2 / 1 | 2 / 2 / 1 |
| Counsel panel, native adverse | 8 | 8 / 8 / 8 / 8 / 8 | 6 / 6 / 8 / 8 / 6 | 8 / 8 / 8 / 8 / 8 |
| Counsel panel, native represented | 11 | 4 / 5 / 4 / 7 / 1 | 3 / 6 / 5 / 9 / 1 | 4 / 5 / 4 / 7 / 1 |
| Counsel panel, scan adverse | 8 | 8 / 8 / 8 / 8 / 8 | 2 / 4 / 8 / 8 / 2 | 8 / 8 / 8 / 8 / 8 |
| Counsel panel, scan represented | 12 | 5 / 6 / 4 / 6 / 1 | 3 / 9 / 9 / 12 / 2 | 5 / 6 / 4 / 6 / 1 |

All three profiles matched every known printed counsel field and its representation flag on 1/11 represented native records and 2/12 represented scans. RL contact precision was 7/7 non-null name, firm or email assignments on native records and 8/10 on scans, recovering 7/24 and 8/27 printed contacts. Both incorrect represented contact assignments were firms. On adverse records, rules and RL made zero wrong-owner contact assignments across eight native and eight scanned views. LR assigned the wrong name in two native and four scanned views.

A separate first-act diagnostic at `0f640d6e` found no first clause on 14/36 views and a locked or ineligible reason on 14/36. Of eight first-act requests, six abstained. The other two repeated the wrong baseline ID with accepted quotes. Two date proposals failed page or event grounding. Two additional views requested other fields. The diagnostic ran for 120.8 seconds and observed 10 HTTP 200 responses. The diagnostic matched the original panel output bytes on 35/36 views and matched reason ID and date on 36/36. Its usage is excluded from the scored cohort totals.

### Historical runtime

| Cohort and profile | PDFs | Wall, s | PDF p50 / p95, s | HTTP attempts | Calls/PDF | HTTP p50 / p95, s | Input / cached / output tokens | Est. USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Organizer training — Rules | 196 | 52.3 | — | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Organizer training — Main LR | 196 | 608.9 | — | 200 × 339 | 1.730 | — | — | — |
| Organizer training — Jury RL | 196 | 176.0 | 0.52 / 3.63 | 200 × 43 | 0.219 | 0.62 / 0.99 | 24,780 / 23,304 / 2,541 | 0.00070 |
| Organizer scans — Rules | 30 | 364.1 | — | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Organizer scans — Main LR | 30 | 654.4 | 17.52 / 278.74 | 200 × 55 | 1.833 | 1.96 / 4.55 | 195,679 / 126,160 / 27,048 | 0.01201 |
| Organizer scans — Jury RL | 30 | 393.1 | 17.81 / 52.16 | 200 × 9 | 0.300 | 0.59 / 0.66 | 4,758 / 4,056 / 290 | 0.00015 |
| Mixed 150 — Rules | 150 | 269.9 | — | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Mixed 150 — Main LR | 150 | 1784.5 | 4.78 / 252.23 | 200 × 267 | 1.780 | 1.95 / 4.67 | 799,903 / 558,568 / 139,556 | 0.04804 |
| Mixed 150 — Jury RL | 150 | 423.1 | 0.74 / 30.02 | 200 × 48 | 0.320 | 0.60 / 1.51 | 26,936 / 24,576 / 2,275 | 0.00078 |
| Layout variants — Rules | 240 | 510.1 | 0.15 / 10.83 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Corpus 1, development — Rules | 22 | 393.4 | 31.23 / 86.03 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Corpus 1, development — Jury RL | 22 | 265.4 | 15.38 / 55.45 | 200 × 6 | 0.273 | 0.57 / 0.88 | 4,149 / 1,224 / 466 | 0.00039 |
| Corpus 2, development — Rules | 39 | 311.6 | 9.23 / 56.43 | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| First-act panel — Rules | 36 | 43.8 | — | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| First-act panel — Main LR | 36 | 325.5 | — | 200 × 72 | 2.000 | — | — | — |
| First-act panel — Jury RL | 36 | 125.0 | 1.78 / 15.12 | 200 × 10 | 0.278 | 0.56 / 0.90 | 5,426 / 4,351 / 310 | 0.00020 |
| Counsel panel — Rules | 39 | 99.8 | — | 0 | 0.000 | — | 0 / 0 / 0 | 0.00000 |
| Counsel panel — Main LR | 39 | 437.1 | — | 200 × 78 | 2.000 | — | — | — |
| Counsel panel — Jury RL | 39 | 163.6 | 8.63 / 15.87 | 200 × 15 | 0.385 | 0.63 / 1.09 | 7,832 / 5,358 / 387 | 0.00037 |

The sibling diagnostic captured HTTP status and wall time for historical LR training and the two spent panels. It did not retain response token counts or request percentiles. The historical rules training, mixed and scan baselines from the same commit also lack worker percentiles.

### Additional pre-merge measurements

On the independent 24-PDF sole-trader mandate panel, main rules and RL `0f640d6e` both scored firm 4/10, proprietor 5/10, type and NIP 6/10, ordered signers 1/10 and complete record 1/10 on the positive records in each view. Neither attributed the attorney or firm as the principal person or signer. Both arms scored zero exact among the two controls in each view. NIP correctness rose from 1/2 to 2/2. A previously missing principal row gained a correctly null NIP in the same control’s native and scan views. Both already extracted the printed NIP on the other control. The model had no NIP field.

The grant panel took 99.6 seconds with rules, PDF p50/p95 0.74/12.44 seconds, and 102.7 seconds with RL, PDF p50/p95 1.12/12.49 seconds. The ten HTTP 200 calls averaged 0.417/PDF with HTTP p50/p95 0.45/0.76 seconds. Of 5,124 input tokens, 3,560 were cached. There were 164 output tokens. Estimated cost was $0.000229. Six records changed during enrichment.

The intervening date-validation snapshot `522946a4` preserved 196/196 training bytes and scored 0.978512 UZP / 0.965969 strict on 30 untouched scans, 21 exact. Training used 43 HTTP 200 calls in 147.5 seconds and the scans used nine in 397.6 seconds. The subsequent populated-field guards at `e9fdc752` and `71d8c75c` each retained all 196 training outputs byte for byte with zero API calls, in 116.8 and 79.9 seconds respectively. A complete keyless 30-scan run on `027e2d6` under lighter load later scored 1.000000 UZP in 225.9 seconds.

## Reproduction

The local measurements used an eight-core arm64 Mac shared with other workloads. The paired release CLI commands ran sequentially with `--jobs 2`, except for the isolated one-PDF serial scan invocations. This is a worker setting. The local host uses OS scheduling across its available cores. The actual two-vCPU guest timing is identified separately when available.

Use `python -m kio2json --jobs 2 --input INPUT --output OUTPUT` with neutral staged filenames. For the serial scan run, stage each scan in a separate input and use `--jobs 1`. For rules, clear the three endpoint variables. The keyed runs set only `KIO_LLM_BASE_URL=https://api.eu.mistral.ai/v1`, `KIO_LLM_MODEL=ministral-3b-2512` and the API key obtained from the local environment. Runtime observation collected status codes, numeric timing, usage and document-event counts.

Training uses the complete organizer inventory, with deterministic neutral names, and negative documents require an empty JSON object. The 150-PDF mix contains the three native positives in each of `przyklad_01`–`przyklad_40` plus all 30 organizer scans. Real corpora select the `dev` entries in each `SPLIT.json`. The 60 synthetic variant cases use seed 63059 in 12 five-case batches. Their SHA-256 is `53414e5959d93426f1553cc36fcbe86968fca23edb80a959740654790b20dd03`. The first-act panels use seed 111 and 300 dpi grayscale scans. The counsel rendered scans also use 300 dpi, retaining the scan-only record.

Engine fingerprints hash sorted relative paths in `kio2json/*.py` and `config/classes/*.toml`. For each file the digest input is its UTF-8 path, a NUL and its 32-byte SHA-256. The merged release keyless control is `38dc48d631f79abf41891affbfa8cf4265b9b94c3ded0ef3d8acca2ee196855d`. The release and historical jury hashes are reported above.
