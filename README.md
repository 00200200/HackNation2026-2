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

doc2json is our HackNation 2026 entry for the Odwołania2json challenge of the Public Procurement Office (UZP). Give it
the PDFs of a KIO appeal case. It decides from the content which file is the appeal, the power of attorney or the
transfer confirmation, and writes the organizer's JSON for each one. Any other document gets `{}`, as UZP confirmed in
[issue #57](https://github.com/00200200/HackNation2026-2/issues/57).

Rules only, with no model call, it scored 1.0000 UZP micro F1 on the 196 organizer training PDFs (against references with
the printed `PL` account prefixes restored) and on the 30 organizer scans at product commit `97dc53e`, and 0.9212 and
0.9244 on two local sets of real documents at `55dc2a1`. Strict micro F1 was 1.0000, 0.9974, 0.8880 and 0.8951 for the
same four sets. All four are development sets, and we have no held-out score. The [results](#results) section lists the
limits and what main has merged since.

<p align="center">
  <a href="https://doc2json.pl"><img src="docs/readme/web.png" alt="doc2json.pl with sample data: drop PDFs on the left, read the JSON on the right" width="100%"></a>
</p>

## The problem

An appeal case is a handful of PDFs, some exported from a word processor and some scanned. Each repeats the same
facts in different words: the parties and their identifiers, the procurement, the contested action and the paid fee.
A person reads them easily, but a system can only use those facts once they are structured data.
<sub>Source: challenge description, UZP, HackNation 2026 (`docs/task/`).</sub>

<p align="center"><img src="docs/readme/classes.png" alt="Three document types: appeal, power of attorney, transfer confirmation; anything else gets an empty object" width="100%"></p>

## How it works

```mermaid
flowchart TD
    VIEW["<b>Viewer and upload API</b><br/>kio2json.gui, kio2json.web_api<br/>doc2json.pl calls the API"]
    CLI["<b>Batch CLI</b><br/>python -m kio2json<br/>input/case/*.pdf"]
    READ["<b>Read each page</b> (pdf_text.py)<br/>PDF text layer, local OCR on pages without text<br/>word boxes kept for layout rules"]
    ROUTE["<b>Classify by content</b> (classify.py, class_config.py)<br/>the file name is never used<br/>cues and fields come from config/classes/*.toml"]
    subgraph EXTRACT["Extract by class"]
        TRANSFER["<b>Transfer confirmation</b><br/>bank_transfer.py, receipt_*.py"]
        POA["<b>Power of attorney</b><br/>power_of_attorney.py, grant_*.py"]
        APPEAL["<b>Appeal</b><br/>appeal.py, appeal_*.py"]
    end
    OTHER["<b>Any other document</b><br/>no class accepts it"]
    NORM["<b>Normalize and validate</b><br/>output_schema.py<br/>a value the document does not state stays null"]
    OUT["<b>Write organizer JSON</b><br/>output/case/name.json"]
    EMPTY["<b>Write {}</b><br/>at the matching JSON path"]
    MODEL["<b>Optional model engine</b> (llm.py)<br/>only with an endpoint configured<br/>a value is kept only with a source quote"]

    VIEW --> READ
    CLI --> READ
    READ --> ROUTE
    ROUTE --> TRANSFER
    ROUTE --> POA
    ROUTE --> APPEAL
    ROUTE --> OTHER
    TRANSFER --> NORM
    POA --> NORM
    APPEAL --> NORM
    NORM --> OUT
    OTHER --> EMPTY
    MODEL -.-> EXTRACT

    classDef io fill:#ecfdf3,stroke:#15803d,color:#1f2933
    classDef local fill:#eff4ff,stroke:#1d4ed8,color:#1f2933
    classDef rejected fill:#fff7ed,stroke:#b45309,color:#1f2933
    classDef optional fill:#f9fafb,stroke:#6b7280,stroke-dasharray:4 3,color:#1f2933
    class CLI,VIEW,OUT io
    class READ,ROUTE,APPEAL,POA,TRANSFER,NORM local
    class OTHER,EMPTY rejected
    class MODEL optional
    style EXTRACT fill:#f9fafb,stroke:#9ca3af,color:#1f2933
```

- Routing reads the text of each PDF and never its file name, so `scan001.pdf` is handled like `odwolanie.pdf`.
- A value the document does not state is `null`. Output from an optional model is kept only when it cites a
  supporting span of the source.
- It needs no GPU: OCR runs offline on the CPU. The default configuration needs no API key and calls no language
  model, because extraction is rules plus local OCR, so it has no per-document API cost. The optional model profile
  we measured calls Mistral's open-weight `ministral-3b-2512` (3,849,090,048 parameters) through the regional endpoint
  `api.eu.mistral.ai`. Its documented processing geography includes EU and EFTA countries, so a narrower location
  commitment is still open, and we have not measured its cost per 100 documents; see
  [Use a model endpoint](docs/readme/reference.md#use-a-model-endpoint).
- Each document class is one TOML file in `config/classes/` with its routing cues, fields and engines. The keys are
  listed in [Add a class](docs/readme/reference.md#add-a-class), and the disabled fourth class is a worked example:
  [enable it](docs/readme/reference.md#enable-the-fourth-class).

Where each step lives in `kio2json/`:

| Modules | Responsibility |
|---|---|
| `__main__.py`, `batch.py` | Batch CLI, and the per-document output and diagnostics it shares with the viewer |
| `gui.py`, `gui_files.py` | Local document viewer |
| `web_api.py`, `web_worker.py`, `jury_web.py` | HTTP API and upload page; each upload is read in a disposable process |
| `pipeline.py` | One PDF to a document class and canonical JSON |
| `pdf_text.py`, `ocr_*.py`, `rapid_worker.py` | Page text from the PDF text layer, local OCR for pages without one with wall-clock limits on optional OCR, and the rules and checks that apply only to OCR text |
| `class_config.py`, `classify.py` | Load `config/classes/*.toml` and route each document from its own content |
| `appeal.py`, `appeal_*.py` | Appeal to KIO: the appeal, the appellants, the contracting authorities and the procurement |
| `power_of_attorney.py`, `grant_*.py` | Power of attorney: the principals with their signatories, and the attorneys |
| `bank_transfer.py`, `receipt_*.py`, `accounts.py` | Transfer confirmation, and printed account numbers |
| `engines.py`, `llm.py`, `model_*.py` | Run the configured extractors in order and fill gaps; the optional model engine |
| `output_schema.py`, `common.py` | Output models built from the class fields, and the patterns and normalisers the extractors share |
| `case_checks.py`, `case_repair.py`, `doubtful_values.py` | Checks across the documents of one case, repair of a damaged value from an independent reading, choice among local readings of a doubtful value |

## Results

<p align="center"><img src="docs/readme/results.png" alt="UZP field micro F1, rules only: 1.0000 on the training cases and the organizer scans, 0.9212 and 0.9244 on two local real-document corpora" width="100%"></p>

| Dataset | PDFs | UZP micro F1 | Strict micro F1 |
|---|---:|---:|---:|
| Organizer training cases (synthetic, corrected references) | 196 | 1.0000 | 1.0000 |
| Organizer scans (scanned PDFs) | 30 | 1.0000 | 0.9974 |
| Local corpus 1 (real) | 39 | 0.9212 | 0.8880 |
| Local corpus 2, dev (real) | 39 | 0.9244 | 0.8951 |

Each row is one rules-only CLI run (no API key, two PDF workers) recorded in
[`evals/results/p0-conventions.json`](evals/results/p0-conventions.json). The training and scan rows are product commit
`97dc53e` (`final_verification`). The corpus rows are the earlier product commit `55dc2a1` (`integration.corpus1all` and
`integration.corpus2`, where `micro_f1` is the UZP score and `micro_f1_strict` the strict one), because the private
corpora were not re-run at `97dc53e`. Main has merged more since then: the first-pass watchdog (#79), the vendored OCR
data (#54), rule fixes (#75), candidate selection (#72), OCR alternatives (#82) and the OCR plausibility gate (#87). The
corpus rows predate them. The
living files `latest.json` and `organizer-scans.json` are described in the
[technical reference](docs/readme/reference.md#current-figures-uzp-micro-f1-rules-only).

UZP micro F1 follows the scoring rules UZP gave on the hackathon Discord, as recorded in
[issue #59](https://github.com/00200200/HackNation2026-2/issues/59) and implemented in `evals/metrics.py`: a field that is
empty in both the reference and the prediction counts as zero, and a wrong value counts as one false positive. Five long
strings accept an 80% RapidFuzz match, because UZP has not confirmed its similarity function. The strict score, a
normalised exact match, is the one we used before.

UZP answered that a transfer account keeps the printed country code
([issue #58](https://github.com/00200200/HackNation2026-2/issues/58)). The original training references omit two printed
`PL` prefixes in each of 48 transfers, so the training row scores against references with them restored
(`--correct-training-accounts`). Against the original references the same outputs score 0.9758 UZP and 0.9585 strict, with
96 field mismatches (`integration.training_raw`). On the organizer scans no field is missing or wrong under the UZP rules
(309 true positives, 0 false positives, 0 false negatives, `integration.scans.field_counts`). The strict metric counts one
false positive and one false negative there (387, 1 and 1, `integration.scans.field_counts_strict`).

All four rows are development sets. The rules were developed against the training cases, the organizer scans and the two
local corpora, and the corpora are private sets of real documents that are not in this repository. We have no held-out
score: these figures are not estimates for unseen cases, and the 60 test PDFs of corpus 2 are not scored. The scan row is
the most exposed. [Issue #81](https://github.com/00200200/HackNation2026-2/issues/81) reports that fresh renders of the same
30 organizer scans score about 0.92 to 0.95 UZP F1, and 0.87 with 1.5 degrees of skew, mostly because transfer routing
fails. Those numbers are approximate and their script is not committed. A reproducible scan stress evaluation is still
open there.

Timing: with the 180-second primary watchdog (`watchdog_commit` `21f55e0`), two workers processed all 226 public PDFs in
160.75 s on a shared Apple M1 ([`first-pass-watchdog.json`](evals/results/first-pass-watchdog.json),
`public_batch.watchdog.wall_seconds`, 160.753). The one-minute load average of the host was 34.65 at the start and 32.54
at the end (`public_batch.watchdog.load_average_1min_start` and `load_average_1min_end`). In an earlier stress run, 150
PDFs took 401.873 s with one worker while eight busy loops occupied the 8 logical CPUs
([`adaptive-ocr-budget.json`](evals/results/adaptive-ocr-budget.json), `runs[5].seconds`, product `59aa13a`). That run
preceded the final change to optional page reads, and the test suite ran during part of it (`serial_measurement`). Both
timings predate #75, #72 and #82. The organizer allows 45 minutes for 150 PDFs
([`data/uzp/README.md`](data/uzp/README.md)), and the jury's machine will differ from ours.

The definition of the score, the earlier rounds and the OCR comparison are in the technical reference:
[current figures](docs/readme/reference.md#current-figures-uzp-micro-f1-rules-only),
[real-document rounds and timings](docs/readme/reference.md#rules-on-real-documents-and-organizer-scans) and
[OCR comparison](docs/readme/reference.md#ocr-on-real-development-documents). Known limits and unconfirmed organizer
details: [known limits](docs/readme/reference.md#known-limits). Full training run:
[`latest.json`](evals/results/latest.json).

## Quick start

Python 3.13, 64-bit. From the repository root:

```bash
python3.13 -m venv .venv && . .venv/bin/activate      # Windows: py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m kio2json                                    # reads ./input/<case>/*.pdf, writes ./output/<case>/*.json
```

| | Windows | Linux or macOS |
|---|---|---|
| CLI on `input/` → `output/` | `.\start.bat` | `./start.sh` |
| Local viewer in the browser (127.0.0.1:8000): pages next to the JSON, and a warning when the documents of one case disagree | `.\start.bat gui` | `./start.sh gui` |
| Web app | [doc2json.pl](https://doc2json.pl) | [doc2json.pl](https://doc2json.pl) |

<p align="center">
  <img src="docs/gui/appeal.png" alt="Local viewer with an appeal" width="49%">
  <img src="docs/gui/transfer.png" alt="Local viewer with a transfer confirmation" width="49%">
</p>
<sub>The transfer screenshot comes from an earlier build, before account numbers kept the printed `PL` country code
([issue #58](https://github.com/00200200/HackNation2026-2/issues/58)).</sub>

`requirements.txt` lists only pinned PyPI packages, so pip downloads only from `pypi.org` and `files.pythonhosted.org`.
The Polish and English OCR data ship in the repository (`kio2json/tessdata/`), and the rules-only CLI and viewer process
PDFs offline after the install. OCR engines, the optional model endpoint and every setting are in the
[technical reference](docs/readme/reference.md#run).

## Run with Docker Compose

Install Docker with Compose v2.24 or later. From the repository root, place case PDFs in
`input/<case>/` or use the bundled `input/case1/`, then run:

```sh
docker compose run --rm cli
```

The first build pulls the `python:3.13-slim` base image and downloads the Python dependencies from PyPI. The Polish
and English OCR data ship in the repository (`kio2json/tessdata/`).
Each input PDF gets a matching file under `output/<case>/`. To upload PDFs in a browser, run:

```sh
docker compose up gui
```

Open <http://127.0.0.1:8000> for the upload page or <http://127.0.0.1:8000/api/docs> for
the API. Press Ctrl+C to stop the server. Both services use local extraction by default.
To enable a model, copy `.env.example` to `.env`, fill in the three endpoint settings,
and rerun the service. Keep the key in the ignored `.env` file.

The image is built for x86-64, because two dependencies, libsass and morfeusz2, have no Linux ARM wheels. Docker Desktop
on Apple Silicon runs it under emulation, which is slower. We have not yet run these two services end to end in a
container and compared their output with the CLI's; that check is open in [WORKLOG.md](WORKLOG.md).

Both services read the host's `config/classes/` directory. See the
[pipeline architecture](docs/readme/reference.md#how-it-works),
[class configuration example](docs/readme/reference.md#enable-the-fourth-class)
and [instructions for adding a class](docs/readme/reference.md#add-a-class). The handover requirements are in
[§3.5 of the task rules](docs/task/regulamin.pdf).

## REST API

The upload page and doc2json.pl call one HTTP API. `docker compose up gui` serves it at
<http://127.0.0.1:8000/api/docs> (OpenAPI), and so does `python -m uvicorn kio2json.jury_web:app --host 127.0.0.1 --port 8000`
in the installed environment (`kio2json.web_api:app` serves the API without the page). The hosted copy is at
<https://doc2json.pl/api/docs>.

```bash
curl -F files=@appeal.pdf -F files=@power.pdf http://127.0.0.1:8000/api/extract
```

The answer has one result per uploaded file, in upload order:
`{"results": [{"index": 0, "file": "appeal.pdf", "class": "appeal", "data": {...}, "error": null}]}`. A document outside every
class has `"class": null` and `"data": {}`. A file that is not a PDF, or a document that fails, also has `"data": {}`, with
the reason in `error`. One request takes up to ten files of 20 MB each, and each document gets 90 seconds by
default and 300 in the `gui` service of `compose.yaml` (`KIO_WEB_MAX_FILES`, `KIO_WEB_MAX_FILE_MB` and
`KIO_WEB_DOC_TIMEOUT_S`). A whole request has 500 seconds (`KIO_WEB_REQUEST_BUDGET_S`). The server reads one document at a time and takes at most four requests at once
(`KIO_WEB_MAX_QUEUED`); a fifth gets HTTP 503. `GET /api/health` answers `{"status": "ok"}`, or `"busy"` while a
document is being read or the queue is full. The extraction is the same one the CLI runs.

## Deploy on the evaluation VM

UZP runs the command from `RUN.md` in `/opt/solution` on a Linux VM, without the team present, after it cuts the team's
access at 11:00 on 22.11.2026 ([`data/uzp/VM.md`](data/uzp/VM.md)). `deploy/vm_setup.sh` installs the pinned requirements
and smoke-tests a transfer and a scanned appeal, and `deploy/RUN.md` is the command we hand over. The steps, the offline
rehearsal and the Docker Compose fallback are in
[Deploy on the evaluation VM](docs/readme/reference.md#deploy-on-the-evaluation-vm). The Ubuntu 24.04 offline run with
two CPUs is recorded as unverified in [`vm-2vcpu.json`](evals/results/vm-2vcpu.json), because Docker Desktop did not
respond on the development host, and the Docker Compose fallback has not been run end to end either.

## Add a document type

```toml
# config/classes/receipt.toml
id = "receipt"
engines = ["labelled_fields"]

[routing]
required = ['^Receipt$', '^Reference:']

[fields.reference]
type = "string"
instruction = "Reference printed on the receipt."
pattern = '^Reference:[ \t]*(.+)$'
```

A class like this needs no code change and no rebuild. Field types, lists, normalisers and model engines:
[Add a class](docs/readme/reference.md#add-a-class). The three organizer classes use the same keys, explained in
[The bundled classes](docs/readme/reference.md#the-bundled-classes).

## Data handling

The default configuration processes everything on one machine: PDFs are read, OCR'd and extracted locally, and no
document text goes anywhere else. The API stores no uploads and no results. An upload is held in memory, or in a
temporary file for a large one, until the request ends (`extract` closes the form in `kio2json/web_api.py`), and the copy
a worker reads sits in a temporary directory that is deleted as soon as its document has been read (`_read`). A model endpoint
is used only when `KIO_LLM_BASE_URL`, `KIO_LLM_MODEL` and `KIO_LLM_API_KEY` are set, and then page text goes to that
endpoint. For the profile we measured that is Mistral's regional API (see [How it works](#how-it-works) for what is
confirmed about its location). The public page runs on a team VPS at OVHcloud, and the repository does not record the
datacentre region (UNCONFIRMED). For documents with personal data, use the CLI or the local viewer, which keep the files
on your machine. The real documents we developed against are private and not in this repository, and `data/uzp/` is the
organizer's published copy of their data.

## Licences

The repository has no `LICENSE` file for our own code yet. Under § 4 of the [task rules](docs/task/regulamin.pdf) the
winning teams transfer the copyright of their solution to the organizer in a written agreement, and external solutions
must be named in the presentation. The organizer allows only open-source components
([FAQ](docs/task/FAQ.md), [`data/uzp/README.md`](data/uzp/README.md)). Ours, with the licence each declares in its
package metadata at the pinned versions (transitive dependencies are in `uv.lock`):

| Component | Licence |
|---|---|
| pdfplumber, pydantic, pydantic-ai-slim, pydantic-settings, tesserocr, onnxruntime, Shiny, RapidFuzz, asn1crypto, FastAPI | MIT |
| RapidOCR | Apache-2.0 |
| Babel | BSD-3-Clause |
| pypdfium2 | BSD-3-Clause and Apache-2.0, with the licences of its bundled dependencies |
| python-stdnum | LGPL v2 or later |
| Morfeusz 2 (`morfeusz2`) | [Its licence page](http://morfeusz.sgjp.pl/doc/license/) |
| Tesseract language data in `kio2json/tessdata/` | Apache-2.0 (`kio2json/tessdata/LICENSE`) |
| Geist font on the page and in the README images | SIL OFL 1.1 (`frontend/public/fonts/LICENSE-Geist.txt`) |
| `ministral-3b-2512`, the optional model (not in the repository) | Apache-2.0 ([provider notes](docs/small-model-providers.md)) |

## Repository

| Path | What is there |
|---|---|
| `kio2json/` | The extractor: PDF text and OCR, routing, rule extractors, optional model engine, CLI and viewer |
| `config/classes/` | One TOML per document class |
| `evals/` | Field-level F1 harness and recorded results |
| `compose.yaml`, `api.Dockerfile` | Docker Compose services for the batch CLI and the local upload page |
| `frontend/`, `docs/deploy.md` | The doc2json.pl page and how it is deployed |
| `deploy/` | VM setup script, handover `RUN.md`, offline rehearsal and the Compose file for the VM |
| `data/uzp/` | Organizer data and schemas (copy of their repository) |
| `docs/task/` | Challenge brief, FAQ and details |
| `WORKLOG.md` | Current state, open work and the dated log |
