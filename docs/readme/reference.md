# doc2json technical reference

[Project overview](../../README.md)

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

Without endpoint credentials the jury configuration runs three rule-based extractors locally. Each class has a TOML file
that selects its routing rules, output fields and extraction engines. New classes can use
label patterns or an optional language model.

## Deploy on the evaluation VM

1. **Request the VM.** Submit one request per team using the form in the
   organizer’s instructions. When the login arrives, connect over SSH. The
   deployment account needs read access to the private GitHub repository.
   [Organizer’s VM instructions and request form](../../data/uzp/VM.md)

2. **Run `vm_setup.sh`.** While the VM is online, run these commands as the
   deployment user. Setup copies the checked-out commit into `/opt/solution/repo`,
   installs Python 3.13 and the pinned requirements, and smoke-tests a transfer
   and a scanned appeal outside the evaluator directories.

   ```sh
   git clone --single-branch --branch main git@github.com:00200200/HackNation2026-2.git ~/kio-release
   cd /opt/solution
   bash ~/kio-release/deploy/vm_setup.sh
   ```

3. **Run the offline rehearsal.** On the VM, the following command prepares a
   disposable x86-64 Ubuntu 24.04 container with two CPUs and 16 GiB. It uses
   the installed Python as the reference. For both the network-disabled run
   and the run after a container restart, it compares all 226 organizer files
   by path and bytes and prints a time estimate for 150 PDFs. The script
   removes its temporary outputs, containers and snapshot image when it exits.

   ```sh
   cd /opt/solution
   bash repo/deploy/rehearse_vm.sh /opt/solution/.venv/bin/python
   ```

   The development host’s Docker engine timed out before starting Ubuntu.
   The Ubuntu offline run, two-vCPU timing and reboot result are unverified.
   On the shared Apple M1 host, the network-denied run (rules-only profile,
   extraction revision `7a1c45b`) wrote output byte-identical to the reference
   run for all 226 local files (196 synthetic training PDFs, 30 organizer scans)
   in 399.77 seconds with two workers. The same mix scales to about 4 min 25 s
   for 150 PDFs on that host.
   [Rehearsal measurements](../../evals/results/vm-2vcpu.json)

4. **Copy `RUN.md` and check the real VM.** Setup installs the native command
   automatically. To restore it for handover, run the following from
   `/opt/solution`.

   ```sh
   install -m 644 repo/deploy/RUN.md /opt/solution/RUN.md
   ```

   Place sample PDFs under a fresh case name in `/opt/solution/input`, run
   the command from `RUN.md` and inspect the matching JSON files. Run
   `sudo reboot`, reconnect, remove your sample outputs and repeat. Remove
   your sample inputs and outputs after the check. The organizer owns both
   directories. Keep them in place for evaluation.

