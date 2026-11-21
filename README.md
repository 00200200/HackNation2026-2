# Odwołania2json

HackNation 2026 entry for the Public Procurement Office (UZP) challenge: read the PDFs of a KIO
appeal case, decide what each one is, and write the organizer's JSON for it. Task brief:
`docs/task/BRIEF.md`. Project state and open work: `WORKLOG.md`.

The extraction path is a rule-based baseline. It uses no language model yet.

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
2. `kio2json/classify.py` uses document content. It checks appeal and power-of-attorney
   headings in reading order. A transfer needs two distinct accounts, a confirmation heading
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
- A confirmation with a masked account, or with neither a transaction amount nor a date,
  can be rejected. Unlabelled or conflicting account roles can produce null fields.
- The party and signature rules need legible section boundaries. A missing grantor heading or
  an ambiguous signature can leave a party or signer out. Attorney names retain the grammatical
  case used in the document.
- Nothing is configuration-driven yet: classes, fields and patterns live in Python modules.
- UNCONFIRMED: what "empty JSON" means for unrelated documents. We write an empty file, as the
  organizer README words it.
- UNCONFIRMED: value types. `pesel` is a number in the organizer's annotated example and a string
  in the reference JSONs; we write a string. The annotated transfer example has a 24-digit
  account, while the rules expect the standard 26 digits.
