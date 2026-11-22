# Worklog

Shared state of the project. Rules: `CLAUDE.md` → Worklog.

## Now

The integration branch combines real-layout appeal, grant and transfer rules with a configurable
OpenAI-compatible model engine. The default CLI and GUI run locally with the three endpoint
variables unset. Keyed runs can use a second OCR reading and recover a failed document with local rules.

The opt-in small-model profile uses Mistral’s regional API, compact source spans and bounded PDF workers. [Provider comparison](docs/small-model-providers.md)

The batch CLI defaults to up to four PDF workers, with one thread per Tesseract instance and up to three concurrent page reads per PDF. The first OCR pass supplies layout word boxes, and optional OCR has up to 300 seconds per document. A shared batch cutoff stops rereads after 27 minutes for 150 PDFs. Required OCR has a 180-second page watchdog and can retry a stalled page once at 150 dpi.

The local viewer flags disagreements between an appeal, its mandate and its receipt. The CLI and viewer can use independently printed sibling values to repair a damaged reading within one case folder.

The grant certificate and board-stamp readers share the copy-attestation check so that a certifier cannot be counted as the issuing officer.

Public landing https://doc2json.pl (`frontend/`, static nginx, monochrome) runs on the team VPS as `doc2json-web`
behind the faktczyfejk Caddy; deploy in `docs/deploy.md`. Its upload calls `kio2json.web_api` (`/api/extract`, rules engine, no keys) in the `doc2json-api` container.