To update, fetch the desired release in `~/kio-release`, check out its commit
and repeat steps 2–4 using the existing clone. The rules-only profile uses
**no external services**. For a keyed deployment, create `/opt/solution/.env`
with mode 600, configure the agreed provider and model there, and identify
the service in `RUN.md`. [Model profile settings](#use-a-model-endpoint)

**Docker Compose fallback.** On the VM, use Compose v2.24 or later. From
`/opt/solution`, build the jury image while online, then install the fallback
command in `RUN.md` if this is the profile the evaluators should run.

```sh
docker compose -f repo/compose.yaml build cli
sed 's|^sudo env PYTHONPATH=.*|sudo docker compose -f repo/deploy/compose.vm.yaml run --rm -T cli|' repo/deploy/RUN.md > RUN.md
```

Run the command in the installed `RUN.md` for the same handover check.
The CLI mounts the evaluator directories, uses the local image and exits after
the batch. For the optional upload UI on port 8080, run
`docker compose -f repo/deploy/compose.vm.yaml up -d gui`. Docker restarts the
UI after a reboot.

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
on Apple Silicon runs it under emulation, which is slower.

Both services read the host's `config/classes/` directory. See the
[pipeline architecture](#how-it-works), [class configuration example](#class-file-reference)
and [instructions for adding a class](#add-a-class). The handover requirements are in
[§3.5 of the task rules](../../docs/task/regulamin.pdf).

## Run

From the repository root, create a virtual environment with 64-bit CPython 3.13.

| Shell | Create | Activate |
|---|---|---|
| Windows PowerShell | `py -3.13 -m venv .venv` | `.\.venv\Scripts\Activate.ps1` |
| macOS or Linux | `python3.13 -m venv .venv` | `. .venv/bin/activate` |

Use the activated shell for the install and run commands below. `requirements.txt` lists only pinned PyPI
packages and no local paths, so pip downloads only from PyPI (`pypi.org` and `files.pythonhosted.org`). Run the install
from the repository root; from another directory, pass the file's full path to `-r`. pip installs the
Tesseract native libraries from PyPI. The Polish and English fast models (8.88 MB, Apache-2.0) ship in
`kio2json/tessdata/` with their licence. They come from a pinned `tessdata_fast` revision, and the CLI checks both
SHA-256 hashes before the first OCR page. Run `python -m kio2json` from the repository root. The rules-only CLI and
viewer process PDFs offline.
[Platform wheels](https://pypi.org/project/tesserocr/2.13.0/#files)

```
python -m pip install -r requirements.txt
python -m kio2json                                   # reads ./input, writes ./output
python -m kio2json --input some/input --output some/output
```

By default the CLI uses up to four worker processes, limited by the CPUs available to Python.
Use `--workers 1` for a sequential run, or set `--workers` (also spelled `--jobs`) to a value from 1 to 8. Each Tesseract instance uses one thread. A PDF worker can recognize up to three retained scan pages concurrently. The CLI writes results in sorted input order.

The default OCR setting is `tesseract-dpi`. Set `KIO_OCR_ENGINE` to choose another mode for the CLI or viewer.

| Setting | Pages requiring OCR |
|---|---|
| `tesseract-dpi` | Polish Tesseract with the source resolution set to the 300 dpi render, including e-mail crops. |
| `tesseract` | Polish Tesseract with automatic source-resolution estimation. |
| `rapidocr` | RapidOCR v6 on CPU. |
| `hybrid` | Start with `tesseract-dpi`. Retry OCR pages with RapidOCR when the document is unreadable or fails to match a class. |

The requirements include the CPU RapidOCR and ONNX Runtime wheels used by the keyed model profile.
Their packaged models support an offline first run.
For example, use `export KIO_OCR_ENGINE=rapidocr` in a POSIX shell or
`$env:KIO_OCR_ENGINE = "rapidocr"` in PowerShell.

Each PDF gets a JSON at the same relative path and file stem. Appeals, powers of attorney and
bank-transfer confirmations get the organizer's structure. Unrelated documents get `{}`. Transfer accounts preserve the printed country code, if present, and omit whitespace. In the default keyless profile, an unreadable PDF receives `{}` and a diagnostic on stderr. The CLI processes the remaining PDFs and exits with status 1. The keyed organizer profile uses the document recovery described below. A nonblank scan that yields fewer than two alphabetic words after page counters are removed
reports `no readable text after OCR`. Blank pages may stand alone or appear beside a readable page.

To open the Polish document viewer, run `python -m kio2json.gui`. It opens a browser on
`127.0.0.1:8000`. Select PDFs and name the case, or enter a folder containing cases. Click
**Analizuj dokumenty**, choose a document and compare its pages with the JSON. **Pobierz wyniki (.zip)**
downloads one JSON per PDF under its case folder. Failed documents show the reason and get `{}` in the ZIP. The viewer keeps temporary copies for the current session. The default configuration
works offline. Page provenance is used internally and the output follows the organizer’s JSON schema.

When a case contains an appeal and a mandate or receipt, the viewer flags differences in party
identifiers, attorney names and procedure numbers. It also flags unusual appeal fees when the
procurement title identifies the category. Select a document to see which files to compare.

Set `KIO_CASE_REPAIR=1` to enable sibling OCR repair in the CLI or viewer. The CLI finishes its
parallel PDF reads before comparing documents in each `input/<case>/` folder. A replacement needs
a damaged printed value and one compatible, independently read spelling in a different document
class. Registry numbers also need a matching party identifier or name. A native text value can be
corrected only when its NIP checksum fails. Missing fields stay empty.

| Start from the repository | Windows | Linux or macOS |
|---|---|---|
| Run the CLI on `input/` and write to `output/` | `.\start.bat` | `./start.sh` |
| Open the viewer | `.\start.bat gui` | `./start.sh gui` |

[Transfer confirmation in the viewer](../../docs/gui/transfer.png) · [Appeal in the viewer](../../docs/gui/appeal.png)

## How it works

1. `kio2json/pdf_text.py` reads the first three pages with pdfplumber for extraction.
   Pages with no usable text, including scans with a selectable page counter, go through OCR at 300 dpi.
   If those pages require OCR and appear unreadable, the reader checks later pages for readable text
   before reporting a document error. When Tesseract reads
   a possible e-mail address with a missing `@`, an English single-word pass rereads that crop. The extractor accepts the separator
   only when the rest of both readings agrees. Call `read_pages(path, word_boxes=boxes)` with
   an empty list to collect raw words and their rectangles alongside the page strings. Coordinates
   are PDF points from the top left, with one-based page numbers. Required Tesseract and RapidOCR
   pages use a 180-second recognition watchdog at 300 dpi. After a timeout, the reader retries once
   at 150 dpi if the document and batch still have time. It gives the retry the smaller of 60 seconds
   and the remaining budget. Tesseract checks its timer during recognition, so setup and cancellation
   can add wall time. Verification crops get up to 10 seconds each and optional full-page reads get up to
   180 seconds each. All optional OCR shares a deadline of
   300 seconds from the start of a PDF. The CLI and GUI also share one cutoff across the batch,
   10.8 seconds per input PDF with a minimum of 300 seconds for small batches. For the jury’s 150 PDFs
   this stops rereads after 27 minutes and leaves 18 minutes for remaining work. When either deadline
   expires, extraction uses the readings already available. Every required first-pass page keeps its full
   recognition timeout. RapidOCR runs in a reusable
   child process. A watchdog kills a stalled RapidOCR worker at its page deadline.
2. The CLI loads `config/classes/*.toml` and the files selected by `--classes` once per batch. `kio2json/class_config.py` matches the
   page text against enabled definitions in ascending `priority`, then class ID order. The first
   match wins. The three organizer classes share the content classifier in `kio2json/classify.py`.
   It reads headings in document order. A transfer normally needs two distinct accounts, a confirmation
   heading or execution status, and a transaction amount or date. Rejected payments and payment
   requests get `{}`.
3. The rule extractors recover party blocks and receipt fields from columns. Each page keeps its source,
   so a scanned attachment cannot enable OCR repairs on a native receipt. Configuring an endpoint enables
   first-page model routing after the rules reject a document. The model extracts from the original reading
   and, on scans, an independent OCR reading. Each accepted value needs a supporting span. The class rules
   fill gaps using the reconstructed layout. The CLI and viewer share this pipeline.

[Pipeline diagram (PDF)](../../docs/pipeline/pipeline.pdf)

## Add a class

A new document class needs one TOML file and no Python. Without extra flags the CLI and viewer load
only the three organizer classes, so unrelated documents in the jury's set still get no fields.

1. Generate a class file from a sample PDF. The tool reads the `Label: value` lines on page 1,
   writes `classes/accession.toml` and prints how that file routes and reads the sample.

   ```sh
   python -m kio2json.classes new accession --from-pdf examples/input/sprawa-demo/zgloszenie_przystapienia.pdf
   ```

2. Edit the file: the routing cues and threshold, the output keys, normalizers and checks. The
   reference below lists every key. [examples/classes/accession.toml](../../examples/classes/accession.toml)
   is a finished example for a notice joining an appeal (zgłoszenie przystąpienia).
3. Run the CLI with the class directory. `--classes` also accepts a single TOML file and can be repeated.

   ```sh
   python -m kio2json --classes classes --input input --output output
   ```

4. Open the viewer with the same flag: `python -m kio2json.gui --classes classes`. It lists the loaded
   classes and names the cues that chose each document's class. The viewer reads the class files again
   on every click on **Analizuj dokumenty**, so a file dropped into `classes/` applies without a restart.
5. Add `--explain DIR` to the CLI run to write `DIR/<case>/<name>.trace.json` for each PDF. It records the
   class, the matched cues and score, each field's page, source line and engine, and every failed check.
   The folder must be outside `--output`, because every JSON there is scored.

`python -m kio2json.classes list --classes classes` prints the classes a run would load.
`config/classes/participation.toml` is a disabled demo class. Turn it on for one run with
`python -m kio2json --enable participation`; `--enable` works for any class whose file sets `enabled = false`.

To see the example end to end, run the CLI on the invented sample with and without the example class:

```sh
python -m kio2json --input examples/input --output /tmp/demo           # the notice produces {}
python -m kio2json --input examples/input --output /tmp/demo --classes examples/classes --explain /tmp/demo-trace
```

### Class file reference

| Key | Meaning |
|---|---|
| `id` | Unique lower-case ID, also used in logs and traces |
| `name` | Name shown in the viewer |
| `enabled` | `false` keeps the class off until `--enable <id>` (default `true`) |
| `priority` | Classes are tried in ascending priority, then ID; the first match wins (default 100; organizer classes use 10 to 30) |
| `engines` | `["labelled_fields"]` reads values after printed labels. `"llm"` asks the configured model endpoint and needs the `KIO_LLM_*` variables |
| `[routing.cues]` with `threshold` | Phrase = weight. The class applies when the weights of the phrases found reach the threshold. Phrases match whole words, ignoring case and line breaks. A negative weight counts against the class |
| `routing.required`, `routing.forbidden` | Regular expressions (case-insensitive, `^` and `$` per line). Every `required` one must match; any `forbidden` match rejects the class |
| `routing.headings`, `routing.pages`, `[routing.evidence]` | A whole-line pattern with spaces removed; how many pages to search (default 1); a capture that must find `minimum` distinct values |
| `[fields.<key>]` | One output key. `type` is `string`, `integer`, `number`, `boolean`, `object` (with `fields`) or `list` (with `items`). `pattern` captures the value in one group. `nullable` defaults to `true` |
| `normalizer` | `iso_date`, `money`, `account_number`, `krs`, `nip`, `regon` or `pesel` |
| `validators` | `"nip"`, `"regon"`, `"pesel"`, `"iban"` (checksums), `{ name = "date_range", min = 2021-01-01, max = 2030-12-31 }` (needs `iso_date`), `{ name = "one_of", values = ["A", "B"] }` |
| `on_invalid` | `"null"` (default) writes null for a value that fails a check; `"warn"` keeps it and reports it in the trace and viewer |

The `labelled_fields` engine needs values printed after fixed labels. A layout without labels needs the
`llm` engine and a model endpoint; the jury configuration runs without one. The three organizer classes
route through `classifier = "kio2json.classify.classify"` and extract with Python, because their real
layouts vary more than labels can describe. Treat class files as trusted configuration: classifier and
extractor paths load Python callables.

## Use a model endpoint

The primary small-model candidate is Mistral’s open-weight `ministral-3b-2512` (3,849,090,048 total parameters). Both the language and vision weights count toward the 8B ceiling. The regional API supports native JSON Schema. Its documented processing geography includes EU and EFTA countries, so the jury deployment needs a narrower location commitment. [Provider comparison and sources](../../docs/small-model-providers.md)

To run the measured rules-first profile, export the Mistral credential in your shell and run the following command.

```sh
export KIO_LLM_BASE_URL=https://api.eu.mistral.ai/v1
export KIO_LLM_MODEL=ministral-3b-2512
export KIO_LLM_API_KEY="$MISTRAL_API_KEY"
export KIO_LLM_OUTPUT=spans KIO_LLM_MODE=RL KIO_LLM_ROUTING=supported
export KIO_LLM_GAP_SCOPE=incomplete KIO_LLM_CHARGE_FOCUS=true
export KIO_LLM_DUAL_OCR=false KIO_LLM_TOKEN_PARAMETER=max_tokens
export KIO_LLM_INLINE_SYSTEM_PROMPTS=false KIO_LLM_TIMEOUT_SECONDS=120
python -m kio2json --input input --output output --jobs 3
```

In `spans` mode the model copies one short passage per scalar into a class-specific native schema. The application locates the passage in up to 8,192 UTF-8 bytes of page text, checks token boundaries and derives dates, amounts, identifiers and organizer codes locally. Each class can supply a short `span_instructions` string in its TOML. The example uses local Tesseract for scans. The model receives text; its vision encoder is included in the published parameter count. The measured model profile selects three document workers.

The rules read each document first. In the profile above, a rejected first page needs evidence of a filing, mandate or payment before the model can route it. On native documents and on locally recognized scanned appeals and receipts, a general model call requires a missing party or core payment detail. Scanned powers and documents routed by the model remain eligible for gap filling. A separate appeal request uses the first charge and the dated introductory act, with a 320-token limit and a 30-second deadline. The rules verify the quoted act and date and supply the organizer’s canonical description.

Set all three variables in the process environment or in an ignored `.env` in the working directory.
Environment values take precedence. The application has no built-in endpoint or credential.

| Variable | Value |
|---|---|
| `KIO_LLM_BASE_URL` | Your provider’s API base URL, including its version path if required |
| `KIO_LLM_MODEL` | Model ID served at that endpoint |
| `KIO_LLM_API_KEY` | Credential accepted by the endpoint |

Other OpenAI-compatible providers can use the same CLI or viewer. When only the three connection variables are set, the bundled classes use model-first
extraction with rule fallback (`KIO_LLM_MODE=LR`). The router asks the model about the first page after
the local rules reject the document (`KIO_LLM_ROUTING=fallback`). On a scan, RapidOCR provides a second
reading alongside Tesseract. The two readings share a 16,384-byte budget. A citation must match one
displayed source. Dates, amounts and identifiers must cover complete printed values.

For compatible servers, `KIO_LLM_OUTPUT=schema` requests native JSON schema support. The default is
`json`. `KIO_LLM_TIMEOUT_SECONDS` sets the request deadline (1–600 seconds, default 180). The engine
allows one structured-output correction. On a model or secondary OCR error, the keyed organizer
profile retries the document with local rules, reports recovery, and continues the batch. An unreadable
document yields `{}`. Custom class directories use the engine chains in their own TOML files.

## Measure

```
uv run python -m evals.run --quick            # dev subset, before a push
uv run python -m evals.run                    # use the original references for all 60 cases and the negatives
uv run python -m evals.run --correct-training-accounts  # restore prefixes printed in the training PDFs
uv run python -m evals.run --organizer-scans  # 30 separately labelled scans
uv run python -m evals.field_report --errors  # which fields fail, with list items paired inside their parent
uv run python -m evals.field_report --force-ocr --errors   # ignore the text layer: what OCR costs
make eval-real HN_REAL_SPLIT=dev              # /Users/domin/hn2-real-eval, or set HN_REAL_CORPUS
uv run python -m evals.run --corpus "$corpus" --split test
uv run python -m evals.run --corpus "$corpus" --split dev --detail-out "$corpus/dev-detail.json"
uv run python -m evals.field_report --corpus "$corpus" --split dev --force-ocr --errors
```

Set `corpus` to a directory containing `cases/<case_id>/<name>.pdf` and `gold/<case_id>/<name>.json`.
An empty gold file marks an unrelated document. Corpus runs write aggregates to
`evals/results/corpus-latest.json`. Set `HN_REAL_SPLIT` to `dev`, `test`, or `all` (default) for `make eval-real`.
The optional `--detail-out` file must be outside every checkout of this repository and its Git metadata.
Both commands check the selected directories, PDFs and references before reporting scores, including with
`--pred`. Invalid inputs or an extractor failure exit with status 2 and preserve the previous results and gate.
Test-split diagnostics omit local paths. Missing or malformed predictions count as missed reference fields.
Training mode checks selected files against the organizer inventory committed in `data/uzp/dane`. Each known
positive reference needs fields for its expected class. The negative-output target requires an empty JSON object. A zero-byte prediction fails. Account fields are compared after removing whitespace, with every printed letter and leading zero retained.
For a case-level split, put `{"dev": [...], "test": [...]}` in `SPLIT.json` at the corpus root. Each list
contains case folder names. The default `--split all` scores the whole corpus, including corpora without a split.
Inspect field errors on dev. Use aggregate scores to evaluate test. The organizer scan mode validates the committed PDF/reference pairs in `data/uzp/dane/skany` and writes `evals/results/organizer-scans.json`. The synthetic training and scan scores have separate result files.

`evals.run` reports UZP micro F1 and macro F1 by document, class and field path. Empty reference and prediction values contribute zero to F1. A wrong value contributes one FP. Five long strings accept an 80% match, measured here with RapidFuzz normalized Levenshtein. UZP has yet to specify the similarity function. The historical score appears as `micro_f1_strict`. [UZP scoring rules](https://github.com/00200200/HackNation2026-2/issues/59)

## Results on the training data (synthetic)

The full run below uses `--correct-training-accounts`. The original references omit two printed `PL` prefixes in each of 48 transfers. Scoring the same predictions against those references gives 0.9758 UZP micro F1 and 0.9585 strict micro F1 (96 field mismatches). [Full evaluation](../../evals/results/latest.json) · [Expected changes by training case](../../evals/results/p0-conventions.json)

| Metric | Value |
|---|---|
| `micro_f1`, all 60 cases and the negatives | 1.000 |
| `micro_f1`, cases 51-60 | 1.000 |
| `classification_accuracy` | 1.000 |
| `negatives_empty` | 1.000 |

Read these as a regression check. The rules were written by looking at these same synthetic
documents, cases 51-60 included, so no case here is unseen and the 51-60 figure is no estimate
of how the rules generalize. UZP describes the hidden evaluation cases as synthetic documents based on real cases. [Task brief](../../docs/task/BRIEF.md#data)

A separate native-text differential test compares the class and serialized fields of 175 invented PDFs
with a snapshot from integration base `3210643`. It includes 135 review cases and 40 additional
documents. Two suites compare 285 invented grant, receipt and routing PDFs and 205 appeal and routing inputs with integration base `e051dfa`. Each expected change records the original value, replacement and reason. [Fixtures and regeneration commands](../../tests/snapshots/README.md)

Forced OCR on all 196 training PDFs (307 rendered pages) gave strict field F1 **0.900**
with automatic source resolution and **0.884** with explicit 300 dpi. The comparison used the rules recorded in the measurement file. To run the
current rules, select `KIO_OCR_ENGINE=tesseract-dpi` and run
`uv run python -m evals.field_report --force-ocr --errors`. [OCR measurements](../../evals/results/ocr-engines.json)

## Rules on real documents and organizer scans

Revision `ca2975392` was evaluated with local rules and with the documented live Ministral 3B profile. The two local datasets contain real documents and use whole-case splits. Corpus 1 contributes all 39 development PDFs, including its previously evaluated split. Corpus 2 contributes 39 development PDFs from 14 cases. Its 60 test PDFs are reserved for the merged system. The organizer supplied a separate set of 30 labelled scans, ten per target class. The scan command stages the committed PDF/reference pairs as one batch with neutral filenames. [Organizer scan set at the measured revision](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/skany)

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

On corpus 1 the model raised transfer F1 by 0.1407. On corpus 2 dev it raised transfer F1 by 0.0421 and appeal F1 by 0.0099. Both profiles matched all ten organizer appeals and powers of attorney, and nine of ten transfer confirmations. [Combined measurements](../../evals/results/round2-integration.json)

Exact counts compare the complete JSON, including list order. A/P/T denotes appeals, powers and transfers. Each private set includes 11 unrelated PDFs. Earlier appeal measurements are available separately. [Real appeal round](../../evals/results/appeal-real-development.json)

Micro F1 pools field matches across documents. Macro F1 averages the three class scores. The combined measurement file includes correct routes for every class and both profiles. This historical measurement counted zero-byte outputs as negatives. Timing includes OCR and extraction on a shared host. [Earlier appeal development measurements](../../evals/results/appeal-scan-development.json) · [Earlier grant development measurements](../../evals/results/poa-development.json) · [Organizer scan report](../../evals/results/organizer-scans.json)

The earlier model-engine experiment compared two profiles on the 17-document corpus 1 holdout. [Model results](../../evals/results/llm-real-docs.json)

The scanned-transfer update was evaluated on a five-case organizer development half and a five-case holdout per class. Their combined transfer routing was 8/10, up from 2/10 on the integration baseline. Transfer field F1 was 0.8667 on the development half and 0.5833 on the holdout. [Scanned-transfer measurements](../../evals/results/scanned-transfers.json)

On all 30 organizer development scans, the rules routed 10/10 transfer confirmations. Nine matched every field literally (59/60 fields, transfer F1 0.9833). The outstanding title contains a severely degraded name and abbreviation. Across all three classes the run averaged 9.23 s/PDF on the shared Apple M1, with a maximum of 19.02 s. With the integrated power-of-attorney rules, micro F1 reached 0.6312 on corpus 1 all, 0.7160 on its dev subset and 0.6816 on corpus 2 dev. [Round 2 measurements](../../evals/results/scanned-transfers-round2.json)

On the shared 16 GB Apple M1, the integrated CLI processed 30 organizer scans in 36.12 s with four rules workers and 44.91 s with three Ministral workers. The 150-PDF batch took 57.54 s and 70.38 s respectively. It used two copies of the 30 scans and 90 training PDFs. [Combined measurements](../../evals/results/round2-integration.json)

### Optional OCR under load

The organizer allows 45 minutes for 150 PDFs. The batch uses 60% of that allowance for optional OCR,
scaled by the number of input PDFs. Required page reads continue after the cutoff.

On the shared 16 GiB M1, four local rules workers produced byte-identical outputs in both runs below.
The CPU was 76.5% idle before the ordinary scan run. The loaded run added one busy loop per CPU core
and reached a one-minute load average of 89.7. Training outputs also matched the baseline at
`dbda151` byte for byte, including all 16 empty negatives.

| Input | No added load | Eight busy loops | Bytes matched | Accuracy |
|---|---:|---:|---:|---|
| 30 organizer scans | 41.54 s | 216.89 s | 30/30 | 29/30 exact |
| 196 training PDFs | 13.65 s | 47.35 s | 196/196 | 1.000 micro F1 |

The 108-document calibration covered all 30 scans and both private development pools. The longest
optional work in that pass took 33.18 seconds. A separate cold repeat of a repaired scan took 48.59
seconds for optional OCR and 51.85 seconds for the whole document. At four times that wall time the
document would take 207.4 seconds, within the 300-second document allowance. A separate run advanced
the deadline clock four times as fast and divided optional engine timeouts by four. All 135 optional
Tesseract reads and three RapidOCR reads finished across the 108 PDFs.

With these limits, eight busy loops and `--jobs 1`, the CLI processed the 150-PDF mix in **401.87 seconds**
(6 min 42 s of the jury’s 45 min). All 150 outputs matched the corresponding four-worker readings.
The mix contained two copies of each organizer scan and 90 training PDFs. This timing preceded the
final change to handling expired optional page reads. [Measurements and output digests](../../evals/results/adaptive-ocr-budget.json)

With the 180-second primary watchdog, two workers processed all 226 public PDFs in 160.75 seconds.
Every output matched `328f705` byte for byte. In a separate serial run on three scans, suspending the
OCR worker for 65 seconds during the first page caused one document failure with the old watchdog.
The new watchdog finished in 83.76 seconds including the pause, and all three outputs matched their
ordinary readings. [Watchdog measurements](../../evals/results/first-pass-watchdog.json)

In the earlier runtime-only experiment on a 16 GiB M1 MacBook Air, four workers processed 30 organizer scans in 37.15 seconds and a mix of
60 scans and 90 training PDFs in 74.42 seconds. Peak sampled process-tree RSS for the mix was
1,504 MiB. All 226 training and scan outputs matched sequential main (`5297660`) byte for byte.
[Batch timings and per-PDF profile](../../evals/results/batch-runtime.json)

The reported times cover these local datasets. OCR runs locally. Under the updated rules, a remote
OCR service would count toward model parameters. [Organizer evaluation rules](../../data/uzp/README.md)

## Ministral on development documents

The paired comparison uses the rules at `eabbb31`. The cold 150-PDF run used `bf57506`. Replaying the same model responses after the date fix reproduced all 108 development outputs byte for byte. The combined table above includes the subsequent receipt-routing and attorney-name fixes.

A cold run of the production CLI processed **150 PDFs in 335.64 seconds** on a 16 GB Apple M1 with three workers, including local OCR and 106 successful regional API requests. The mix comprised 108 development PDFs and 42 public training PDFs. The organizer scan group averaged 3.33 wall seconds per PDF. All outputs completed, with zero retries or recoveries. On the 91-PDF development pool, the fresh responses scored **.7208 micro and .7079 macro**. The live micro / macro scores were .7097 / .6701 on corpus 1 dev, .7104 / .6747 on corpus 2 dev, and .7394 / .7040 on organizer scans. The jury’s 45-minute allowance applies to its own machine and document mix.

The rules-first profile above uses `ministral-3b-2512` and local Tesseract. The paired comparison below uses the same primary readings and captured API responses for each policy. Corpus 1 all includes its 22 dev PDFs and 17 additional development PDFs. The 91-PDF row pools corpus 1 dev, corpus 2 dev and all organizer scans. The coordinator reserved corpus 2 test for the final integrated system.

| Development set | PDFs | Rules micro / macro | 3B micro / macro | 3B appeal / mandate / transfer F1 | 8B comparison micro / macro |
|---|---:|---:|---:|---:|---:|
| Corpus 1 dev | 22 | .6973 / .6628 | .7016 / .6545 | .7173 / .7879 / .4583 | .7128 / .6741 |
| Corpus 1 all | 39 | .5872 / .5519 | .6196 / .6230 | .6168 / .6783 / .5741 | .6237 / .6211 |
| Corpus 2 dev | 39 | .5248 / .3619 | .7027 / .6668 | .7133 / .4706 / .8167 | .6529 / .4838 |
| Organizer scans | 30 | .5633 / .4711 | .7360 / .6943 | .7511 / .8108 / .5208 | .7147 / .6553 |
| Pooled | 91 | .5858 / .4848 | .7146 / .6969 | .7265 / .7202 / .6439 | .6910 / .6098 |

Across the 91 PDFs, the 3B profile added 207 correct field matches, lost five and introduced 47 net false positives relative to the rules. It made 18 routing requests, 57 general extraction requests and 17 first-charge requests. In isolation, those 17 first-charge requests added four correct matches and removed four false positives. All 18 unrelated PDFs stayed empty without an API request. Three of the 30 organizer scans matched their full reference field sets. The secondary five-field fuzzy proxy scored .7325 for the 3B profile and .6006 for rules. [Per-field counts, per-class scores, timings and ablations](../../evals/results/small-model.json)

The larger `ministral-8b-2512` checkpoint has 8,918,026,240 parameters and exceeds the 8B submission limit. It serves as a development comparison. An on-device smoke test of the 3B Q4_K_M quantization with llama.cpp on a 16 GB Apple M1 recovered the date and amount of an invented transfer in 14.97 seconds. The development corpus scores in the table use the regional API. A separate local CPU check put the company into the natural-person name field on eight of ten invented grants. [Checkpoint and hosting evidence](../../docs/small-model-providers.md) · [Local grant review](https://github.com/00200200/HackNation2026-2/pull/26#issuecomment-7069029860)

To try the same checkpoint locally, save the pinned Q4_K_M file outside the checkout as `ministral.gguf` and start llama.cpp. With the regional profile variables shown above, override the connection variables for the local server and use one document worker. [Pinned GGUF release](https://huggingface.co/unsloth/Ministral-3-3B-Instruct-2512-GGUF/tree/7564922f37fa5bbb62b87f09a55c12f1f91d7a6a) · [llama.cpp b12608](https://github.com/ggml-org/llama.cpp/releases/tag/b12608)

```sh
llama-server -m ministral.gguf --host 127.0.0.1 --port 18089 -c 8192 -np 1 --alias ministral-local
# In another shell with the extraction settings above
export KIO_LLM_BASE_URL=http://127.0.0.1:18089/v1 KIO_LLM_MODEL=ministral-local KIO_LLM_API_KEY=local
python -m kio2json --input input --output output --jobs 1
```

## OCR on real development documents

All five runs used the same frozen extraction rules and 20 real development PDFs. Native text was
used where available. Tesseract's explicit-DPI mode gained **0.0301** dev micro-F1 over automatic DPI.
In that rules-only experiment, the hybrid improved on explicit DPI by **0.0133**. Keyless extraction keeps the `tesseract-dpi` setting. The earlier DeepSeek Flash run combined Tesseract and RapidOCR on scans. The regional Ministral recipe above uses Tesseract alone. [OCR measurements](../../evals/results/ocr-engines.json) · [Flash configuration](../../evals/results/llm-real-docs.json)

| Variant | Field micro-F1 | Macro-F1 | Routed correctly, appeal / power / transfer / other | Wall s / OCR page | CPU s / OCR page | Peak RSS, MiB | Installed MB |
|---|---:|---:|---|---:|---:|---:|---:|
| T0 | 0.3864 | 0.2794 | 7/7 / 2/3 / 0/4 / 6/6 | 3.07 | 2.32 | 493 | 221.27 |
| T1 | 0.4164 | 0.2915 | 7/7 / 2/3 / 0/4 / 6/6 | 5.98 | 3.02 | 312 | 221.27 |
| T1-PNG | 0.4164 | 0.2915 | 7/7 / 2/3 / 0/4 / 6/6 | 1.78 | 1.73 | 425 | 221.27 |
| R | 0.4588 | 0.3693 | 7/7 / 2/3 / 2/4 / 6/6 | 14.27 | 15.19 | 1035 | 434.15 |
| TR | 0.4297 | 0.3841 | 7/7 / 2/3 / 2/4 / 6/6 | 10.11 | 8.79 | 984 | 434.15 |

T0 uses automatic source resolution. T1 sets 300 dpi. T1-PNG isolates lossless PNG ingestion.
R runs RapidOCR throughout. TR retries an unrouted or unreadable T1 document with RapidOCR.
Macro-F1 averages the three target classes. Timing includes the whole batch on a shared Apple
M1, divided by its 34 distinct OCR pages. TR retried 9 documents (14 additional OCR pages).
Peak RSS covers the process tree. Installed sizes are decimal MB excluding pip, bytecode and
the interpreter. The six unrelated documents contribute routing outcomes. No private test cases
were scored for this comparison.

The default engine was measured again after the extraction rules began tracking page sources.
The real-dev result is in [the OCR branch corpus report](https://github.com/00200200/HackNation2026-2/blob/5c4eff29d5872d64845ec533a3df0af9ba174740/evals/results/corpus-latest.json). The
`provenance_check` entry records the paired native-text and forced-OCR checks on the same
rules. [OCR results](../../evals/results/ocr-engines.json)

## Known limits

- A sole trader’s mandate can identify the person separately from the registered business name. The extractor reads the grantor’s declaration, owner fields on a CEIDG card, or an explicitly labelled proprietor signature. A registered business name can supply the person when exactly one end prints an identifiable personal name. The mandate schema records the NIP and has no REGON field. A damaged name or a signature without an identified signer can still leave a field empty.

- An appeal can name the contracting authority by its role in conducting or awarding the procurement. A numbered list can identify joint authorities and mark one as the lead. An unfamiliar caption or a nearby name without local organization, address or registry evidence can leave the party list empty.

- In rules-first native-schema mode, a receipt amount, execution date, singleton appeal party name or procurement title can be reconsidered when its first page contains a conflicting, locally readable value. The model selects a candidate ID in one request per disputed block. The extractor copies the corresponding printed span and normalizes it locally. Abstention or a failed request preserves the rule value. If OCR misses the correct digits in every reading, this step cannot recover them.

- For appeals with parallel sections, the reader looks for a persistent gap between overlapping blocks of text with independent headings. A shared heading above full-width prose stays after both columns. Sparse cards and word boxes that disagree with the transcript can leave the original order ambiguous. A procurement title without a readable label can still be missed. [Two-column appeal evaluation](../../evals/results/two-column-appeals.json)

- On two-column receipts a payment amount can sit beside a different label. The reader checks the amount's column and currency. A damaged account, reference or remittance title can still be unreadable after the receipt is identified.

- A bank letter can attest an executed payment in prose. A history export needs a single identifiable posted transfer or a clearly marked detail section. If several rows could own an amount or account, the extractor can leave the statement empty.

- A receipt that shows only acceptance for future execution can remain unclassified. On damaged scans, a booking date and debit can establish a completed payment even when the account roles are unreadable. The affected account fields stay null.
- A model can cite the wrong party’s valid source text.

- Appeal extraction reads the first three pages. A signature or dated notice later in the PDF can be missed.
  Scanned appeal covers use printed word positions to reconnect party labels with their address blocks.
  The extractor checks ambiguous contact details and reference prefixes against cropped words.
  Explicit party labels and filing clauses can identify the parties. An unlabelled list, an ambiguous
  column alignment or an inflected company name can still leave a party missing. A plain title can include
  lowercase continuation rows before the next labelled field. A challenge date needs a link to the act
  or its notification. Separate filing, invoice and statutory dates can appear on the same page.
  A searchable scan with a damaged text layer can be reread when its cover resembles an appeal.
  The retry checks the class from the page image. Poorly recognized names and signatures outside the opening pages remain common sources of error.
- Receipt routing uses evidence that a payment was executed, its amount or date, and the participating
  accounts. A booking table or bank letter needs both an amount and a date. The extractor binds payer
  and payee separately from fee and refund accounts. Explicit operation or execution dates and transaction IDs take
  precedence over posting dates and daily sequence numbers. An unclear role or conflicting value can
  leave a field empty. For an unfamiliar split confirmation heading, the fallback requires a single
  labelled amount, a transaction date and distinct, explicitly owned accounts. A register or a
  payment with an explicit refusal can therefore produce an empty object.
- First-page word positions can recover fields whose labels and values occupy different rows or columns.
  OCR can still split a title or change an amount. For an unrouted scan with confirmation and transaction
  evidence, the default engine can reread the first page at automatic resolution. Conflicting dates,
  amounts or transaction IDs prevent that retry from supplying a result.
- A partially masked account can identify a payment role when its field is explicit, the other account
  passes the Polish IBAN checksum, and the confirmation supplies the amount and date. The masked number
  is null. OCR also supports fully masked fields. Digit repairs apply only to OCR text and require a
  single checksum-valid candidate. A number printed in a native text layer keeps its printed digits.
- On appeals and mandates, side-by-side role headings and a consistent gutter can delimit separate party cards.
  A signer caption can supply a name when its column identifies the principal. Conflicting identities or
  an unlabelled signature can leave the signer missing.
- Grant extraction reads numbered and coordinated appointments, officers in representation clauses,
  and digital approval signatures. Where a name is inflected, rules use a compatible printed form
  or a unique case- and gender-compatible personal-name reading from Morfeusz2. Ambiguous readings
  retain the printed spelling. On single-page scans with a sole corporate grantor and no identified
  signer, a local RapidOCR pass can read a board title and a name in the same stamp column after
  the mandate. It shares the optional full-page OCR budget. A damaged or handwritten signature can still leave the signer missing.
  PDF signer names are extracted from embedded CMS certificates without validating trust or revocation.
- UZP confirmed that an unrelated document gets `{}`. Its JSON uses the input PDF’s stem. [Organizer clarification](https://github.com/00200200/HackNation2026-2/issues/57)
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs. We write a string.

### Generated layout evaluation

Run `uv run python -m evals.run --variants 60` to regenerate 240 individual PDFs and write
`evals/results/variants.json`. Each cycle of 60 visits every public synthetic case once.
A case contributes an appeal, a power of attorney, a completed transfer and one generated
look-alike. The six negative families are BZP and TED notices, KIO rulings, invoices,
payment requests and pro-forma invoices. All names and identifiers come from synthetic
case facts or the seeded generator. No external documents need to be downloaded.

The generator builds references from the facts it prints, including substituted references
in the transfer title and the presence or absence of a country prefix on each account.
It varies typography and spacing and distributes six profiles across cases. The scan profile
rasterizes pages at 150–300 dpi with rotation, blur, noise and JPEG compression. ReportLab is
a development dependency for writing searchable Polish PDFs and embedding the scanned pages.
The evaluator runs five cases per temporary directory and uses two CLI workers by default.
Use the keyless configuration for comparison with the committed baseline.

For each rule change run `make eval-variants` alongside the corpus development evaluations.
The gate compares the generated input/reference digest, pooled UZP micro F1 and fraction of
unrelated documents with an empty JSON object against the committed baseline. It writes the candidate report under
`.cache/` and exits unsuccessfully on a regression or incomplete outputs. The report includes
the historical strict score, per-field counts and F1, class F1, positive layout profiles ranked
by F1, and negative outcomes by family. Profiles use different synthetic cases in each cycle,
so the ranking also reflects differences in case difficulty. Hidden-set performance is unknown.

### Case-linked benchmark

Run `make eval-cases` to score 26 invented cases with the local jury CLI. Each case supplies a short or long appeal, a mandate with identified grantors and signers, a bank receipt, and a related out-of-scope document. Each set of four appears in a separate case folder in native and image-only form. The two folders share case facts, independently of their opaque filenames. Only the PDFs enter the extractor.

```sh
make eval-cases CASE_ARGS="--split development"
make eval-cases CASE_ARGS="--split reserved"
make eval-cases CASE_ARGS="--seed 104 --cases 13 --generate-to .cache/case-inspection"
```

The default report is `.cache/case-benchmark.json`. Generation alone requires a new directory and writes `input/`, `gold/` and `manifest.json`. The manifest gives the reference path, paired PDF paths, case, split, family, scan settings, section bounds and printed field boxes. Page indices start at zero. Boxes are in native PDF points from the top left. To locate them on a scan, rotate their corners about the page center by the recorded counterclockwise angle and scale by DPI/72.

The development split uses the early modular appeal, six early mandates and seven early receipt layouts. The reserved split uses independently phrased long appeals, company/consortium/sole-trader mandates, the late bank table and the five organizer scan receipt layouts. CCITT Group 4 is reserved for that split. Both splits also contain JPEG scans. A 13-case cycle covers every family. Larger prefixes repeat layouts with new parties, dates and payment facts.

The report gives UZP and strict F1, literal JSON matches, routing and negative rejection by family, class and rendering, plus field counts within each family. Its 95% intervals resample complete cases 1,000 times and are omitted for single-case slices. Family frequencies in the jury set are unknown. The synthetic scores describe these authored layouts. Scans retain the page geometry of their native counterparts. Interior pages in the long appeal are more lightly typeset than those in the inspected organizer files.

On the 26-case panel, keyless main `fa9937e` scored **0.7191 UZP F1** (case-bootstrap 95% interval 0.6780–0.7570) and **0.6617 strict F1**. It routed 188/208 PDFs, returned 85 exact JSONs and rejected all 52 negatives. Extraction took 485 seconds with two workers on the shared development Mac.

| Main on the generated cases | PDFs | UZP F1 | Strict F1 | Exact |
|---|---:|---:|---:|---:|
| Appeals | 52 | 0.7285 | 0.6377 | 0 |
| Mandates | 52 | 0.6667 | 0.6763 | 4 |
| Transfers | 52 | 0.7557 | 0.7460 | 29 |
| Native, all classes | 104 | 0.6086 | 0.5339 | 44 |
| Scans, all classes | 104 | 0.8133 | 0.7865 | 41 |

Four receipt layouts are the first routing targets. The early bank letter, transaction history, operation details and order details each missed all four PDFs (two cases in both renditions). The sole-trader mandate routed 8/8 but scored 0.2069 UZP F1, with missed principal names and identifiers. Most families have few independent cases. The scorecard includes every family, codec/DPI combination, sample count and field result. [Benchmark measurements](../../evals/results/case-benchmark.json)

The transfer update routed all four development bank letters, with 0.9767 UZP and 0.9167 strict field F1. After integrating main `cf67694`, development UZP F1 rose from 0.9603 to 0.9729. The frozen rules still missed all four PDFs in each reserved history, operation-detail and order-detail family. Reserved UZP F1 was 0.7923, and all 52 negatives across the two splits remained empty. [Transfer results](../../evals/results/case-transfers.json)

A routing-only follow-up recognized two of four PDFs in each reserved transaction-history, operation-detail and order-detail family. These six receipts raised reserved UZP F1 from 0.7923 to 0.8159 and strict F1 from 0.7705 to 0.7867. None of the six had every field correct. The remaining families, including all 24 negatives, kept their scores. Development remained at 0.9729 UZP and 0.9667 strict. This was a second blind evaluation after the first candidate disclosed aggregate misses. [Paired routing results](../../evals/results/case-transfer-routing.json)

On the same main revision, #69’s 240 compact-form PDFs scored 0.9125 UZP and 0.8743 strict, with 60/60 negatives rejected. The replay matched #69’s published PDF/reference digest and five-case batching. The two panels differ in both facts and layouts.
