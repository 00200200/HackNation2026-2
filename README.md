# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

Without endpoint credentials the jury configuration runs three rule-based extractors locally. Each class has a TOML file
that selects its routing rules, output fields and extraction engines. New classes can use
label patterns or an optional language model.

## Run

From the repository root, create a virtual environment with 64-bit CPython 3.13.

| Shell | Create | Activate |
|---|---|---|
| Windows PowerShell | `py -3.13 -m venv .venv` | `.\.venv\Scripts\Activate.ps1` |
| macOS or Linux | `python3.13 -m venv .venv` | `. .venv/bin/activate` |

Use the activated shell for the install and run commands below. pip installs the
Tesseract native libraries from PyPI. The local language-data wheel downloads the Polish and
English fast models (8.88 MB combined) from a pinned revision on `raw.githubusercontent.com`
and verifies both SHA-256 hashes. Once installed, the rules-only CLI and viewer process PDFs offline.
[Platform wheels](https://pypi.org/project/tesserocr/2.13.0/#files)

If the Tesseract data host is unreachable, download both language files on a connected machine and copy them into
one directory. Before rerunning the install command below, set
`export KIO_TESSDATA_SOURCE=/absolute/path/to/models` in a POSIX shell or
`$env:KIO_TESSDATA_SOURCE = 'C:\models'` in PowerShell. Keep the original filenames.
The installer verifies the same hashes for locally supplied files.
[pol.traineddata](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/pol.traineddata) · [eng.traineddata](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata)

```
python -m pip install -r requirements.txt
python -m kio2json                                   # reads ./input, writes ./output
python -m kio2json --input some/input --output some/output
```

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
bank-transfer confirmations get the organizer's structure. Any other document gets an empty
file. In the default keyless profile, an unreadable PDF receives an empty file and a diagnostic on stderr. The CLI processes the remaining PDFs and exits with status 1. The keyed organizer profile uses the document recovery described below. A nonblank scan that yields fewer than two alphabetic words after page counters are removed
reports `no readable text after OCR`. Blank pages may stand alone or appear beside a readable page.

To open the Polish document viewer, run `python -m kio2json.gui`. It opens a browser on
`127.0.0.1:8000`. Select PDFs and name the case, or enter a folder containing cases. Click
**Analizuj dokumenty**, choose a document and compare its pages with the JSON. **Pobierz wyniki (.zip)**
downloads one JSON per PDF under its case folder. Failed documents show the reason and get an
empty file. The viewer keeps temporary copies for the current session. The default configuration
works offline. Page provenance is used internally and the output follows the organizer’s JSON schema.

| Start from the repository | Windows | Linux or macOS |
|---|---|---|
| Run the CLI on `input/` and write to `output/` | `.\start.bat` | `./start.sh` |
| Open the viewer | `.\start.bat gui` | `./start.sh gui` |

[Transfer confirmation in the viewer](docs/gui/transfer.png) · [Appeal in the viewer](docs/gui/appeal.png)

## How it works

1. `kio2json/pdf_text.py` reads the first three pages with pdfplumber for extraction.
   Pages with no usable text, including scans with a selectable page counter, go through OCR at 300 dpi.
   If those pages require OCR and appear unreadable, the reader checks later pages for readable text
   before reporting a document error. When Tesseract reads
   a possible e-mail address with a missing `@`, an English single-word pass rereads that crop. The extractor accepts the separator
   only when the rest of both readings agrees. Call `read_pages(path, word_boxes=boxes)` with
   an empty list to collect raw words and their rectangles alongside the page strings. Coordinates
   are PDF points from the top left, with one-based page numbers. Polish Tesseract has 60 seconds per
   recognition call and each English verification crop has one second. RapidOCR runs in a reusable
   child process. A 60-second page deadline kills a stalled worker so processing can continue.
2. The CLI loads `config/classes/*.toml` once per batch. `kio2json/class_config.py` matches the
   page text against enabled definitions in ascending `priority`, then class ID order. The first
   match wins. The three organizer classes share the content classifier in `kio2json/classify.py`.
   It reads headings in document order. A transfer normally needs two distinct accounts, a confirmation
   heading or execution status, and a transaction amount or date. Rejected payments and payment
   requests get an empty file.
3. The rule extractors recover party blocks and receipt fields from columns. Each page keeps its source,
   so a scanned attachment cannot enable OCR repairs on a native receipt. Configuring an endpoint enables
   first-page model routing after the rules reject a document. The model extracts from the original reading
   and, on scans, an independent OCR reading. Each accepted value needs a supporting span. The class rules
   fill gaps using the reconstructed layout. The CLI and viewer share this pipeline.

[Pipeline diagram (PDF)](docs/pipeline/pipeline.pdf)

## Enable the fourth class

The optional `participation.toml` recognizes a form headed **Karta uczestnika**. It extracts the
participant, filing date and reference. To try it, copy the directory and set `enabled = true`
in the copy of `participation.toml`. Point the CLI at that directory for one run.

```sh
cp -R config/classes /tmp/kio-classes
# Edit /tmp/kio-classes/participation.toml, then run:
KIO_CLASSES_DIR=/tmp/kio-classes python -m kio2json --input input --output output
```

With the default directory, that form gets an empty file. The end-to-end test writes an invented
PDF, runs the CLI in both configurations and checks the output, including its ISO date.

```sh
uv run pytest -q tests/test_class_config.py -k fourth
```

## Add a class

The three organizer class definitions supply the field descriptions, types and grounding rules for a configured model. For a new class in a custom directory, its own TOML selects the routing cues and engine order.

1. Create one TOML file in your class directory and choose a unique English `id`. This example
   adds a receipt with one reference field.

   ```toml
   id = "receipt"
   engines = ["labelled_fields"]

   [routing]
   required = ['^Receipt$', '^Reference:']
   forbidden = ['^Draft\b']

   [fields.reference]
   type = "string"
   instruction = "Reference printed on the receipt."
   pattern = '^Reference:[ \t]*(.+)$'
   ```

2. Set the routing cues. Patterns are case-insensitive and support line anchors. Every
   `required` pattern must match and any `forbidden` match rejects the class. Each optional
   `headings` pattern must match a whole line with whitespace removed. `routing.pages` limits
   the search to the first N available pages (default 1). To require distinct references, for
   example, add `[routing.evidence]` with `pattern = 'Reference: (\w+)'` and `minimum = 2`.
   Classes with a Python router can set `classifier = "kio2json.classify.classify"` in
   `[routing]` in place of the cues. The function receives the page texts and returns a class ID
   or `None`. Each organizer class uses this setting.
3. Define one field per output key. Scalars support `string`, `integer`, `number` and `boolean`.
   Object fields have a `fields` table, and list fields declare an `items` schema, which can
   itself contain lists. All fields carry an `instruction`. Fields are nullable by default.
   A labelled field's `pattern` captures the value in one group. On a list, each capture is
   one row, and its child patterns search within that row. Available normalizers are
   `iso_date`, `money`, `account_number`, `krs`, `nip`, `regon` and `pesel`.
4. Run the CLI with a PDF containing the new heading and labels. For the example above,
   a document with lines `Receipt` and `Reference: HX-7` yields `{"reference": "HX-7"}`.
   Test a near miss such as a draft. Changes take effect on the next invocation.
   Treat class files as trusted application configuration. Extractor and classifier paths load Python callables.

## Use a model endpoint

To enable a model for the three bundled classes, supply these variables in the process environment or in
an ignored `.env` in the working directory. Environment values take precedence. Choose an OpenAI-compatible
Chat Completions endpoint that can return structured JSON. For submission, the provider and inference
region must meet the organizer’s EU/EEA requirements. Model selection is pending.

| Variable | Value |
|---|---|
| `KIO_LLM_BASE_URL` | Your provider’s API base URL, including its version path if required |
| `KIO_LLM_MODEL` | Model ID served at that endpoint |
| `KIO_LLM_API_KEY` | Credential accepted by the endpoint |

Run the same CLI or viewer command. With all three variables set, the bundled classes use model-first
extraction with rule fallback (`KIO_LLM_MODE=LR`). The router asks the model about the first page after
the local rules reject the document (`KIO_LLM_ROUTING=fallback`). On a scan, RapidOCR provides a second
reading alongside Tesseract. The two readings share a 16,384-byte budget. A citation must match one
displayed source. Dates, amounts and identifiers must cover complete printed values.

For compatible servers, `KIO_LLM_OUTPUT=schema` requests native JSON schema support. The default is
`json`. `KIO_LLM_TIMEOUT_SECONDS` sets the request deadline (1–600 seconds, default 180). The engine
allows one structured-output correction. On a model or secondary OCR error, the keyed organizer
profile retries the document with local rules, reports recovery, and continues the batch. An unreadable
document yields an empty file. Custom class directories use the engine chains in their own TOML files.

## Measure

```
uv run python -m evals.run --quick            # dev subset, before a push
uv run python -m evals.run                    # all 60 synthetic training cases and the negatives
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
positive reference needs fields for its expected class. The negative-output target requires zero-byte predictions.
For a case-level split, put `{"dev": [...], "test": [...]}` in `SPLIT.json` at the corpus root. Each list
contains case folder names. The default `--split all` scores the whole corpus, including corpora without a split.
Inspect field errors on dev. Use aggregate scores to evaluate test. The organizer scan mode validates the committed PDF/reference pairs in `data/uzp/dane/skany` and writes `evals/results/organizer-scans.json`. The synthetic training and scan scores have separate result files.

`evals.run` reports pooled micro F1 and macro F1 by document, class and field path.
The working definitions are in `evals/metrics.py`. The organizer's formula is UNCONFIRMED.

## Results on the training data (synthetic)

Source: `evals/results/latest.json` (full mode; the file records the commit it was run on).

| Metric | Value |
|---|---|
| `micro_f1`, all 60 cases and the negatives | 1.000 |
| `micro_f1`, cases 51-60 | 1.000 |
| `classification_accuracy` | 1.000 |
| `negatives_empty` | 1.000 |

Read these as a regression check. The rules were written by looking at these same synthetic
documents, cases 51-60 included, so no case here is unseen and the 51-60 figure is no estimate
of how the rules generalize. The hidden test set holds real cases, and this is not its score.

A separate native-text differential test compares the class and serialized fields of 175 invented PDFs
with a snapshot from integration base `3210643`. It includes 135 review cases and 40 additional
documents. Two suites compare 285 invented grant, receipt and routing PDFs and 205 appeal and routing inputs with integration base `e051dfa`. Each expected change records the original value, replacement and reason. [Fixtures and regeneration commands](tests/snapshots/README.md)

Forced OCR on all 196 training PDFs (307 rendered pages) gave strict field F1 **0.900**
with automatic source resolution and **0.884** with explicit 300 dpi. The comparison used the rules recorded in the measurement file. To run the
current rules, select `KIO_OCR_ENGINE=tesseract-dpi` and run
`uv run python -m evals.field_report --force-ocr --errors`. [OCR measurements](evals/results/ocr-engines.json)

## Rules on real documents and organizer scans

These runs used local rules with the three endpoint variables unset. The two local datasets contain real documents and use whole-case splits. Corpus 1 contributes all 39 development PDFs, including its previously evaluated split. Corpus 2 contributes 39 development PDFs from 14 cases. Its 60 test PDFs are reserved for the merged system. The organizer supplied a separate set of 30 labelled scans, ten per target class. The scan command stages the committed PDF/reference pairs as one batch with neutral filenames. [Organizer scan set at the measured revision](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/0b360a9da4b482a6a280696df6714404e0953505/dane/skany)

| Dataset | PDFs | Micro F1 | Macro F1 by class | Appeal | Power of attorney | Transfer | Correct routes (appeal / power / transfer) | Empty negatives | Wall s/PDF |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| Local corpus 1, all | 39 | 0.7104 | 0.6950 | 0.7046 | 0.9189 | 0.4615 | 12/13 / 6/6 / 4/9 | 11/11 | 8.45 |
| Local corpus 2, dev | 39 | 0.7713 | 0.6375 | 0.8148 | 0.9462 | 0.1515 | 13/13 / 5/5 / 1/10 | 11/11 | 3.89 |
| Organizer scans | 30 | 0.9203 | 0.7315 | 1.0000 | 1.0000 | 0.1944 | 10/10 / 10/10 / 2/10 | n/a | 16.44 |

Micro F1 pools field matches across documents. Macro F1 averages the three class scores. The routing columns count correctly classified documents in each target class. The negatives column counts zero-byte outputs. Timing includes OCR and extraction on a shared host. [Merged development measurements](evals/results/appeal-scan-development.json) · [Earlier grant development measurements](evals/results/poa-development.json) · [Organizer scan report](evals/results/organizer-scans.json)

The earlier model-engine experiment compared two profiles on the 17-document corpus 1 holdout. [Model results](evals/results/llm-real-docs.json)

The organizer allows 45 minutes for its 150-PDF batch, an average budget of 18 seconds per PDF.
The reported times cover these local datasets. OCR runs locally. Under the updated rules, a remote
OCR service would count toward model parameters. [Organizer evaluation rules](data/uzp/README.md)

## OCR on real development documents

All five runs used the same frozen extraction rules and 20 real development PDFs. Native text was
used where available. Tesseract's explicit-DPI mode gained **0.0301** dev micro-F1 over automatic DPI.
In that rules-only experiment, the hybrid improved on explicit DPI by **0.0133**. Keyless extraction keeps the `tesseract-dpi` setting. The separately measured keyed profile uses both readings on scanned pages. [Scores and measurement method](evals/results/ocr-engines.json)

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
rules. [OCR results](evals/results/ocr-engines.json)

## Known limits

- On corpus 2 dev, rules routed only one of ten transfers. A missing route makes every reference field in that document a miss.
- A model can cite the wrong party’s valid source text. The integration measurements above cover the rules-only profile.

- Appeal extraction reads the first three pages. A signature or dated notice later in the PDF can be missed.
  Scanned appeal covers use printed word positions to reconnect party labels with their address blocks.
  The extractor checks ambiguous contact details and reference prefixes against cropped words.
  Explicit party labels and filing clauses can identify the parties. An unlabelled list, an ambiguous
  column alignment or an inflected company name can still leave a party missing. A plain title can include
  lowercase continuation rows before the next labelled field. A challenge date needs a link to the act
  or its notification. Separate filing, invoice and statutory dates can appear on the same page.
- Receipt routing uses evidence that a payment was executed, its amount or date, and the participating
  accounts. A booking table or bank letter needs both an amount and a date. The extractor binds payer
  and payee separately from fee and refund accounts. Explicit operation or execution dates and transaction IDs take
  precedence over posting dates and daily sequence numbers. An unclear role or conflicting value can
  leave a field empty.
- First-page word positions can recover fields whose labels and values occupy different rows or columns.
  OCR can still split a title or change an amount. For an unrouted scan with confirmation and transaction
  evidence, the default engine can reread the first page at automatic resolution. Conflicting dates,
  amounts or transaction IDs prevent that retry from supplying a result.
- A partially masked account can identify a payment role when its field is explicit, the other account
  passes the Polish IBAN checksum, and the confirmation supplies the amount and date. The masked number
  is null. OCR also supports fully masked fields. Digit repairs apply only to OCR text and require a
  single checksum-valid candidate. A number printed in a native text layer keeps its printed digits.
- Grant extraction reads numbered and coordinated appointments, officers in representation clauses,
  and digital approval signatures. Where a name is inflected, rules use a compatible printed form
  or a unique case- and gender-compatible personal-name reading from Morfeusz2. Ambiguous readings
  retain the printed spelling. A damaged or handwritten signature can still leave the signer missing.
  PDF signer names are extracted from embedded CMS certificates without validating trust or revocation.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
