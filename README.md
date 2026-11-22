<p align="center">
  <img src="docs/readme/hero.png" alt="doc2json: KIO appeal PDFs in, the organizer's JSON out" width="100%">
</p>

<p align="center">
  <a href="https://doc2json.pl"><b>doc2json.pl</b></a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#results">Results</a> ·
  <a href="docs/readme/reference.md">Technical reference</a>
</p>

HackNation 2026 entry for the **Odwołania2json** challenge of the Public Procurement Office (UZP). Drop the PDFs of a
KIO appeal case in. doc2json works out which file is the appeal, the power of attorney and the transfer
confirmation from their content, and writes the organizer's JSON for each one. For an unrelated document it writes `{}`.

<p align="center">
  <a href="https://doc2json.pl"><img src="docs/readme/web.png" alt="doc2json.pl: drop PDFs on the left, read the JSON on the right" width="100%"></a>
</p>

## The problem

A KIO case can include an appeal, a power of attorney and a payment receipt. Each describes a different part of the same proceeding. The extractor reads native text and scans, identifies the document type and writes the fields UZP asks for. [Task brief](docs/task/BRIEF.md)

<p align="center"><img src="docs/readme/classes.png" alt="Three document types: appeal, power of attorney, transfer confirmation; unrelated documents produce an empty JSON object" width="100%"></p>

## How it works

<p align="center"><img src="docs/readme/pipeline.png" alt="Read, route, extract, normalise, write" width="100%"></p>

