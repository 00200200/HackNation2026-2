# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

The jury configuration runs three rule-based extractors locally. Each class has a TOML file
that selects its routing rules, output fields and extraction engines. New classes can use
label patterns or an optional language model.

## Run

You need Python 3.13+. Scanned PDFs also need the Tesseract binary with Polish data on `PATH`
(`brew install tesseract tesseract-lang`, `apt install tesseract-ocr tesseract-ocr-pol`, or the
UB Mannheim installer on Windows). Without Tesseract or its Polish data, PDFs that have a text
layer with readable content still work. The CLI reports which scans failed and why.

```
pip install -r requirements.txt
python -m kio2json                                   # reads ./input, writes ./output
python -m kio2json --input some/input --output some/output
```

Each PDF gets a JSON at the same relative path and file stem. Appeals, powers of attorney and
bank-transfer confirmations get the organizer's structure. Any other document gets an empty
file. A PDF that cannot be processed also gets an empty file, is reported on stderr, and makes
the run exit with status 1 after processing the remaining PDFs. This includes required OCR that fails or times out.

## How it works

1. `kio2json/pdf_text.py` reads the first three pages with pdfplumber. Pages with no text or
   only page numbers go through Polish Tesseract at 300 dpi.
2. The CLI loads `config/classes/*.toml` once per batch. `kio2json/class_config.py` matches the
   page text against enabled definitions in ascending `priority`, then class ID order. The first
   match wins. For example, a transfer requires two distinct accounts and evidence of payment
   confirmation or execution. Invoices that request payment get an empty file.
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
   the search to the first N available pages (default 1). For a count of distinct matches,
   see `[routing.evidence]` and `minimum` in `bank_transfer.toml`.
3. Define one field per output key. Scalars support `string`, `integer`, `number` and `boolean`.
   Object fields have a `fields` table, and list fields declare an `items` schema, which can
   itself contain lists. All fields carry an `instruction`. Fields are nullable by default.
   A labelled field's `pattern` captures the value in one group. On a list, each capture is
   one row, and its child patterns search within that row. Available normalizers are
   `iso_date`, `money`, `account_number`, `krs`, `nip`, `regon` and `pesel`.
4. Run the CLI with a PDF containing the new heading and labels. For the example above,
   a document with lines `Receipt` and `Reference: HX-7` yields `{"reference": "HX-7"}`.
   Test a near miss such as a draft. Changes take effect on the next invocation.
   Treat class files as trusted application configuration since `python` loads a callable.

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

The model supplies a verbatim quote with each scalar value. The engine checks each quote
against the supplied text, then writes only the public fields. Missing information or an
unmatched quote yields null, even for a normally mandatory scalar. A matching quotation
can still refer to the wrong party. Pydantic AI allows one structured-output correction within
a 60-second run timeout. Transport retries are disabled. An endpoint or validation failure is
reported for that PDF on stderr and the batch exits with status 1. Offline model tests cover
these extraction rules. Accuracy and latency on a live model have yet to be measured.

## Measure

```
uv run python -m evals.run --quick            # dev subset, before a push
uv run python -m evals.run                    # all 60 training cases and the negatives
uv run python -m evals.field_report --errors  # which fields fail, with list items paired inside their parent
uv run python -m evals.field_report --force-ocr --errors   # ignore the text layer: what OCR costs
```

`evals.run` is the team's F1 harness and the source of every number below; its definition of
F1 is in `evals/metrics.py`. The organizers have not published theirs.

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

## Known limits

- The rules follow the two layout families in the training data. `input/case1` holds the
  organizer's one real, redacted, scanned appeal, which has a different layout. For that file
  the baseline finds the class, filing date, place, BZP number and title. OCR puts text from the
  contracting authority in the appellant block and leaves the challenged action empty. The
  organizer supplies no reference JSON for this file.
- Through OCR the rules lose fields. Tesseract misreads characters inside identifiers (`7` as
  `/` in account numbers, `@` in e-mail addresses, `sp. z o.o.` as `sp. z 0.0.`) and drops the
  dotted signature lines that the power-of-attorney rules use to find signers.
  `evals.field_report --force-ocr` shows the affected fields.
- Transfer confirmations with a masked account can be rejected. Attorney names retain the grammatical
  case used in the document.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
