# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

The extraction path is a rule-based baseline. It uses no language model yet.

## Run

From the repository root, use 64-bit CPython 3.13 and a virtual environment. pip installs
the Tesseract library from the tesserocr wheel. While building the local language-data wheel,
pip downloads the Polish and English fast models (8.9 MB combined) from a pinned upstream
revision and verifies their SHA-256 hashes. Installation needs internet access. Once installed,
the CLI reads scans offline. The Windows x64, Linux x64 and macOS wheels are listed on PyPI.
[Wheel files](https://pypi.org/project/tesserocr/2.13.0/#files)

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
the run exit with status 1 after processing the remaining PDFs. This includes required OCR that fails or times out.

## How it works

1. `kio2json/pdf_text.py` reads the first three pages with pdfplumber. Pages with no text or
   only page numbers go through the selected OCR engine at 300 dpi. With default Tesseract, if an address appears to have lost
   its `@`, an English single-word pass rereads that crop. The extractor accepts the separator
   only when the rest of both readings agrees. Call `read_pages(path, word_boxes=boxes)` with
   an empty list to collect raw words and their rectangles alongside the page strings. Coordinates
   are PDF points from the top left, with one-based page numbers.
2. `kio2json/classify.py` uses document content. It checks appeal and power-of-attorney
   headings in reading order. A transfer normally needs two distinct accounts, a confirmation heading
   or execution status, and the transaction’s own amount or date. A rejected payment or an
   invoice asking for confirmation gets an empty file.
3. `kio2json/appeal.py`, `power_of_attorney.py` and `bank_transfer.py` extract the fields with
   labelled fields, party sections and grant declarations. The appeal extractor reads the
   challenged act and date from the first charge or its dated introductory sentence.

## Measure

```
uv run python -m evals.run --quick            # dev subset, before a push
uv run python -m evals.run                    # all 60 training cases and the negatives
uv run python -m evals.field_report --errors  # which fields fail, with list items paired inside their parent
uv run python -m evals.field_report --force-ocr --errors   # ignore the text layer: what OCR costs
```

The native-text results use the team's F1 definition in `evals/metrics.py`. The organizers have not published theirs.

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

On the same 196 synthetic documents rendered as 307 images, the strict field report scored **0.903**
with the pip-installed OCR path and **0.775** on the original system-Tesseract path at `4deb354`.
On an Apple M1 with 16 GiB RAM, the full command reported 366 MiB peak RSS. A separate
four-page run measured 727 MiB for the OCR interpreter. Run
`uv run python -m evals.field_report --force-ocr --errors` to reproduce the OCR score.

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
  and two explicitly labelled accounts: one fully masked by asterisks and the other checksum-valid.
  Unlabelled or conflicting roles can leave account fields empty.
  Attorney names retain the grammatical case used in the document.
- Classes, fields and extraction patterns live in Python modules.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
