# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

Without endpoint credentials the jury configuration runs three rule-based extractors locally. Each class has a TOML file
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
file. A PDF that cannot be processed also gets an empty file, is reported on stderr, and makes
the run exit with status 1 after processing the remaining PDFs. A nonblank scan that yields fewer than two alphabetic words after page counters are removed
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
3. `kio2json/engines.py` sends the joined page text to the selected extractor. The three jury
   classes use `python` with a dotted path to the existing rule function. Native pages follow
   the integration baseline. The reader records which pages needed OCR so account repair,
   damaged e-mail handling and signature recovery can use the source of each field.
   A scanned attachment does not enable masked-account routing on a native receipt. `labelled_fields` extracts values by pattern. `llm`
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

For submission, choose an EU/EEA provider and inference region that serve an open-weight chat model.
Set all three variables in the process environment or in an ignored `.env` in the working directory.
Environment values take precedence. The application has no built-in endpoint or credential.

| Variable | What to supply |
|---|---|
| `KIO_LLM_BASE_URL` | The provider’s OpenAI-compatible Chat Completions base URL, including its version path if required |
| `KIO_LLM_MODEL` | The model ID from that provider’s catalogue |
| `KIO_LLM_API_KEY` | Its API credential |

Run `python -m kio2json --input input --output output` as usual. To compare profiles, set
`KIO_LLM_MODE` to `R` (rules), `L` (model), `RL` (rules fill first), `LR` (model fills first) or
`V` (model with format and checksum validation). With all three credentials present the bundled registry defaults to `LR` and `fallback`.
Both hybrid modes fill missing fields and empty lists. Within an existing list, a unique configured identity connects the two engines’ records.
`KIO_LLM_ROUTING` accepts `rules`, `fallback` (consult the model only after rule rejection) and
`model` (ask on every first page). Custom class directories retain their explicit TOML engine chains.

On scanned pages in the default Tesseract profile, the model receives the primary text and a
second reading by RapidOCR. Rules continue to use their primary page text and OCR provenance.
The 16,384-byte excerpt budget is shared between readings. Each citation is checked against a
single displayed source. Set `KIO_LLM_DUAL_OCR=false` to measure one reading. Native pages
do not trigger alternate OCR. Use a model context large enough for the excerpt, schema and up
to 1,800 generated tokens for a non-reasoning response. The class’s field definitions accompany the excerpt. Pydantic AI requests
a JSON object, validates it against the cited schema and permits one correction within a
180-second call deadline. `KIO_LLM_TIMEOUT_SECONDS` accepts 1–600 seconds. Endpoints
with native JSON schema constraints can use `KIO_LLM_OUTPUT=schema`; the default is `json`.
For another endpoint, set `KIO_LLM_ROUTE_REASONING` and `KIO_LLM_EXTRACT_REASONING` to a
`reasoning_effort` supported by the model. `KIO_LLM_ROUTE_MAX_TOKENS` and `KIO_LLM_EXTRACT_MAX_TOKENS`
set positive completion budgets, including reasoning. `KIO_LLM_ROUTE_TIMEOUT_SECONDS` and
`KIO_LLM_EXTRACT_TIMEOUT_SECONDS` override the shared deadline for their stage (1–600 seconds).
Use `KIO_LLM_TOKEN_PARAMETER` to select `max_tokens` or `max_completion_tokens` when the server
requires a specific field. Set `KIO_LLM_INLINE_SYSTEM_PROMPTS=false` for servers requiring system
messages at the beginning of the conversation. `KIO_LLM_THINKING_TYPE=enabled` sends
`thinking.type=enabled` and preserves the returned `reasoning_content` on a validation retry.
These optional settings apply to whichever model ID and base URL you supply.

The development measurements used the following explicit settings in addition to endpoint credentials.
A dash uses the application default.

| Setting | DeepSeek Pro | DeepSeek Flash |
|---|---|---|
| `KIO_LLM_TOKEN_PARAMETER` | `max_tokens` | `max_tokens` |
| `KIO_LLM_INLINE_SYSTEM_PROMPTS` | `false` | `false` |
| `KIO_LLM_THINKING_TYPE` | `enabled` | — |
| `KIO_LLM_ROUTE_REASONING` / `KIO_LLM_EXTRACT_REASONING` | `low` / `high` | `none` / `none` |
| `KIO_LLM_ROUTE_MAX_TOKENS` / `KIO_LLM_EXTRACT_MAX_TOKENS` | `24576` / `32768` | `32` / `1800` |
| `KIO_LLM_TIMEOUT_SECONDS` | `480` | `180` |

Transport retries are disabled. A failed document produces an empty
file and an error on stderr. The CLI finishes the batch with exit status 1.

