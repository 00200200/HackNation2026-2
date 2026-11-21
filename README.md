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
confirmation from their content, and writes the organizer's JSON for each one. Anything else gets an empty file.

<p align="center">
  <a href="https://doc2json.pl"><img src="docs/readme/web.png" alt="doc2json.pl: drop PDFs on the left, read the JSON on the right" width="100%"></a>
</p>

## The problem

An appeal case is not one document. It is a handful of PDFs, some exported from a word processor and some
scanned, with the same facts written differently in each: parties, identifiers, the procurement, the contested
action and the paid fee. People read them easily; systems cannot, until the data is structured.
<sub>Source: challenge description, UZP, HackNation 2026 (`docs/task/`).</sub>

<p align="center"><img src="docs/readme/classes.png" alt="Three document types: appeal, power of attorney, transfer confirmation; anything else gets an empty file" width="100%"></p>

## How it works

<p align="center"><img src="docs/readme/pipeline.png" alt="Read, route, extract, normalise, write" width="100%"></p>

- **Content, not file names.** Routing reads the text. A file called `scan001.pdf` is handled like `odwolanie.pdf`.
- **No guessing.** A value the document does not state is `null`. Optional model output is kept only when it
  cites a supporting span of the source.
- **Runs on the jury's laptop.** CPU only, offline OCR, installed with `pip install -r requirements.txt`. No API
  key is needed for the default configuration, which uses no language model at all (rules only, 0 model
  parameters). An optional OpenAI-compatible endpoint is described in
  [Use a model endpoint](docs/readme/reference.md#use-a-model-endpoint).
- **New document types in configuration.** Each class is one TOML file in `config/classes/` with its routing cues,
  fields and engines. The disabled fourth class shows how: [enable it](docs/readme/reference.md#enable-the-fourth-class).

## Results

<p align="center"><img src="docs/readme/results.png" alt="Field-level micro F1: 1.000 on synthetic training cases, 0.685 on organizer scans, 0.631 and 0.605 on real local corpora" width="100%"></p>

| Dataset | PDFs | Micro F1 | Appeal | Power of attorney | Transfer |
|---|---:|---:|---:|---:|---:|
| Organizer training cases (synthetic) | 196 | 1.000 | | | |
| Organizer scans (real) | 30 | 0.685 | 0.612 | 1.000 | 0.194 |
| Local corpus 1 (real) | 39 | 0.631 | 0.602 | 0.919 | 0.462 |
| Local corpus 2, dev (real) | 39 | 0.605 | 0.601 | 0.946 | 0.152 |

Rules only, no endpoint configured. None of these is the score on the organizer's hidden test set. The F1 definition
is ours: the organizer has not published theirs.
Method, timings and the OCR comparison: [technical reference](docs/readme/reference.md#results-on-the-training-data-synthetic).
Raw results: [training](evals/results/latest.json), [organizer scans](evals/results/organizer-scans.json),
[local corpora](evals/results/poa-development.json).

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
| Desktop viewer: pages next to the JSON | `.\start.bat gui` | `./start.sh gui` |
| Web app | [doc2json.pl](https://doc2json.pl) | [doc2json.pl](https://doc2json.pl) |

<p align="center">
  <img src="docs/gui/appeal.png" alt="Desktop viewer with an appeal" width="49%">
  <img src="docs/gui/transfer.png" alt="Desktop viewer with a transfer confirmation" width="49%">
</p>

OCR engines, offline install of the language data, the optional model endpoint and every setting are in the
[technical reference](docs/readme/reference.md#run).

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

No code change and no rebuild. Field types, lists, normalisers and model engines:
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