The jury can run the batch CLI and upload UI locally with the root Compose file. [Docker instructions](README.md#run-with-docker-compose)

The final deck (12 slides) and a two-minute demo script are in `docs/pitch/`. The form fields and the jury's commands are in `docs/submission.md`. [Number sources](docs/pitch/README.md)

The evaluation VM kit installs the rules CLI under `/opt/solution`. The VM owner still needs to run the Ubuntu offline and reboot checks. [Deployment steps](README.md#deploy-on-the-evaluation-vm)

A new document class needs one TOML file. `--classes PATH` and `--enable ID` add classes to the three organizer
classes in the CLI and viewer. A class file can declare weighted routing cues with a threshold and named checks
(`nip`, `regon`, `pesel`, `iban`, `date_range`, `one_of`). `python -m kio2json.classes new` writes a class file from a sample PDF.
The viewer lists the loaded classes, the cue that chose each class, failed checks and each field's source;
`--explain DIR` writes the same trace to a folder outside `--output`. Example: `examples/classes/accession.toml`.

## Last eval

The scan stress eval (`evals/scan_stress.py`, #81) re-rendered the 30 organizer scans from seed 2026 into 16 variants, the delivered files and 15 re-renders, and ran the CLI once per variant as the jury does: neutral case folders, no model endpoint, the default four workers. The product code was main `a84258d`, scored with the issue #59 metric at 0.80 s per document on a 10-core Mac (the dev machine, not jury hardware). The delivered scans scored 1.000 UZP (0.997 strict). The re-renders scored 0.791 to 0.965: 200 dpi grey JPEG 0.933, 150 dpi 0.922, 300 dpi 0.965, one-bit 0.882 (200 dpi) and 0.904 (300 dpi), skew from −3° to +3° 0.791 to 0.901, noise 0.931, three mixed sets 0.825 to 0.876. Of the F1 lost, routing errors account for 0.000 to 0.099 and field errors for 0.033 to 0.125. 54 of the 60 misrouted documents are transfers: receipt 0007 came back as `{}` in 13 of the 15 re-renders, 0008 in 10, 0004 in 9 and 0003 in 8. Why each receipt failed, gate by gate, is in the #81 thread; the report records only where each document was routed. [Per-variant report](evals/results/scan-stress.json)

Native two-column appeal field F1 rose from 0.4064 to 0.9717 across ten generated cases. On the five held-out cases, native F1 rose from 0.3387 to 0.9700 and forced-Tesseract F1 rose from 0.8619 to 0.8925. [Per-field, organizer and private aggregate results](evals/results/two-column-appeals.json)

On the 240 seeded PDFs, UZP field micro F1 rose from 0.2960 on #69 to **0.8948** on the robustness checkpoint. The classifier routed 170/180 positives, including all 60 appeals, and returned `{}` on all 60 negatives. The control with #78’s account and JSON conventions scored 0.3179. The ten remaining routing misses were alternative-format transfers.

Main incorporated this classifier and the separate transfer-format fix in #89. The integrated rerun scored **0.9125** and routed **180/180** positives. Two-column appeals scored 0.4064 field F1 despite all ten routing correctly. All 196 organizer training outputs matched the control byte for byte and 29/30 organizer scans matched their references exactly. Private UZP F1 was 0.9247 on corpus 1 all and 0.9244 on corpus 2 dev. [Profile and gate comparisons](evals/results/variant-robustness.json)

The fixed-seed benchmark re-rendered the facts from all 60 synthetic cases and generated 60 look-alike negatives. The keyless extractor was main at `3eccb41`, scored with the issue #59 metric. The initial `f7f3ee9` run had the same dataset digest and field counts.

| Dataset | PDFs | UZP micro F1 | Strict micro F1 | Appeal F1 | Power F1 | Transfer F1 | Empty negatives |
|---|---:|---:|---:|---:|---:|---:|---:|
| Generated layouts | 240 | 0.2960 | 0.2860 | 0.0000 | 0.5529 | 0.6617 | 60/60 |

Weakest positive profiles were label synonyms (0.1693), alternative formats (0.2083) and two columns (0.2089). Appeal F1 was zero in all six profiles. The benchmark uses short, newly authored forms built from the training facts. Profile scores also reflect their different case samples. [Original baseline and routing-only checkpoint](evals/results/variant-robustness.json)

The empty-object writer preserved all 180 positive training files byte for byte and wrote `{}\n` for all 16 negatives. Keeping printed country codes then changed two fields in each of 48 transfers. The comparison used local rules and two PDF workers. The integrated run includes the UZP scorer and the fix for a printed underline in a recipient account cell.

| Dataset | Main strict `f7f3ee9` | Candidate strict `41903d1` | Integrated strict | Integrated UZP |
|---|---:|---:|---:|---:|
| Training, original references | 1.0000 | 0.9585 | 0.9585 | 0.9758 |
| Training, corrected references | 0.9585 | 1.0000 | 1.0000 | 1.0000 |
| Organizer scans (30) | 0.9766 | 0.9974 | 0.9974 | 1.0000 |
| Corpus 1 all (39) | 0.8889 | 0.8873 | 0.8880 | 0.9212 |
| Corpus 2 dev (39) | 0.8926 | 0.8926 | 0.8951 | 0.9244 |

The first main scan batch required one isolated OCR timeout retry on the shared host. All 196 training files matched byte for byte before and after integration. The jury CI checker matched all 90 training entries against corrected references. [Field counts and expected changes by case](evals/results/p0-conventions.json)

Main `f7f3ee9` ran with local rules and two PDF workers. Both scores below use the same predictions and original references. The difference is UZP F1 minus historical strict F1.

| Dataset | PDFs | UZP micro F1 | Strict micro F1 | Difference |
|---|---:|---:|---:|---:|
| Synthetic training | 196 | 1.0000 | 1.0000 | +0.0000 |
| Organizer scans | 30 | 0.9869 | 0.9740 | +0.0129 |
| Corpus 1 all | 39 | 0.9212 | 0.8889 | +0.0323 |
| Corpus 2 dev | 39 | 0.9221 | 0.8926 | +0.0295 |

PR #55 changed two corpus 1 appeals, trimming one field and setting three to null. Its UZP F1 rose from 0.9212 to 0.9247. The other three sets kept identical predictions.

The fresh scan batch routed 29/30 documents, including nine of ten transfers. The earlier strict score of 0.9974 below used a batch with all 30 routed correctly.

The corpus 1 development subset (22 PDFs) scored 0.9221 UZP and 0.8740 strict. [Counts and PR #55 comparison](evals/results/uzp-metric.json)

Round 3 raised rules-only micro F1 from 0.8607 to 0.8900 on corpus 1 (39 PDFs) and from 0.8789 to 0.8926 on corpus 2 dev (39 PDFs). Four recovered payment receipts brought routing to 78/78, including the 22 negatives. One appeal timed out in the initial corpus 1 run (0.8812) and returned its baseline bytes in an isolated rerun. All 30 organizer scan outputs and 196 synthetic training outputs matched the baseline byte for byte. Organizer scans scored 0.9974 with 29/30 exact, and synthetic F1 was 1.000. [Field counts, intermediate runs and timing](evals/results/round3.json)

In the earlier small-model experiment the profile used evidence-gated routing, selective native gap filling and first-charge verification. Against the rules at `eabbb31`, it raised strict micro F1 on the 91-PDF development pool from .5858 to .7146. A fresh 150-PDF CLI run took 335.64 seconds and scored .7208 micro F1 on its 91-PDF development subset. All 196 organizer training outputs matched the rules byte for byte in keyed and keyless runs. [Per-field results and timing](evals/results/small-model.json)

The full synthetic run matched 196/196 CLI outputs against the baseline by path, class and bytes,
including 16 empty negatives. The field report matched all 2,316 fields. Training micro F1 and the
cases 51–60 regression score were both 1.000. [Full training run](evals/results/latest.json)

Revision `ca2975392` was evaluated with local rules and with the documented live Ministral 3B profile. The two local datasets contain real documents and use whole-case splits. Corpus 1 contributes all 39 development PDFs, including its previously evaluated split. Corpus 2 contributes 39 development PDFs from 14 cases. Its 60 test PDFs are reserved for the merged system. The organizer supplied a separate set of 30 labelled scans, ten per target class, in revision `0b360a9`.

| Dataset | Profile | Micro F1 | Macro F1 | Appeal F1 | Power F1 | Transfer F1 | Exact A/P/T | Empty negatives | Wall s/PDF |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| Synthetic training | Rules | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 60/60/60 | 16/16 | 0.04 |
| Synthetic training | Ministral 3B | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 60/60/60 | 16/16 | 0.05 |
| Organizer scans | Rules | 0.9974 | 0.9944 | 1.0000 | 1.0000 | 0.9833 | 10/10/9 | — | 1.20 |
| Organizer scans | Ministral 3B | 0.9974 | 0.9944 | 1.0000 | 1.0000 | 0.9833 | 10/10/9 | — | 1.50 |
| Corpus 1 all | Rules | 0.8607 | 0.7785 | 0.8910 | 0.9558 | 0.4889 | 3/2/0 | 11/11 | 1.10 |
| Corpus 1 all | Ministral 3B | 0.8695 | 0.8254 | 0.8910 | 0.9558 | 0.6296 | 3/2/1 | 11/11 | 1.56 |
| Corpus 2 dev | Rules | 0.8789 | 0.8951 | 0.8713 | 0.9895 | 0.8246 | 2/4/4 | 11/11 | 0.76 |
| Corpus 2 dev | Ministral 3B | 0.8920 | 0.9124 | 0.8811 | 0.9895 | 0.8667 | 2/4/4 | 11/11 | 0.75 |

On corpus 1 the model raised transfer F1 by 0.1407. On corpus 2 dev it raised transfer F1 by 0.0421 and appeal F1 by 0.0099. Both profiles matched all ten organizer appeals and powers of attorney, and nine of ten transfer confirmations. [Combined measurements](evals/results/round2-integration.json)

Exact counts compare the complete JSON, including list order. A/P/T denotes appeals, powers and transfers. Each private set includes 11 unrelated PDFs. Earlier appeal measurements are available separately. [Real appeal round](evals/results/appeal-real-development.json)

[Earlier appeal development measurements](evals/results/appeal-scan-development.json) · [Earlier grant development measurements](evals/results/poa-development.json) · [Organizer scan aggregate](evals/results/organizer-scans.json)

The scanned-transfer rules routed 5/5 organizer dev transfers and 3/5 on the single organizer holdout, along with 4/4 and 9/10 transfers on the two private dev partitions. The synthetic regression still matched all 196 outputs byte for byte. [Per-step and holdout aggregates](evals/results/scanned-transfers.json)

On all 30 organizer development scans, the rules routed 10/10 transfer confirmations. Nine matched every field literally (59/60 fields, transfer F1 0.9833). The outstanding title contains a severely degraded name and abbreviation. Across all three classes the run averaged 9.23 s/PDF on the shared Apple M1, with a maximum of 19.02 s. With the integrated power-of-attorney rules, micro F1 reached 0.6312 on corpus 1 all, 0.7160 on its dev subset and 0.6816 on corpus 2 dev. [Round 2 measurements](evals/results/scanned-transfers-round2.json)

The subsequent real-grant round found six labelled grants in corpus 1 and five in corpus 2 dev.
On these development documents, grant field F1 rose to 0.9558 and 0.9895 respectively.
Two and four grant JSONs matched exactly. The ten organizer grants remained exact.

## Next

| Item | Owner |
|---|---|
| Rehearse the installed solution on the organizer VM before access ends at 11:00 on 22 November. Check the offline run, reboot, and two-vCPU timing using [the VM instructions](data/uzp/VM.md). | 00200200 (VM request, credentials, final deployment, 2-vCPU timing and F1, rehearsal on the VM, per the #66 thread); Dominik-Galus built the kit (PR #77) |
| If the team keeps the Ministral profile (#38): obtain an EU/EEA-only processing commitment for Mistral or deploy the same weights within the EEA. UZP said no private hosting; UNCONFIRMED whether that rules out the second option, since upstream `VM.md` allows models and containers on the evaluation VM | Deployment |
| Score corpus 2 test once after the class rules and small-model profile are integrated | Coordinator |
| Improve receipt routing and recover damaged party names on development inputs | Open |
| Scan robustness (#81) and OCR-flecked titles (#102): tolerant cue matching for transfer receipts and for appeal and mandate titles. Branch `fix/ocr-tolerant-cues`, stacked on the stress eval (`feat/scan-stress`) | Claude, in progress |
| Confirm the unresolved VM, model hosting and scoring details listed in [the task brief](docs/task/BRIEF.md). | Open |
| Promote HackNation2026 PR #48 to `prod` after the faktczyfejk demo, so the doc2json.pl Caddy block survives a redeploy | Open |
| Run `docker compose run --rm cli` and `docker compose up gui` once on an amd64 Docker host and compare the CLI output with `python -m kio2json` (no Docker on the dev Macs; hosted Actions are blocked by billing, #67) | Open |

<!-- Superseded by the UZP scoring decision below. Previous open item:
| Confirm the organizer’s F1 formula and Stage II weights with UZP | Open |
-->

## Decisions

- 22.11.2026: UZP micro F1 is the primary extraction score. Compare the five long fields at an inclusive 80% threshold using RapidFuzz normalized Levenshtein until UZP names its similarity function. When the reference contains a value, both a wrong guess and a null cost one error. Keep supported OCR text, especially when trimming noise could recover a match. Abstaining helps when the reference is absent. [Organizer rules](https://github.com/00200200/HackNation2026-2/issues/59)

- 21.11.2026: use the tesserocr wheel, Polish fast model and an English reread of ambiguous e-mail tokens. The
  model-data wheel verifies the upstream SHA-256 checksums at install time.
- 21.11.2026: Python 3.13, uv, pydantic-ai 2.71.0. Cases 51–60 are the holdout for prompt work.
- 21.11.2026: rules first. Every training target PDF has a text layer and the rules match all reference JSONs, so
  an OCR or model change has to beat this baseline in the eval. The baseline's rules have seen cases 51-60; a fresh case split is needed to measure generalization for work that builds on these rules.
- 21.11.2026: use the date and act stated together in the first charge. When its heading lacks a date, use
  the introductory sentence describing the dated act. In cases 01–39 that sentence supplies the reference reason.
- 21.11.2026 · UZP confirmed that unrelated PDFs produce `{}` and transfer account numbers keep their printed country code with all whitespace removed. The CLI and GUI use the same empty object for a failed PDF and report the failure separately. [Empty output](https://github.com/00200200/HackNation2026-2/issues/57) · [Account numbers](https://github.com/00200200/HackNation2026-2/issues/58)
- 21.11.2026: file, module and identifier names are English; the jury GUI, organizer's JSON keys and original file stems use Polish.
- 21.11.2026: delegated work and reviews (pre-commit review, pre-push judge) go to Codex workers through
  `/orchestrator`, not to Claude subagents.

## Log

- 22.11.2026 · Claude · Added `evals/scan_stress.py` and `make scan-stress` for #81: 16 fixed-seed variants of the 30 organizer scans (the delivered files and 15 re-renders), run as the jury runs the app and scored with the loss split into routing and field errors. Baseline on main `a84258d`, no product change: delivered 1.000, re-renders 0.791 to 0.965, and 54 of the 60 misrouted documents are transfers returned as `{}`. [Report](evals/results/scan-stress.json) · feat/scan-stress

- 22.11.2026 · Codex · Separated sole-trader identities, mandate signatures and challenged acts using the case-linked development split. [Field errors and split results](evals/results/case-mandates-appeals.md)

- 22.11.2026 · Codex · Added contracting-authority descriptions and inflected captions to the appeal party reader. Joint authority cards preserve the printed names, registry IDs and lead marker. [Caption measurements](evals/results/authority-captions.json)

- 22.11.2026 · Codex · Recovered role-labelled appeal cards with inflected captions and nearby party evidence. The paired PDF controls cover names, registry IDs and counsel attached to each appellant. [Development measurements](evals/results/appeal-party-headings.json)

- 22.11.2026 · Claude · Brought `docs/task/BRIEF.md` up to UZP's Discord answers (#64), the Regulamin (`docs/task/regulamin.pdf`) and the organizer's `VM.md`; refreshed `data/uzp` to `eadffbc` (adds `VM.md` only). In WORKLOG: recorded the `{}` and account-number decisions, put the VM row first, scoped the Ministral row to #38, split the UZP-answer issues into per-issue rows with their owners, flagged the eval's `negatives_empty` check and merged main and dropped the rows it finished (#60, #59, #61) · docs/brief-update

- 22.11.2026 · Claude · #62 classes from one TOML file (`--classes`, `--enable`, weighted cues, named checks, `python -m kio2json.classes new`), and the #40 trace from `feat/explain` (`--explain DIR`, viewer class list, routing cue, field sources). 1826 tests pass. The CLI wrote the same bytes as main `328f705` for all 226 organizer PDFs (196 training, 30 scans), and the full training eval at `853b230` scored 1.000 micro F1 with every target met · branch `claude/config-classes-case-ab8189`
- 22.11.2026 · Claude · A model quote for an account may now leave out the printed country code; the value must still carry it (`cited_account` grounds from the digits on, as NIP and KRS do for their prefix). Span-only output is unchanged. CLI outputs of the rules profile for all 226 PDFs of `data/uzp/dane` (196 training, 30 scans) matched main `257a6af` byte for byte. Branch `claude/model-quote-printed-pl`.

- 22.11.2026 · Codex · Integrated the signed judging criteria, VM instructions and UZP clarifications from #49 and refreshed the README visuals from #36 against recorded results.
- 21.11.2026 · Claude · presentation-style README with monochrome visuals in `docs/readme/`; previous README moved to `docs/readme/reference.md` · feat/docs

- 22.11.2026 · Codex · Raised the required page watchdog from 60 to 180 seconds and added one 150-dpi retry within the remaining OCR budget. Regression tests cover timeout recovery, immediate engine errors, budget exhaustion and word-box coordinates after resizing.

- 22.11.2026 · Codex · Added case warnings and opt-in sibling OCR repair for #61. All 304 keyless outputs matched main byte for byte. UZP F1 stayed at 0.9231 on corpus 1 all, 0.9221 on corpus 1 dev and 0.9244 on corpus 2 dev. Training scored 1.000 with 196 exact outputs. The 30 singleton scans had 29 exact outputs and UZP F1 of 1.000. [Paired case measurements](evals/results/case-siblings.json)

- 22.11.2026 · Codex · Grouped appeal and mandate word boxes by printed role and column. Added regressions for wrapped names, repeated stationery, extra appointees and principal-specific signatures.
- 22.11.2026 · Claude · #54 review follow-ups: the README names both PyPI hosts (`pypi.org`, `files.pythonhosted.org`) instead of "no other host"; `tests/test_batch_runtime.py` writes its fixture files as UTF-8, because a CP1252 Windows locale cannot encode the Polish literal in the worker fixture. `kio2json/` has no text-mode `open`, `read_text` or `write_text` without an encoding. 59 sites in `tests/` and 7 in `evals/` still use the locale default; they only matter for a Windows run of the tests, not for the Linux evaluation VM. `.gitattributes` marks the vendored `.traineddata` files binary so no checkout can rewrite them, and the stale `packaging/**` path filter is gone from `jury-batch.yml`. Merged `main` again (#74, `pdf_text.py` conflict: kept `OCRWord` and the tessdata constants).
- 22.11.2026 · Codex · Integrated the #73 x86-64 pin for both jury Compose services on `integrate/pr73`.
- 22.11.2026 · Claude · Docker follow-up stacked on #54: pinned the Compose image to `linux/amd64` (arm64 hosts cannot install `libsass` and `morfeusz2`), named the vendored Tesseract models as the one exception to "never commit model weights" in `CLAUDE.md`, corrected two README sentences and made `tests/test_tessdata.py` clear the `_language_dir` cache even when it fails. Not run in Docker.
- 22.11.2026 · Claude · Took over #54: merged `main` (`3eccb41`, with the Compose files from #68; `api.Dockerfile` has no `COPY packaging` line any more), reworded the README install sentence after CodeRabbit, fixed the Docker section's claim that the build downloads OCR data, rechecked at `d14da55` (ruff clean, 1738 tests, eval-quick 1.000). Fresh py3.13 venv: `pip install -r requirements.txt` from another directory rc=0, 80 packages, 520 MiB; its CLI and `uv run` wrote byte-identical JSON for `input/case1` and three organizer scans. Every pin has a manylinux x86_64 wheel; `libsass` and `morfeusz2` have no Linux aarch64 wheel, so an arm64 image build needs `platform: linux/amd64` (a compiler would not help; the Docker follow-up adds the pin). No Docker on this machine and GitHub Actions is blocked by billing, so container byte parity is still unchecked.
- 22.11.2026 · Claude · Handoff fix/install-deps (#44/#45): code done at de49710; fresh py3.13 venv `pip install -r requirements.txt` from another directory rc=0, 80 pkgs, site-packages 642 → 519 MiB (main: raw.githubusercontent.com timeout, 133 pkgs); make check 1704+2 passed; eval-quick 1.000 clean; CLI identical on cases 01/13/27/38/50. Left: judge PASS, stamp, push, PR.
- 21.11.2026 · Claude · #44/#45: vendored the pinned pol/eng tessdata in `kio2json/tessdata/` (SHA-256 checked at first OCR use), dropped the local `packaging/` wheel so pip needs only PyPI from any directory; `pydantic-ai-slim[openai]` replaces `pydantic-ai`, requirements.txt 134 → 81 packages without anthropic, google-genai, logfire or pydantic-evals.

- 22.11.2026 · Codex · Integrated #55 on `integrate/pr55`. The filter preserves technical titles and native text in mixed PDFs. A lawyer’s name in a firm field needs two weak OCR words and a conflicting crop reading before the field is cleared.
- 22.11.2026 · Claude · #39: scanned-appeal party names and lawyer fields become null on stray scanner symbols, a low letter ratio or capitals noise after a lawyer's title; a capitals-noise tail after a legal form is cut unless it names another consortium member; titles are checked for stray symbols only. On the organizer template scan the appellant and law firm names are now null and the authority name ends at its legal form (checked by a direct CLI run; the template is not in the eval). Organizer scans 0.9974 → 0.9974, full training 1.000 → 1.000 (holdout 1.000), both against `4d91600`; the private dev corpora are not on this machine and were not measured · b2121b5
- 22.11.2026 · Claude · #39: judge PASS on `c4b3d94` after two rounds of P2 fixes; pushed `fix/ocr-plausibility` with a PR to main. Left: a real-corpus check by the corpus owner before merge (dev corpora not on this machine).
- 22.11.2026 · Claude · #39: closed #55 unmerged, superseded by #87, which already brought its gate into main. The reworked variant (trim a noise tail and trailing stray symbols, null only a value that is noise throughout) gave byte-identical output to main `e149af2` on the 30 organizer scans and the same three scored fields on the template scan (only its redacted law-firm name differs: main null, the rework keeps a garbled reading). It changed none of 283 clean long-string reference values and scored the same UZP F1 on 6 of 7 injected-damage recipes; on the seventh, three stray `|` inside a value, it scored 0.916 against 0.884 for main. It was never run on the private corpora. [Numbers](https://github.com/00200200/HackNation2026-2/pull/55#issuecomment-7072913999) (`fix/ocr-plausibility` kept)
- 22.11.2026 · Claude · Removed the deadline guard in front of the alternate OCR reading in `_process` (CodeRabbit on #33). After the shared deadline, recovery from a failed keyed extraction now tests the cached RapidOCR reading against the rules instead of returning `{}`; a new alternate reread still stops itself in `read_pages`. Only `KIO_OCR_ENGINE=hybrid` is affected, the default engine and its OCR work are unchanged. [Tests](tests/test_cached_ocr_deadline.py) (`fix/cached-ocr-after-deadline`)
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

- 21.11.2026 · Codex · Recovered scanned transfer confirmations from debit details and posted rows, preserved printed IBAN prefixes on scans and corrected tilted receipt columns on `feat/scanned-transfers`.
- 21.11.2026 · Codex · Merged integrated rules at `21737c1`. The Ministral profile now checks the document’s own heading before fallback routing, limits native gap calls to missing parties or payment facts, and can verify the first allegation in one short request. On corpus 2 dev, eight targeted requests added four correct fields in a paired comparison.
- 21.11.2026 · Codex · Fixed the execution-date regression reported on PR #23, added three native receipts with baseline outputs, and recognized three additional completed payment statuses. All 196 training files matched the baseline byte for byte at `ee6c36e`. The clean training run scored 1.000 micro F1 and the 30 organizer scans scored 0.5633 micro F1.

- 21.11.2026: the appeal-scan branch recovers first-act dates, role and counsel blocks, and procurement fields using OCR provenance and first-page word boxes. All ten public appeal references matched exactly in development.
- 21.11.2026 · Codex · Recovered officers, multiple appointments and register digits on scanned grants, and named signers from embedded certificates on real grants. All 10 organizer grants matched exactly in rules-only mode.
- 21.11.2026 · Codex · Required the dated execution statement to name the payment. Added the reviewer's copy-of-receipt case, an archival request and a transfer executed before booking. All 196 training outputs at `36afcb7` matched the baseline byte for byte, and full training scored 1.000 micro F1. The organizer scan run exhausted shared disk space while writing the 30th output. The table retains the earlier scan measurement.
- 21.11.2026 · Codex · Merged main at `5297660` into the appeal scan branch and combined cover-page OCR evidence with scanned grant and certificate extraction.
- 21.11.2026 · Codex · Verified merge `6f55ef6` against main: all 196 training outputs matched byte for byte. Organizer scan micro F1 rose from 0.6852 to 0.9203. Refreshed both real development cohorts.

- 21.11.2026 · Codex · Measured the second scanned-transfer pass at `12a5681`. Nine of ten development receipts matched exactly, and all 196 training outputs retained byte parity. [Round 2 measurements](evals/results/scanned-transfers-round2.json)

- 21.11.2026 · Codex · Recovered joint purchasing lists across page breaks, identified appellant counsel and employers, reread damaged searchable appeals and linked first charges to notification evidence. Measured the changes on both real development sets and the organizer scans.
- 21.11.2026 · Codex · Recovered stamp signers by column, resolved a damaged initial in a titled appointment list, joined grantor registry rows and completed inflected company names. Side-by-side approval signatures now follow their visible reading order.

- 21.11.2026 · Codex · Synced the small-model branch with main at `5297660`, including scanned grant extraction and the bank execution-date rules.
- 21.11.2026 · Codex · Verified training on the clean merge `fb08cd7` and on `main` at `5297660`. Both scored 1.000 micro F1 and produced identical paths and bytes for all 196 PDFs, including all 16 empty negative outputs.
- 21.11.2026 · Codex · Integrated the five accuracy PRs. The first live rules-first run matched 10/30 organizer documents exactly, compared with 29/30 keyless. Apply verified scan fields and grant signatures before model gap filling.
- 21.11.2026 · Codex · On organizer scans, full local extraction restored 26/30 exact keyed outputs. The remaining model regressions filled absent references with account numbers and assigned a party mailbox to counsel. Apply the existing core-field check to rule-routed scanned appeals and receipts with the incomplete-gap profile.

- 21.11.2026 · Codex · Verified the merge at `fb08cd7` against `main` at `5297660`. The keyless CLI matched all 196 training outputs by path and bytes, with micro F1 1.000. On 30 organizer scans, both scored 0.6852 micro F1. Main took 9.65 s/PDF with default settings. The first branch run timed out in Polish OCR on the last PDF. The completed branch retry at `37d6352` used `OMP_THREAD_LIMIT=1` and took 3.69 s/PDF.
- 21.11.2026 · Codex · Merged main through `791dd00`. On the reviewer’s invented PDFs, the regional rules-first profile recovered the date, amount, transaction reference and title on four completed receipts, and the printed full attorney name on three grants. Five negative controls stayed empty. The previous corpus measurements document the earlier product revisions.
- 21.11.2026 · Codex · After fixing the two keyed extraction regressions at `facdd0c`, the keyless CLI matched main at `791dd00` byte for byte on all 196 training outputs, including 16 empty negatives. Both revisions scored 1.000 micro F1 on full training and cases 51–60. Ruff and all 1,535 tests passed.


- 21.11.2026 · Codex · Measured `a32ba1c` against `5297660`. All 226 outputs matched byte for byte. Four workers processed 30 scans in 37.15 s and the 150-PDF mix in 74.42 s on an M1. [Per-PDF runtime profile](evals/results/batch-runtime.json)
- 21.11.2026 · Codex · On `perf/adaptive-budget`, all 226 public outputs matched under eight CPU busy loops. A single worker completed the 150-PDF mix under that load in 401.87 seconds. [OCR budget measurements](evals/results/adaptive-ocr-budget.json)
- 21.11.2026 · Codex · In the integrated Ministral profile, preserve the required null personal name for a corporate grantor after filling model gaps. The previous profile filled it on three organizer scans and one corpus 1 grant.
- 21.11.2026 · Codex · Restored issuer declarations above grant titles, printed signers beside email addresses, and scanned sole-trader names. Certificate attribution now checks the signer's role. Eight invented CLI cases compare the affected records with the pre-PR #25 base.
- 21.11.2026 · Codex · Measured the integrated accuracy and runtime PRs at `ca2975392`. Both profiles matched all 196 training outputs from main byte for byte. On the shared 16 GB Apple M1, the integrated CLI processed 30 organizer scans in 36.12 s with four rules workers and 44.91 s with three Ministral workers. The 150-PDF batch took 57.54 s and 70.38 s respectively. It used two copies of the 30 scans and 90 training PDFs. [Combined measurements](evals/results/round2-integration.json)
- 21.11.2026 · Claude · Updated `docs/task/BRIEF.md` to organizer README `0b360a9`: evaluation method and hardware UNCONFIRMED, 150 PDFs in 45 min, OCR by API scored like an LLM, API provider privacy policy and EU/EEA, LLM scoring under revision, 30 labelled scans, FAQ 10 vs PDF 30/20, mixed transfer file names. Closes #43.
- 21.11.2026 · Claude · landing/upload UI in `frontend/`, prod compose on the shared `edge` network, deploy notes · feat/frontend
- 21.11.2026 · Claude · doc2json.pl live over HTTPS (DNS A records, Caddy block on the server), landing reduced to the dark tool screen · feat/frontend
- 21.11.2026 · Claude · `kio2json.web_api` (health + extract, index-matched results) behind doc2json.pl, API container, frontend wired · feat/web-extraction

- 21.11.2026 · Integrated #27 and #34 with streamed upload limits and a disposable OCR process per document. The request deadline includes upload and queue time.

- 22.11.2026 · Codex · Fixed appeal party boundaries at numbered headings, parenthesized page counters over scans, labelled OCR receipt accounts and explicit grantor signature blocks. The remaining round-three routing and role errors are tracked in #1.

- 22.11.2026 · Restored independent appeal sections from native and OCR word positions, preserved shared headings and bound party cards to their columns. [Measurements](evals/results/two-column-appeals.json)

- 22.11.2026 · Added corroborating Polish filing and payment cues, scoped fields and native two-column reading for issue #63. Re-ran the 240-PDF benchmark and organizer and private gates against the confirmed JSON and account conventions. [Final field counts](evals/results/variants.json)

- 22.11.2026 · Claude · `start.sh` now finds `.venv/bin/python` or `python3`, the CLI writes progress lines as UTF-8 when a Windows redirect uses an ANSI code page, `deploy/RUN.md` says unrelated documents produce `{}`, and the rehearsal speeds in `docs/readme/reference.md` name their revision and profile · fix/jury-run-hardening

- 22.11.2026 · Claude · `start.sh` takes the first of `.venv/bin/python`, `python3` and `python` that is Python 3.13 or newer, `*.sh` files keep LF endings and the encoding test pins its working directory. A two-worker run on the 30 organizer scans at `d9a3b25`, with 12 busy loops on an Apple M2 Pro (about 1.1 cores), kept UZP F1 at 1.000 and routing at 30 of 30. It is recorded as a simulation, not VM timing. [Measurements](evals/results/vm-2vcpu.json) · fix/jury-run-hardening

- 22.11.2026 · Claude · The rehearsal sentence in `docs/readme/reference.md` now says the output was compared with the reference run, names the 226 files as 196 synthetic training PDFs plus 30 organizer scans, and cites the committed record `evals/results/vm-2vcpu.json` for the 399.77 s figure and the revision `7a1c45b` · fix/jury-run-hardening

- 22.11.2026 · Claude · Updated the final deck (12 slides) with the UZP-formula F1, the #76 accession class, a components and licences slide, the Regulamin Stage II split, an architecture slide, UZP value and a two-minute demo script; added the submission checklist with the VM evaluation from the organizer's VM.md. Posted the pre-access history audit and the title recommendation on #48 · docs/pitch

## Frontend branch snapshot before API integration

Public landing https://doc2json.pl (`frontend/`, static nginx, monochrome) runs on the team VPS as `doc2json-web`
behind the faktczyfejk Caddy; deploy in `docs/deploy.md`. Its upload is not wired to the extraction yet: it calls
`/api/health` and keeps files in the browser while that returns 404.

These runs used local rules with the three endpoint variables unset. The two local datasets contain real documents and use whole-case splits. Corpus 1 contributes all 39 development PDFs, including its previously evaluated split. Corpus 2 contributes 39 development PDFs from 14 cases. Its 60 test PDFs are reserved for the merged system. The organizer supplied a separate set of 30 labelled scans, ten per target class, in revision `0b360a9`.

| Dataset | PDFs | Micro F1 | Macro F1 by class | Appeal | Power of attorney | Transfer | Correct routes (appeal / power / transfer) | Empty negatives | Wall s/PDF |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Local corpus 1, all | 39 | 0.6307 | 0.6607 | 0.6016 | 0.9189 | 0.4615 | 12/13 / 6/6 / 4/9 | 11/11 | 7.39 |
| Local corpus 2, dev | 39 | 0.6045 | 0.5662 | 0.6008 | 0.9462 | 0.1515 | 12/13 / 5/5 / 1/10 | 11/11 | 6.33 |
| Organizer scans | 30 | 0.6852 | 0.6023 | 0.6123 | 1.0000 | 0.1944 | 9/10 / 10/10 / 2/10 | n/a | 10.05 |

[Grant development measurements](evals/results/poa-development.json) · [Organizer scan aggregate](evals/results/organizer-scans.json)

| Item | Owner |
|---|---|
| Evaluate the planned Mistral API model (at most 8B parameters) on dev | Open |
| Score corpus 2 test once after selecting and freezing the merged profile | Open |

- 21.11.2026 · Codex · Round 3 traced 130 field errors on 78 real development PDFs. Recovered identifiers from matching party records, checked damaged company names against declarations and read debit amounts across bank columns. The single-field Ministral whitespace trial lost one correct title in 12 calls and was dropped.
- 22.11.2026 · Codex · Implemented UZP’s empty-object and printed-account conventions on `fix/p0-conventions`. The training scorer can restore missing country codes from each transfer PDF with `--correct-training-accounts`.

- 22.11.2026 · Codex · Added a Python 3.13 jury install and 150-PDF CLI comparison for Windows x64, Linux x64 and macOS in `ab3c8fa`. GitHub blocked all three jobs before checkout due to account billing. The run produced no timings. [Run record](evals/results/jury-batch.json)
- 22.11.2026 · Codex · Implemented the UZP scorer and retained historical strict micro F1 on `feat/uzp-metric` (#59).

- 22.11.2026 · Codex · Added the seeded layout regression gate and measured main at `f7f3ee9` and `3eccb41` on the same 240 generated PDFs for issue #63.

- 22.11.2026 · Codex · Added local jury Compose services and the signed task rules for #60. Compose configuration validated. Docker Desktop did not answer its health probe, so container byte parity is pending.
- 22.11.2026 · Codex · The keyless LSTM crop experiment retained 13 correctly printed checksum-invalid accounts on the 240 seeded variants, raising UZP F1 from 0.2960 to 0.3053. It changed no digits on either real cohort or the organizer scans. [Paired measurements](evals/results/ocr-alternatives.json)

- 22.11.2026 · Claude · doc2json.pl frontend: route file drops anywhere on the page to the upload, report a refused clipboard copy, white keyboard focus ring on light buttons, null token at #8a8a8a (CodeRabbit threads on #27) · fix/frontend-review-27
- 2026-11-22 · Grounded candidate selection for disputed, populated first-page transfer fields, singleton appeal party names and procurement titles in the rules-first schema profile (`feat/doubtful-values`).
- 22.11.2026 · Codex · Scored candidate selection after merging #71 at `c13dc3e7f`. Across 91 development PDFs, UZP micro-F1 was 0.9572 keyless and 0.9617 keyed with two workers. All 196 keyless training outputs matched main byte for byte. [Development counts](evals/results/doubtful-values.json)
- 22.11.2026 · Codex · Prepared the VM installation and offline rehearsal for #66 and refreshed the organizer instructions to `eadffbc`. [Rehearsal measurements](evals/results/vm-2vcpu.json)

- 22.11.2026 · Claude · Follow-up to #49 after #90 integrated an earlier snapshot of it: restored the `docs/task/BRIEF.md` text that snapshot dropped (per-profile failure behaviour, the PR #77 install kit and its unverified checks, the UNCONFIRMED tag on the synthetic-set relay, the `--correct-training-accounts` note) and recorded that the organizer README (`data/uzp/README.md:143`) still asks for an empty file while UZP replied four times on Discord, three times explicitly specifying `{}` (#57). Removed the stale "wire the upload" row from the frontend snapshot, since the page calls `/api/extract`, and named the owners of the VM row from the #66 thread · docs/brief-followup
- 22.11.2026 · Codex · Synced #72 with main at `4222472`, retaining first-page candidate selection in the keyed profile.
- 22.11.2026 · Codex · Synced the rule fixes in #75 with main at `b9c2c7f`, preserving the printed account prefix during OCR slash repair.
- 22.11.2026 · Codex · Integrated the merged #75 rule fixes into #72 at main `257a6af`.
- 2026-11-22 · Transfer confirmations can bind a split execution heading to a single dated amount and two explicitly owned accounts. Receipt dates also accept Roman months and labelled whole amounts can place the currency first.
- 22.11.2026 · Codex · Added the seeded case-linked benchmark on `feat/case-benchmark`, pairing each native appeal, mandate, transfer and near-negative with a scan and grouping the results by case and layout. Main `fa9937e` scored 0.7191 UZP and 0.6617 strict on 208 PDFs. [Measurements](evals/results/case-benchmark.json)
- 22.11.2026 · Codex · Integrated the additional document families and matched native controls from #88 as `make eval-document-variants`. The fixed #69/#93 benchmark still runs with `make eval-variants`. · integrate/pr88