Each accepted value needs a citation in the displayed text. If a model flattens line breaks,
the extractor looks for a unique span containing the same words and checks the original characters.
Dates, amounts and IDs must cover complete tokens. Selected organizer fields can derive a canonical
value from printed evidence, such as a TED reference in the alternate year/series format. A quote
from the wrong party can still support a value. PDF table cells and party boundaries remain open
work in [issue 10](https://github.com/00200200/HackNation2026-2/issues/10).

### EU providers for the submission

Both candidates offer OpenAI-compatible chat with structured JSON for the Apache-2.0
Mistral Small 3.2 24B model. Prices below are euros per million input/output tokens, checked on
21 November 2026. Hosted accuracy, latency and account approval time remain unmeasured.
[Model card](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506)

| Provider and region | Model ID | Price and access |
|---|---|---|
| Scaleway, Paris, France | `mistral-small-3.2-24b-instruct-2506` | €0.15 / €0.35 before tax, first 1M tokens free. Existing customers can generate an IAM API key immediately. New accounts need billing information. Standard quotas require card and identity verification. [Region](https://www.scaleway.com/en/docs/generative-apis/faq/) · [Structured output](https://www.scaleway.com/en/docs/generative-apis/how-to/use-structured-outputs/) · [Pricing](https://www.scaleway.com/en/pricing/model-as-a-service/) · [Onboarding](https://www.scaleway.com/en/generative-apis-signup/) |
| Berget AI, Stockholm, Sweden | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | €0.30 / €0.30, €5 starting credit on the trial. Register in the console and select **API Keys → Create New Key**. The provider advertises setup in minutes. [Region and endpoint](https://docs.berget.ai/quickstart) · [Model capabilities](https://docs.berget.ai/models/capabilities) · [Pricing](https://berget.ai/en/serverless-inference) · [Key setup](https://docs.berget.ai/integrations/cline-vscode) |

Scaleway also lists the measured Flash release as `deepseek-v4.1-flash-1017` at €0.60 input
(€0.12 cached) and €1.80 output per million tokens. Its `qwen3.8-27b` is €0.60/€3.30 and
`llama-3.3-70b-instruct` is €0.90/€0.90. Its API base URL is `https://api.scaleway.ai/v1`.
Berget uses `https://api.berget.ai/v1` and lists a Qwen 3.8 27B preview with JSON schema support.
Matching model releases can still differ in quantization and serving settings.
[Scaleway prices](https://www.scaleway.com/en/pricing/model-as-a-service/) ·
[Scaleway API](https://www.scaleway.com/en/docs/generative-apis/faq/) ·
[Berget capabilities](https://docs.berget.ai/models/capabilities)

### Measurements on real KIO documents

On the private dev split (22 PDFs in 14 cases), DeepSeek V4 Pro with model-first extraction and rule fallback (`LR`) scored **0.7236 field micro-F1**. The keyless rules profile scored **0.4356**. The keyed profile asks the model to classify a first page only when the rules reject it. This recovered all five positive documents the rule router missed, and all seven unrelated PDFs still produced empty files. The EU-hosted submission endpoint still needs its own evaluation. [Aggregate results](evals/results/llm-real-docs.json)

All five rows below use the same fallback router, including `R`, where the model can route but rules extract every field. Macro F1 gives equal weight to the three classes. All five modes classified 15/15 positives correctly and returned empty files for 7/7 negatives.

| Pro extraction mode | Micro F1 | Macro F1 | Appeal | Power of attorney | Transfer | Serial stage seconds/PDF |
|---|---:|---:|---:|---:|---:|---:|
| R | 0.4203 | 0.3228 | 0.4685 | 0.5000 | 0.0000 | 8.18 |
| L | 0.7114 | 0.6767 | 0.7277 | 0.6774 | 0.6250 | 69.91 |
| RL | 0.6734 | 0.6819 | 0.6667 | 0.7541 | 0.6250 | 69.91 |
| **LR** | **0.7236** | **0.7090** | 0.7277 | 0.7742 | 0.6250 | 69.91 |
| V | 0.7114 | 0.6767 | 0.7277 | 0.6774 | 0.6250 | 69.91 |

With `LR`, rule-only routing scored 0.6783 micro-F1 and found 10/15 positives. Asking Pro about every first page produced the same score and routes as fallback but required 22 classification calls instead of 12. On the same dev PDFs, DeepSeek Flash scored 0.6951 micro-F1 and 0.6302 macro-F1 with `LR` and fallback routing. Its class scores were 0.7225 for appeals, 0.7097 for powers of attorney and 0.4583 for transfers. Flash took 14.12 serial stage seconds per PDF. These timings sum the recorded OCR, routing and extraction calls and divide by 22. The comparison reuses identical calls across modes.


In a separate uncached test on two invented native-text PDFs, one worker took 2.56 s/PDF with Flash and 15.09 s/PDF with Pro. Two simultaneous document workers took 1.15 and 12.55 s/PDF respectively. Each PDF needed one route followed by one extraction. The class decision selects the extraction schema, so these calls run in sequence within each PDF. The fixture had no OCR cost.

The model reads up to three pages. Scanned pages receive a second OCR reading, and the two readings share a 16,384-byte input budget. The extractor can recover a line-wrapped citation when its words map to one source span. It checks typed values and canonical organizer codes against that evidence. Across the development iterations, Flash `L` with fallback routing improved from 0.5418 with the 8,192-byte single reading to 0.6870 with the final profile. Multiple changes contributed to this difference.

In a strict audit that paired repeated records within their parent, Pro `L` had 72 errors across 247 dev field comparisons. In 53 cases the raw response proposed the reference value and grounding replaced it with null. Fifteen quotes could not be recovered. Another 38 quotes matched the source but failed the check for the proposed value. The audit found one nonnull output against a null reference, three name or title convention differences and four incorrect or omitted values recognizable in the input. Eleven cases remained unresolved. This audit used the cached primary and secondary readings and could not establish an input-loss count beyond the first three pages.


**Local Qwen comparison.** On the 16 GB Apple M1 we served Unsloth’s Apache-2.0 GGUF of Qwen3-4B-Instruct-2507 (`Q4_K_M`, 2,497,281,120 bytes) using llama.cpp build `b12608`. From the directory containing the binary distribution and the model saved as `qwen.gguf`, run the following command. The measured model file has SHA-256 `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`. [Model files](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF) · [llama.cpp release](https://github.com/ggml-org/llama.cpp/releases/tag/b12608)

```sh
./llama-b12608/llama-server -m qwen.gguf --host 127.0.0.1 --port 18089 \
  -c 16384 -np 1 -ngl 99 --cache-type-k q8_0 --cache-type-v q8_0 --alias qwen-local
```

The local base URL is `http://127.0.0.1:18089/v1` and the model ID is `qwen-local`. The native-schema run used `KIO_LLM_OUTPUT=schema` and `KIO_LLM_TIMEOUT_SECONDS=360`. Supply a nonempty placeholder for `KIO_LLM_API_KEY` when running this local server without authentication.

Within the 30-minute local budget, Qwen completed 11 of 22 dev PDFs (nine positive, two unrelated). On those same PDFs, Qwen scored 0.4323 micro-F1, Flash 0.7266 and Pro 0.7682. The respective gaps to Flash and Pro were 0.2943 and 0.3359. The completed Qwen prefix averaged 114.18 wall seconds/PDF using cached OCR. The remaining 11 have no local score.

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

A separate native-text differential test compares the class and serialized fields of 175 invented PDFs
with a snapshot from integration base `3210643`. It includes 135 review cases and 40 additional
documents. [Fixtures and regeneration command](tests/snapshots/README.md)

Forced OCR on all 196 training PDFs (307 rendered pages) gave strict field F1 **0.900**
with automatic source resolution and **0.884** with explicit 300 dpi. The comparison used the rules recorded in the measurement file. To run the
current rules, select `KIO_OCR_ENGINE=tesseract-dpi` and run
`uv run python -m evals.field_report --force-ocr --errors`. [OCR measurements](evals/results/ocr-engines.json)

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
The real-dev result is in [the corpus report](evals/results/corpus-latest.json). The
`provenance_check` entry records the paired native-text and forced-OCR checks on the same
rules. [OCR results](evals/results/ocr-engines.json)

## Known limits

- The rules follow the two layout families in the training data. `input/case1` holds the
  organizer's one real, redacted, scanned appeal, which has a different layout. For that file
  the extractor finds the class, filing date, place, procurement reference, BZP number and title.
  The appellant name contains OCR noise. The contracting-authority list is empty and the challenged
  action is missing. The organizer supplies no reference JSON for this file.
- OCR can still lose accented letters, split a notice number or reorder columns. Scans with a
  noisy but nonempty text layer follow the native-text path. A Polish account containing OCR
  glyphs is repaired only if a unique candidate passes the IBAN mod-97 check. A fully printed
  digit string is retained as read, including when the printed checksum is invalid. Ambiguous
  signatures and e-mail addresses can remain missing.
- On a scanned receipt, the single-account route needs a confirmation heading, a transaction amount and date,
  and two explicitly labelled accounts. One must show a mask (asterisks, Xs or a dash) and the other a checksum-valid number.
  The classifier passes the labelled account evidence to the extractor. A repeated number elsewhere in the text cannot fill a masked role. Unlabelled or conflicting roles can leave account fields empty.
- OCR can recover a signer from a signature caption, a signature line in the grantor’s block, or a closing name with a representation title directly beneath the grant. Ambiguous roles can leave a signer out. Attorney names retain the grammatical case used in the document.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
