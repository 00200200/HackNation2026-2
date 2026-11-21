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
   primary page and each English verification crop has one second. Optional OCR calls also share a
   27-second deadline measured from the start of each PDF. When it expires, extraction continues with the
   available readings. Every page required for the first reading still gets its full recognition timeout. RapidOCR runs in a reusable
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

The three organizer class definitions supply the field descriptions, types and grounding rules for the model profiles. For a new class in a custom directory, its own TOML selects the routing cues and engine order.

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

The primary small-model candidate is Mistral’s open-weight `ministral-3b-2512` (3,849,090,048 total parameters). Both the language and vision weights count toward the 8B ceiling. The regional API supports native JSON Schema. Its documented processing geography includes EU and EFTA countries, so the jury deployment needs a narrower location commitment. [Provider comparison and sources](docs/small-model-providers.md)

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

On corpus 1 the model raised transfer F1 by 0.1407. On corpus 2 dev it raised transfer F1 by 0.0421 and appeal F1 by 0.0099. Both profiles matched all ten organizer appeals and powers of attorney, and nine of ten transfer confirmations. [Combined measurements](evals/results/round2-integration.json)

Exact counts compare the complete JSON, including list order. A/P/T denotes appeals, powers and transfers. Each private set includes 11 unrelated PDFs. Earlier appeal measurements are available separately. [Real appeal round](evals/results/appeal-real-development.json)

Micro F1 pools field matches across documents. Macro F1 averages the three class scores. The combined measurement file includes correct routes for every class and both profiles. The negatives column counts zero-byte outputs. Timing includes OCR and extraction on a shared host. [Earlier appeal development measurements](evals/results/appeal-scan-development.json) · [Earlier grant development measurements](evals/results/poa-development.json) · [Organizer scan report](evals/results/organizer-scans.json)

The earlier model-engine experiment compared two profiles on the 17-document corpus 1 holdout. [Model results](evals/results/llm-real-docs.json)

The scanned-transfer update was evaluated on a five-case organizer development half and a five-case holdout per class. Their combined transfer routing was 8/10, up from 2/10 on the integration baseline. Transfer field F1 was 0.8667 on the development half and 0.5833 on the holdout. [Scanned-transfer measurements](evals/results/scanned-transfers.json)

On all 30 organizer development scans, the rules routed 10/10 transfer confirmations. Nine matched every field literally (59/60 fields, transfer F1 0.9833). The outstanding title contains a severely degraded name and abbreviation. Across all three classes the run averaged 9.23 s/PDF on the shared Apple M1, with a maximum of 19.02 s. With the integrated power-of-attorney rules, micro F1 reached 0.6312 on corpus 1 all, 0.7160 on its dev subset and 0.6816 on corpus 2 dev. [Round 2 measurements](evals/results/scanned-transfers-round2.json)

On the shared 16 GB Apple M1, the integrated CLI processed 30 organizer scans in 36.12 s with four rules workers and 44.91 s with three Ministral workers. The 150-PDF batch took 57.54 s and 70.38 s respectively. It used two copies of the 30 scans and 90 training PDFs. [Combined measurements](evals/results/round2-integration.json)

The organizer allows 45 minutes for its 150-PDF batch, an average budget of 18 seconds per PDF.
In the earlier runtime-only experiment on a 16 GiB M1 MacBook Air, four workers processed 30 organizer scans in 37.15 seconds and a mix of
60 scans and 90 training PDFs in 74.42 seconds. Peak sampled process-tree RSS for the mix was
1,504 MiB. All 226 training and scan outputs matched sequential main (`5297660`) byte for byte.
[Batch timings and per-PDF profile](evals/results/batch-runtime.json)

The reported times cover these local datasets. OCR runs locally. Under the updated rules, a remote
OCR service would count toward model parameters. [Organizer evaluation rules](data/uzp/README.md)

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

Across the 91 PDFs, the 3B profile added 207 correct field matches, lost five and introduced 47 net false positives relative to the rules. It made 18 routing requests, 57 general extraction requests and 17 first-charge requests. In isolation, those 17 first-charge requests added four correct matches and removed four false positives. All 18 unrelated PDFs stayed empty without an API request. Three of the 30 organizer scans matched their full reference field sets. The secondary five-field fuzzy proxy scored .7325 for the 3B profile and .6006 for rules. [Per-field counts, per-class scores, timings and ablations](evals/results/small-model.json)

The larger `ministral-8b-2512` checkpoint has 8,918,026,240 parameters and exceeds the 8B submission limit. It serves as a development comparison. An on-device smoke test of the 3B Q4_K_M quantization with llama.cpp on a 16 GB Apple M1 recovered the date and amount of an invented transfer in 14.97 seconds. The development corpus scores in the table use the regional API. A separate local CPU check put the company into the natural-person name field on eight of ten invented grants. [Checkpoint and hosting evidence](docs/small-model-providers.md) · [Local grant review](https://github.com/00200200/HackNation2026-2/pull/26#issuecomment-7069029860)

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
In that rules-only experiment, the hybrid improved on explicit DPI by **0.0133**. Keyless extraction keeps the `tesseract-dpi` setting. The earlier DeepSeek Flash run combined Tesseract and RapidOCR on scans. The regional Ministral recipe above uses Tesseract alone. [OCR measurements](evals/results/ocr-engines.json) · [Flash configuration](evals/results/llm-real-docs.json)

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
  retain the printed spelling. On single-page scans with a sole corporate grantor and no identified
  signer, a local RapidOCR pass can read a board title and a name in the same stamp column after
  the mandate. It has a 35-second deadline. A damaged or handwritten signature can still leave the signer missing.
  PDF signer names are extracted from embedded CMS certificates without validating trust or revocation.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
