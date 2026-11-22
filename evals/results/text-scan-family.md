# Scan-set readers on text PDFs (#101)

Measured on 22.11.2026: main `027e2d6` (#123) against branch `fix/text-pdf-scan-readers` merged with it. These are
scratch runs; the outputs are not committed. Counts follow #59: a wrong value is one false positive, a missing value
one false negative.

## The 11 organizer documents rebuilt as text PDFs

The documents of `tests/fixtures/scan_family/` were written to PDFs with `write_text_pdf` from
`tests/test_text_scan_family.py`, run through `python -m kio2json` and scored against the organizer references in
`data/uzp/dane/skany/` with `evals.metrics.score_doc`. `uv run pytest tests/test_text_scan_family.py` repeats the
comparison for the 13 fixtures. The scan readers were written for these documents, so this set is in-sample: it shows
that the text-layer path reaches the score of the scan path, not what the hidden set will give.

| Document | main tp / fp / fn | branch tp / fp / fn |
|---|---|---|
| appeal 0001 | 14 / 0 / 3 | 17 / 0 / 0 |
| appeal 0004 | 19 / 1 / 1 | 21 / 0 / 0 |
| appeal 0007 | 16 / 0 / 3 | 19 / 0 / 0 |
| appeal 0009 | 11 / 2 / 1 | 14 / 0 / 0 |
| appeal 0010 | 12 / 1 / 3 | 16 / 0 / 0 |
| grant 0003 | 5 / 0 / 1 | 6 / 0 / 0 |
| grant 0004 | 6 / 0 / 2 | 8 / 0 / 0 |
| grant 0005 | 5 / 0 / 3 | 8 / 0 / 0 |
| grant 0007 | 8 / 0 / 4 | 12 / 0 / 0 |
| grant 0009 | 3 / 1 / 6 | 10 / 0 / 0 |
| grant 0010 | 4 / 1 / 2 | 6 / 1 / 0 |
| **UZP micro F1** | **0.8548** (103 / 6 / 29) | **0.9964** (137 / 1 / 0) |

The one error left is grant 0010, `mocodawca[].data.nazwa`. Main's sole-trader rule (#109) names the grantor by its
firm, as the four training references with a sole-trader grantor do. The organizer's reference for scan 0010 leaves
the name null, and the scan reader abstains on it. Main gives the same value; the test names that one field.

## Other checks

| Check | main | branch |
|---|---|---|
| 196 training and negative outputs (`data/uzp/dane/`) | | byte-identical |
| 30 organizer scans | | byte-identical |
| `make eval-cases`, UZP / strict / exact | 0.9040 / 0.8856 / 131 | 0.9072 / 0.8903 / 133 |
| `make eval-cases`, tp / fp / fn | 1384 / 16 / 278 | 1393 / 16 / 269 |
| `make eval-variants`, 240 PDFs, micro F1 | 0.9545 | 0.9545 (all 240 outputs byte-identical) |
| `python -m evals.document_variants`, 390 documents, UZP / strict | 0.8691 / 0.8044 | 0.8727 / 0.8082 |
| `python -m evals.document_variants`, tp / fp / fn | 1504 / 68 / 385 | 1515 / 65 / 377 |
| `python -m evals.document_variants`, classification accuracy | 0.9333 | 0.9389 |
| 10 receipts rebuilt from scan OCR text, UZP micro F1 | 0.3881 (13 / 0 / 41) | 0.6829 (28 / 3 / 23) |

- The byte-identity checks compare two `python -m kio2json` runs over the same inputs with `diff -r`.
- The 9 extra true positives of `make eval-cases` are all in the late-list native family (UZP 0.8666 to 0.8794).
- In the document variants the classification gain is one document: the text receipt
  `przyklad_44-v0/potwierdzenie_przelewu.pdf`, which main writes as an empty file, is now read as a transfer
  confirmation (168 to 169 of 180 positives). The layout repairs of `repair_receipt_layout` now apply to text receipts.
- The receipts are the OCR text of the ten organizer receipt scans used as a text layer; only 0003 and 0005 are
  committed as fixtures. The checksum substitution of `normalize_receipt` was left off text pages after a run on main
  `4f33ee3` over the 196 training and negative PDFs: with it, 7 outputs changed and 9 printed accounts that fail the
  checksum became null (`na_rachunek` 5, `z_rachunku` 4).
- The full eval (`python -m evals.run`) scores the synthetic training and negative PDFs against their original
  references. The pre-push hook records its result in `.git/eval-latest.json`; it is not committed. Those 196
  outputs are byte-identical to main, so this change does not move that score.

Not run: corpus 1 and 2 dev (`make eval-real` needs `HN_REAL_CORPUS`, and there is no local copy on this machine).
