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

The CLI reads and routes each document locally, then runs the rules for that class. On the jury VM, Ministral can fill a field the rules left null using a verbatim quote from the document. Every value the rules supplied is final. The CLI checks the evidence against the field and its owner. Missing scalar values can remain `null`. [Pipeline](docs/pipeline/pipeline.pdf) · [Model configuration](docs/readme/reference.md#use-a-model-endpoint)

## Results

<p align="center"><img src="docs/readme/results.png" alt="Keyless UZP micro-F1 results, with exact values and source files in the table below" width="100%"></p>

| Dataset | PDFs | UZP micro F1 | Strict micro F1 | Source |
|---|---:|---:|---:|---|
| Organizer training (synthetic) | 196 | 1.0000 | 1.0000 | [Result](https://github.com/00200200/HackNation2026-2/blob/35b1d0159b580268d10aaebbbd6ce7c01aeb2911/evals/results/latest.json) |
| Organizer scans | 30 | 1.0000 | 0.9974 | [Result](https://github.com/00200200/HackNation2026-2/blob/35b1d0159b580268d10aaebbbd6ce7c01aeb2911/evals/results/organizer-scans.json) |
| Local corpus 1, all | 39 | 0.9231 | 0.8900 | [Result](https://github.com/00200200/HackNation2026-2/blob/35b1d0159b580268d10aaebbbd6ce7c01aeb2911/evals/results/ocr-alternatives.json) |
| Local corpus 2, dev | 39 | 0.9244 | 0.8951 | [Result](https://github.com/00200200/HackNation2026-2/blob/35b1d0159b580268d10aaebbbd6ce7c01aeb2911/evals/results/ocr-alternatives.json) |

The public training score uses the account prefixes printed in the PDFs. The local rows report the `fast` Tesseract arm of the OCR-alternatives experiment. All four rows used local rules without a model endpoint. UZP accepts approximate matches for five long fields. Our scorer uses normalized Levenshtein similarity for those fields. The strict column uses the project's earlier scoring method. [Scoring rules](https://github.com/00200200/HackNation2026-2/issues/59) · [Evaluation method](docs/readme/reference.md#measure)

Run `make eval-cases` for the paired native/scan benchmark. The rules recovered all four development bank letters. The three reserved history and detail layouts still missed all 12 PDFs. [Case families and scores](docs/readme/reference.md#case-linked-benchmark)

On five held-out cases in a ten-appeal two-column benchmark, field F1 was 0.9700 with native text and 0.8925 with forced OCR. Unlabelled procurement titles remained missing. [Field results and limits](evals/results/two-column-appeals.json)

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

The setup script installs the jury CLI in `/opt/solution`. The evaluator runs the two-worker command in `RUN.md` from that directory. Before handover, the deployment owner sets `KIO_LLM_API_KEY` in `/opt/solution/.env` alongside `KIO_LLM_BASE_URL=https://api.eu.mistral.ai/v1` and `KIO_LLM_MODEL=ministral-3b-2512`. The same command uses local rules when the key is absent and preserves their output if a model call fails. [Jury command](deploy/RUN.md) · [VM setup and rehearsal](docs/readme/reference.md#deploy-on-the-evaluation-vm)

The jury model has 3.85 billion parameters, including its vision weights. Mistral lists EU and EFTA data centers for its regional inference service. The exact country serving this model is unconfirmed. [Model size](docs/small-model-providers.md) · [Regional inference](https://docs.mistral.ai/inference/regional-inference) · [Privacy policy](https://legal.mistral.ai/terms/privacy-policy/) · [Data Processing Addendum](https://legal.mistral.ai/terms/data-processing-addendum/)

## Run with Docker Compose

Run `docker compose run --rm cli` for the batch or `docker compose up gui` for the local upload page. [Compose setup](docs/readme/reference.md#run-with-docker-compose)

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

## Repository

| Path | What is there |
|---|---|
| `kio2json/` | The extractor: PDF text and OCR, routing, rule extractors, optional model engine, CLI and viewer |
| `config/classes/` | One TOML per document class |
| `evals/` | Field-level F1 harness and recorded results |
| `frontend/`, `docs/deploy.md` | The doc2json.pl page and how it is deployed |
| `data/uzp/` | Organizer data and schemas (copy of their repository) |
| `docs/task/` | Challenge brief, FAQ and details |
| `WORKLOG.md` | Current state, open work and the dated log |
