# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

The jury configuration runs three rule-based extractors locally. Each class has a TOML file
that selects its routing rules, output fields and extraction engines. New classes can use
label patterns or an optional language model.

## Run

From the repository root, use 64-bit CPython 3.13 and a virtual environment. pip installs the
Tesseract native libraries from PyPI. The local language-data wheel downloads the Polish and
English fast models (8.88 MB combined) from a pinned revision on `raw.githubusercontent.com`
and verifies both SHA-256 hashes. Once installed, the CLI and viewer process PDFs offline.
[Platform wheels](https://pypi.org/project/tesserocr/2.13.0/#files)

If the model host is unreachable, download both files on a connected machine and copy them into
one directory. Before rerunning the install command below, set
`export KIO_TESSDATA_SOURCE=/absolute/path/to/models` in a POSIX shell or
`$env:KIO_TESSDATA_SOURCE = 'C:\models'` in PowerShell. Keep the original filenames.
The installer verifies the same hashes for locally supplied files.
[pol.traineddata](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/pol.traineddata) · [eng.traineddata](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata)

```
pip install -r requirements.txt
python -m kio2json                                   # reads ./input, writes ./output
python -m kio2json --input some/input --output some/output
```

The default setting is `KIO_OCR_ENGINE=tesseract`. To use RapidOCR v6, install the optional
CPU runtime and set `KIO_OCR_ENGINE=rapidocr` in the environment before invoking the same CLI.
Use `export KIO_OCR_ENGINE=rapidocr` in a POSIX shell or `$env:KIO_OCR_ENGINE = "rapidocr"`
in PowerShell. The RapidOCR wheel includes its recognition and detection models, so the first
run can also be offline.

```
python -m pip install "rapidocr==3.10.0" "onnxruntime==1.32.0"
```

With uv, `uv run --group rapidocr python -m kio2json` uses the pinned optional dependencies.

Each PDF gets a JSON at the same relative path and file stem. Appeals, powers of attorney and
bank-transfer confirmations get the organizer's structure. Any other document gets an empty
file. A PDF that cannot be processed also gets an empty file, is reported on stderr, and makes
the run exit with status 1 after processing the remaining PDFs. An image-only document with no readable text on any inspected page reports
`no readable text after OCR`. A blank separator beside a readable page is accepted.

To open the Polish document viewer, run `python -m kio2json.gui`. It opens a browser on
`127.0.0.1:8000`. Select PDFs and name the case, or enter a folder containing cases. Click
**Analizuj dokumenty**, choose a document and compare its pages with the JSON. **Pobierz wyniki (.zip)**
downloads one JSON per PDF under its case folder. Failed documents show the reason and get an
empty file. The viewer keeps temporary copies for the current session. The default configuration
works offline. The pipeline does not report which pages used OCR.

| Start from the repository | Windows | Linux or macOS |
|---|---|---|
| Run the CLI on `input/` and write to `output/` | `.\start.bat` | `./start.sh` |
| Open the viewer | `.\start.bat gui` | `./start.sh gui` |

[Transfer confirmation in the viewer](docs/gui/transfer.png) · [Appeal in the viewer](docs/gui/appeal.png)

## How it works

1. `kio2json/pdf_text.py` reads the first three pages with pdfplumber. Pages with no text or
   only page numbers go through the selected OCR engine at 300 dpi. When Tesseract reads
   a possible e-mail address with a missing `@`, an English single-word pass rereads that crop. The extractor accepts the separator
   only when the rest of both readings agrees. Call `read_pages(path, word_boxes=boxes)` with
   an empty list to collect raw words and their rectangles alongside the page strings. Coordinates
   are PDF points from the top left, with one-based page numbers.
2. The CLI loads `config/classes/*.toml` once per batch. `kio2json/class_config.py` matches the
   page text against enabled definitions in ascending `priority`, then class ID order. The first
   match wins. The three organizer classes share the content classifier in `kio2json/classify.py`.
   It reads headings in document order. A transfer normally needs two distinct accounts, a confirmation
   heading or execution status, and a transaction amount or date. Rejected payments and payment
   requests get an empty file.
3. `kio2json/engines.py` sends the joined page text to the selected extractor. The three jury
   classes use `python` with a dotted path to the existing rule function. Each function retains
   its field order and normalization. `labelled_fields` extracts values by pattern. `llm`
   generates a Pydantic AI output model from the same field definitions.

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

Choose an OpenAI-compatible chat endpoint serving your open-weight model with structured
tool output. Set these variables in the process environment or in an ignored `.env` in the
working directory. Existing environment values take precedence.

| Variable | Value |
|---|---|
| `KIO_LLM_BASE_URL` | API base URL, including the endpoint's version path, e.g. `http://localhost:8000/v1` |
| `KIO_LLM_MODEL` | Model identifier advertised by that endpoint |
| `KIO_LLM_API_KEY` | Endpoint credential |

Set `engines = ["llm"]` for model-only extraction. Remove the `extractor` entry when removing
the Python engine. Use `engines = ["python", "llm"]` to keep values found by the rules and
consult the model for null fields. A fallback preserves existing arrays, including empty ones.
To fill missing fields within existing records, set `match_by` on the list to a unique scalar
field, such as `data.nazwa` in `power_of_attorney.toml`. Ambiguous identities keep their original
records. The built-in jury classes use only `python` and require no endpoint settings.

The model supplies a verbatim quote for each scalar. The engine checks that the page contains
the quote and that the quote supports the value. Copied text must appear in the quote after
normalization. Full references and email addresses keep their internal punctuation. For dates,
amounts, accounts and registry IDs, the quote must cover the complete printed value, including
any sign. Grouped amounts such as `9 876,54 PLN` and amounts with attached currency such as
`EUR87,23` are supported. An incomplete value or an overlong account yields null, including for
normally mandatory scalars. A correctly quoted value from the wrong party’s block can still pass.

Pydantic AI allows one structured-output correction within a 60-second run timeout. Transport
retries are disabled. An endpoint failure is reported on stderr with the PDF path, failure type
and HTTP status when available. The CLI continues the batch and exits with status 1.
Offline model tests cover these rules. Accuracy and latency on a live model have yet to be measured.

## Measure

```
uv run python -m evals.run --quick            # dev subset, before a push
uv run python -m evals.run                    # all 60 training cases and the negatives
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
Inspect field errors on dev. Use aggregate scores to evaluate test.

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

On the merged extraction rules, the default engine scored **0.897** strict field F1 on the
196 documents rendered as 307 images. RapidOCR v6 transcripts scored **0.828** with the same rules.
Run `uv run python -m evals.field_report --force-ocr --errors` to repeat the default OCR run.

On 17 real development scans (34 pages), Tesseract scored **0.331** and RapidOCR v6 scored
**0.419**. The runs took 2.78 and 15.45 CPU seconds per page respectively on an Apple M1.
Across all 20 development documents with natural text-layer routing, corpus micro-F1 was
0.3864 with Tesseract and 0.4588 with RapidOCR.

## Known limits

- The rules follow the two layout families in the training data. `input/case1` holds the
  organizer's one real, redacted, scanned appeal, which has a different layout. For that file
  the extractor finds the class, filing date, place, procurement reference, BZP number and title.
  Both party lists and the challenged action are empty. The organizer supplies no reference JSON
  for this file.
- OCR can still lose accented letters, split a notice number or reorder columns. Scans with a
  noisy but nonempty text layer follow the native-text path. A Polish account containing OCR
  glyphs is repaired only if a unique candidate passes the IBAN mod-97 check. A fully printed
  digit string is retained as read, including when the printed checksum is invalid. Ambiguous
  signatures and e-mail addresses can remain missing.
- A receipt with one masked account must have a confirmation heading, a transaction amount and date,
  and two explicitly labelled accounts. One must be fully masked by asterisks and the other checksum-valid.
  Unlabelled or conflicting roles can leave account fields empty.
- A signer needs a signature heading, a signature line in the grantor’s block, or a closing name with a representation title directly beneath the grant. Ambiguous roles can leave a signer out. Attorney names retain the grammatical case used in the document.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