Routing reads the document text. Each class configuration supplies its routing rules, fields and extraction engines. The default CLI runs on CPU with local OCR and rule-based extraction. It writes `null` for missing values. An optional language model can extract fields from cited source spans. [Pipeline](docs/readme/reference.md#how-it-works) · [Model configuration](docs/readme/reference.md#use-a-model-endpoint)

The default configuration needs no GPU and no API key and calls no language model, so it has no per-document API cost. The optional model profile we measured calls Mistral's open-weight `ministral-3b-2512` (3,849,090,048 parameters) through the regional endpoint `api.eu.mistral.ai`. Its documented processing geography includes EU and EFTA countries, so a narrower location commitment is still open, and we have not measured its cost per 100 documents.

Where each step lives in `kio2json/`:

| Modules | Responsibility |
|---|---|
| `__main__.py`, `batch.py` | Batch CLI, and the per-document output and diagnostics it shares with the viewer |
| `gui.py`, `gui_files.py`, `gui_explain.py` | Local document viewer, with panels for the class list and a document's trace |
| `web_api.py`, `web_worker.py`, `jury_web.py` | HTTP API and upload page; each upload is read in a disposable process |
| `pipeline.py`, `trace.py` | One PDF to a document class and canonical JSON, and the opt-in trace of the routing reason and the source of each field |
| `pdf_text.py`, `ocr_*.py`, `rapid_worker.py` | Page text from the PDF text layer, local OCR for pages without one with wall-clock limits on optional OCR, and the rules and checks that apply only to OCR text |
| `class_config.py`, `classify.py`, `validators.py`, `classes.py` | Load the class TOML files (`config/classes/` by default), route each document from its own content, apply the field checks a class declares, and scaffold a class from a sample PDF (`python -m kio2json.classes`) |
| `appeal.py`, `appeal_*.py` | Appeal to KIO: the appeal, the appellants, the contracting authorities and the procurement |
| `power_of_attorney.py`, `grant_*.py`, `attorney_spans.py` | Power of attorney: the principals with their signatories, and the attorneys |
| `bank_transfer.py`, `receipt_*.py`, `accounts.py` | Transfer confirmation, and printed account numbers |
| `engines.py`, `llm.py`, `model_*.py`, `charge_model.py`, `derived_evidence.py`, `endpoint_error.py` | Run the configured extractors in order and fill gaps; the optional model engine |
| `output_schema.py`, `common.py`, `personal_names.py` | Output models built from the class fields, the patterns and normalisers the extractors share, and inflected Polish personal names |
| `case_checks.py`, `case_repair.py`, `doubtful_values.py` | Checks across the documents of one case, repair of a damaged value from an independent reading, choice among local readings of a doubtful value |

## Results

These field scores come from the keyless CLI on merged main at `725765b`, with two workers. Both private corpora contain real documents and are not distributed. [Merged-main measurements](evals/results/merged-main-725765b.json)

| Dataset | PDFs | UZP micro F1 | Strict micro F1 |
|---|---:|---:|---:|
| Organizer synthetic training, printed account prefixes | 196 | 1.0000 | 1.0000 |
| Organizer scans | 30 | 1.0000 | 0.9974 |
| Fixed synthetic layout variants | 240 | 0.9512 | 0.9264 |
| Case-linked synthetic documents, development | 112 | 0.9729 | 0.9667 |
| Case-linked synthetic documents, reserved | 96 | 0.7923 | 0.7705 |
| Private corpus 1, development | 22 | 0.9286 | 0.8821 |
| Private corpus 2, development | 39 | 0.9244 | 0.8951 |

On organizer scans, 29 of 30 outputs matched the reference JSON exactly, including after a serial retry of the remaining scan. A separate mixed batch of 90 native PDFs and two copies of the 30 scans took 343.53 seconds, with 148 of 150 outputs exact. UZP allows approximate matches on five long fields. The UZP column uses normalized Levenshtein similarity for those fields. The strict column uses the project's earlier scoring method. [Batch results](evals/results/merged-main-725765b.json) · [Scoring rules](https://github.com/00200200/HackNation2026-2/issues/59)

Each case-linked document has a native and a scanned rendering. The receipt router at `b5cdc5b` recognized all four development bank letters. On a second blind evaluation of the reserved split, correct routes rose from 82 to 88 of 96 and UZP F1 rose from 0.7923 to 0.8159. The six newly routed PDFs comprised two transaction histories, two operation details and two order details. Each still had field errors. Exact outputs stayed at 41 of 96. [Case scores](evals/results/case-transfer-routing.json)

On eight reserved synthetic sole-trader mandates, the grantor reader recovered all eight personal names and tax IDs. It missed the business and signer names on all eight. [Grantor field results](evals/results/sole-trader-grantors.md)

On five held-out cases in a separate ten-appeal, two-column benchmark, field F1 was 0.9700 with native text and 0.8925 with forced OCR. Unlabelled procurement titles remained missing. [Two-column results](evals/results/two-column-appeals.json) · [Pipeline diagram (PDF)](docs/pipeline/pipeline.pdf)

The original training references omit the printed `PL` prefix of two accounts in each of 48 transfers, so the training row scores against references with them restored (`--correct-training-accounts`, [issue #58](https://github.com/00200200/HackNation2026-2/issues/58)). At product commit `55dc2a1` the outputs scored 0.9758 UZP and 0.9585 strict against the original references, with 96 field mismatches (`integration.training_raw` in [`p0-conventions.json`](evals/results/p0-conventions.json)).

The rows are development sets or benchmarks that we generated. The rules were developed against the training cases, the organizer scans and the two local corpora, and the corpora are private sets of real documents that are not in this repository. The reserved case-linked split uses independently phrased appeals and further layouts, but it comes from the same generator as the development split and has been scored more than once, so it does not estimate how real documents score. These figures are not estimates for unseen cases, and the 60 test PDFs of corpus 2 are reserved and not scored. The two-column benchmark above holds out five of its ten generated appeals, but all ten come from one generator, so it does not estimate how real documents score either. A held-out run on 21.11.2026 of two DeepSeek model profiles scored 0.7002 and 0.6055 micro F1 on 17 PDFs from 7 cases under the metric of that time (`test.deepseek_v4_pro.micro_f1` and `test.deepseek_flash.micro_f1` in [`llm-real-docs.json`](evals/results/llm-real-docs.json), runtime commits `d288af1` and `15f4fbb`). It measured older code, and [WORKLOG.md](WORKLOG.md) notes that corpus 1's previously evaluated split now sits inside its 39 development PDFs. Both profiles ran on the provider's own API through an endpoint authorized for development. Neither is the Mistral profile above, and the repository's configuration does not use them. The table comes from one run on merged main at `725765b`, and the extractor has changed since (for example descriptive captions in #122, sole-trader grantors in #123, receipt routing in #124 and delivery proofs in #128), so a measurement on the submission commit is still open ([WORKLOG.md](WORKLOG.md)).

Corpus 1 has 39 development PDFs: the 22 of the table row (`private_development.corpus_1` in [`merged-main-725765b.json`](evals/results/merged-main-725765b.json)) and 17 more, the split that was evaluated earlier and now sits inside the development data. Older corpus 1 figures cover all 39 PDFs and do not compare with the row: 0.9231 UZP and 0.8900 strict at `7a1c45b` ([`ocr-alternatives.json`](evals/results/ocr-alternatives.json)), and 0.9247 and 0.8921 at `2c00fbb` (`stages.final.gates.corpus_1_all` in [`variant-robustness.json`](evals/results/variant-robustness.json)).

Rendering the 30 organizer scans again lowers the scan row. In [issue #81](https://github.com/00200200/HackNation2026-2/issues/81#issuecomment-7073288215) they were rendered from a fixed seed in 15 variants on main `fecdca5` and scored 0.791 to 0.965 UZP F1, against 1.000 for the delivered files. Plain re-renders at 150 to 300 dpi scored 0.922 to 0.965, added noise 0.931, one-bit images 0.882 and 0.904, up to 3 degrees of skew 0.791 to 0.901, and three mixed variants 0.856 pooled. Documents returned as `{}`, mostly transfer confirmations, cost 0.000 to 0.099 of F1, and wrong fields in routed documents cost 0.033 to 0.125. The script is not on main yet, so these numbers come from the issue comment.

[Known limits](docs/readme/reference.md#known-limits) lists what the extractor does not handle, and the [task brief](docs/task/BRIEF.md) lists the unconfirmed organizer details. The `{}` for an unrelated document is UZP's answer on Discord, which the brief records next to the organizer README's "empty `.json` file".

Timing (keyless, local rules): with the 180-second primary watchdog (`watchdog_commit` `21f55e0`), two workers processed all 226 public PDFs in 160.75 s on a shared Apple M1 ([`first-pass-watchdog.json`](evals/results/first-pass-watchdog.json), `public_batch.watchdog.wall_seconds`, 160.753). The one-minute load average of the host was 34.65 at the start and 32.54 at the end (`public_batch.watchdog.load_average_1min_start` and `load_average_1min_end`). In an earlier stress run, 150 PDFs took 401.873 s with one worker while eight busy loops occupied the 8 logical CPUs ([`adaptive-ocr-budget.json`](evals/results/adaptive-ocr-budget.json), `runs[5].seconds`, product `59aa13a`). That run preceded the final change to optional page reads, and the test suite ran during part of it (`serial_measurement`). Both timings predate #54, #72, #75, #82, #87 and #89. The 150-PDF mixed batch under the results table, run on merged main at `725765b`, is newer than both. The organizer allows 45 minutes for 150 PDFs ([`data/uzp/README.md`](data/uzp/README.md)), and the jury's machine will differ from ours.

## Quick start

Install 64-bit Python 3.13. From the repository root, create and activate a virtual environment.

| Shell | Create | Activate |
|---|---|---|
| PowerShell | `py -3.13 -m venv .venv` | `.\.venv\Scripts\Activate.ps1` |
| macOS or Linux | `python3.13 -m venv .venv` | `. .venv/bin/activate` |

Place PDFs under `input/<case>/`, then run the following commands. The CLI writes the matching JSON files under `output/<case>/`.

```sh
python -m pip install -r requirements.txt
python -m kio2json
```

| | Windows | Linux or macOS |
|---|---|---|
| CLI on `input/` → `output/` | `.\start.bat` | `./start.sh` |
| Local viewer in the browser (127.0.0.1:8000): pages next to the JSON | `.\start.bat gui` | `./start.sh gui` |
| Web app | [doc2json.pl](https://doc2json.pl) | [doc2json.pl](https://doc2json.pl) |

<p align="center">
  <img src="docs/gui/appeal.png" alt="Local viewer with an appeal" width="49%">
  <img src="docs/gui/transfer.png" alt="Local viewer with a transfer confirmation" width="49%">
</p>

OCR engines, offline install of the language data, the optional model endpoint and every setting are in the
[technical reference](docs/readme/reference.md#run).

## Deploy on the evaluation VM

UZP runs the command from `RUN.md` in `/opt/solution` on a Linux VM, without the team present, after it cuts the team's access at 11:00 on 22.11.2026 ([`data/uzp/VM.md`](data/uzp/VM.md)). `deploy/vm_setup.sh` installs the pinned requirements and smoke-tests a transfer and a scanned appeal, and `deploy/RUN.md` is the command we hand over. The reference includes the offline rehearsal, the reboot checks and the Docker Compose fallback. [VM setup](docs/readme/reference.md#deploy-on-the-evaluation-vm) The Ubuntu 24.04 offline run with two CPUs is recorded as unverified (`ubuntu_24_04_amd64_2vcpu_16g.status` in [`vm-2vcpu.json`](evals/results/vm-2vcpu.json)), because Docker Desktop did not respond on the development host, and the Docker Compose fallback has not been run end to end either.

## Run with Docker Compose

Run `docker compose run --rm cli` for the batch or `docker compose up gui` for the local upload page. We have not yet run these two services end to end in a container and compared their output with the CLI's; that check is open in [WORKLOG.md](WORKLOG.md). [Compose setup](docs/readme/reference.md#run-with-docker-compose)

## Add a document type

```toml
# classes/receipt.toml
id = "receipt"
engines = ["labelled_fields"]

[routing]
required = ['^Receipt$', '^Reference:']

[fields.reference]
type = "string"
instruction = "Reference printed on the receipt."
pattern = '^Reference:[ \t]*(.+)$'
```

Save this file as `classes/receipt.toml` and run `python -m kio2json --classes classes --input input --output output`. Add `--explain trace` to record the routing decision and field sources separately. The reference shows how to generate a class from a sample PDF and configure field checks.
[Add a class](docs/readme/reference.md#add-a-class).

## REST API

The upload page and doc2json.pl call one HTTP API. In the installed environment, `python -m uvicorn kio2json.jury_web:app --host 127.0.0.1 --port 8000` serves it. `docker compose up gui` is configured to serve it too, but the Compose services have not been run end to end yet. OpenAPI is at <http://127.0.0.1:8000/api/docs> and, for the hosted copy, <https://doc2json.pl/api/docs>. Swagger UI loads from cdn.jsdelivr.net, so that page is blank offline, while `/api/openapi.json` still works.

```bash
curl -F files=@appeal.pdf -F files=@power.pdf http://127.0.0.1:8000/api/extract
```

The answer has one result per uploaded file, in upload order: `{"results": [{"index": 0, "file": "appeal.pdf", "class": "appeal", "data": {...}, "error": null}]}`. A document outside every class has `"class": null` and `"data": {}`. A file that is not a PDF, or a document that fails, also has `"data": {}`, with the reason in `error`. One request takes up to ten files of 20 MB each. Each document gets 90 seconds (300 in the `gui` service of `compose.yaml`), and a request that runs past 500 seconds ends with HTTP 408 and no results. The server reads one document at a time and accepts at most four requests at once (one being read, three waiting), so a fifth gets HTTP 503. `GET /api/health` answers `{"status": "ok"}`, or `"busy"` while a document is being read or the queue is full. The limits are the environment variables `KIO_WEB_MAX_FILES`, `KIO_WEB_MAX_FILE_MB`, `KIO_WEB_DOC_TIMEOUT_S`, `KIO_WEB_REQUEST_BUDGET_S` and `KIO_WEB_MAX_QUEUED`. The extraction is the same one the CLI runs.

## Data handling

The default configuration processes everything on one machine: PDFs are read, OCR'd and extracted locally, and no document text goes anywhere else. The API stores no uploads and no results. An upload is held in memory, or in a temporary file for a large one, until the request ends (`extract` closes the form in `kio2json/web_api.py`), and the copy a worker reads sits in a temporary directory that is deleted as soon as its document has been read (`_read`). A model endpoint is used only when `KIO_LLM_BASE_URL`, `KIO_LLM_MODEL` and `KIO_LLM_API_KEY` are set in the environment or in a `.env` file in the working directory, and then page text goes to that endpoint. For the profile we measured that is Mistral's regional API (see [How it works](#how-it-works) for what is confirmed about its location). The public page runs on a team VPS at OVHcloud, and the repository does not record the datacentre region (UNCONFIRMED). For documents with personal data, use the CLI or the local viewer, which keep the files on your machine. The real documents we developed against are private and not in this repository, and `data/uzp/` is the organizer's published copy of their data.

## Licences

The repository has no `LICENSE` file for our own code yet. Under § 4 of the [task rules](docs/task/regulamin.pdf) the winning teams transfer the copyright of their solution to the organizer in a written agreement, and external solutions must be named in the presentation. The organizer allows only open-source components ([FAQ](docs/task/FAQ.md), [`data/uzp/README.md`](data/uzp/README.md)). Ours, with the licence each declares in its package metadata at the pinned versions (transitive dependencies are in `uv.lock`):

| Component | Licence |
|---|---|
| pdfplumber, pydantic, pydantic-ai-slim, pydantic-settings, tesserocr, onnxruntime, Shiny, RapidFuzz, asn1crypto, FastAPI | MIT |
| RapidOCR | Apache-2.0 |
| Babel | BSD-3-Clause |
| pypdfium2 | BSD-3-Clause and Apache-2.0, with the licences of its bundled dependencies |
| python-stdnum | LGPL v2 or later |
| Morfeusz 2 (`morfeusz2`) | BSD 2-clause ([its licence page](http://morfeusz.sgjp.pl/doc/license/)) |
| Tesseract language data in `kio2json/tessdata/` | Apache-2.0 (`kio2json/tessdata/LICENSE`) |
| Geist font on the page and in the README images | SIL OFL 1.1 (`frontend/public/fonts/LICENSE-Geist.txt`) |
| `ministral-3b-2512`, the optional model (not in the repository) | Apache-2.0 ([provider notes](docs/small-model-providers.md)) |

## Repository

| Path | What is there |
|---|---|
| `kio2json/` | The extractor: PDF text and OCR, routing, rule extractors, optional model engine, CLI and viewer |
| `config/classes/` | One TOML per document class |
| `evals/` | Field-level F1 harness, recorded results and the generated layout benchmark (`make eval-variants`) |
| `compose.yaml`, `api.Dockerfile` | Docker Compose services for the batch CLI and the local upload page |
| `deploy/` | VM setup script, handover `RUN.md`, offline rehearsal and the Compose file for the VM |
| `frontend/`, `docs/deploy.md` | The doc2json.pl page and how it is deployed |
| `data/uzp/` | Organizer data and schemas (copy of their repository) |
| `docs/task/` | Challenge brief, FAQ and details |
| `WORKLOG.md` | Current state, open work and the dated log |
