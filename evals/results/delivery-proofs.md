# Delivery-proof routing

## Change

The default PDF router checks the authored message on electronic delivery and signature-validation forms. It excludes attachment lists and quoted text before checking for a filing, delegation or transfer. Field extraction still uses the original document.

## Development regressions

On the five committed attachment-title fixtures, main routes each form as a power of attorney. The frozen branch returns five empty objects. The fixtures cover an ePUAP submission proof, a sending proof, a receipt proof, a signature report and a general letter. Across all 20 focused tests, main passes seven and the branch passes all 20. [Regression tests](../../tests/test_delivery_proofs.py)

PDF CLI results on those five forms and three matched substantive bodies follow. Each view uses the same rendered bytes for both revisions.

| View | Revision | Exact empty forms | Correct genuine routes |
|---|---|---:|---:|
| native | main | 0/5 | 1/3 |
| native | branch | 5/5 | 3/3 |
| scan | main | 0/5 | 1/3 |
| scan | branch | 5/5 | 3/3 |

## Independent acceptance panel

The coordinator wrote 24 items after the router froze at `e5f1460`. Each item was rendered as native text and a 200 dpi grayscale scan with 0.45° skew. Six negatives used a labelled table and six used a letter layout. Both revisions processed the same 48 PDFs once through the keyless CLI with two workers.

| View | Revision | Exact empty negatives | Wrong non-null leaves on negatives | Correct positive routes | Valid JSON | Previously correct positives with identical output |
|---|---|---:|---:|---:|---:|---:|
| native | main | 12/12 | 0 | 11/12 | 24/24 | — |
| native | branch | 12/12 | 0 | 11/12 | 24/24 | 11/11 |
| scan | main | 12/12 | 0 | 11/12 | 24/24 | — |
| scan | branch | 12/12 | 0 | 11/12 | 24/24 | 11/11 |

Acceptance passed in each view. All 48 files were byte-identical across revisions. Both revisions returned an empty object for transfer P11. The panel supplies class labels. Positive field preservation uses byte equality against correct main outputs. The following cells show the routes on main and the branch, respectively.

| Item | Expected | Native main → branch | Scan main → branch |
|---|---|---|---|
| N01 | {} | {} → {} | {} → {} |
| N02 | {} | {} → {} | {} → {} |
| N03 | {} | {} → {} | {} → {} |
| N04 | {} | {} → {} | {} → {} |
| N05 | {} | {} → {} | {} → {} |
| N06 | {} | {} → {} | {} → {} |
| N07 | {} | {} → {} | {} → {} |
| N08 | {} | {} → {} | {} → {} |
| N09 | {} | {} → {} | {} → {} |
| N10 | {} | {} → {} | {} → {} |
| N11 | {} | {} → {} | {} → {} |
| N12 | {} | {} → {} | {} → {} |
| P01 | appeal | appeal → appeal | appeal → appeal |
| P02 | appeal | appeal → appeal | appeal → appeal |
| P03 | appeal | appeal → appeal | appeal → appeal |
| P04 | appeal | appeal → appeal | appeal → appeal |
| P05 | grant | grant → grant | grant → grant |
| P06 | grant | grant → grant | grant → grant |
| P07 | grant | grant → grant | grant → grant |
| P08 | grant | grant → grant | grant → grant |
| P09 | transfer | transfer → transfer | transfer → transfer |
| P10 | transfer | transfer → transfer | transfer → transfer |
| P11 | transfer | {} → {} | {} → {} |
| P12 | transfer | transfer → transfer | transfer → transfer |

## Regression gates

Paired with merged main `725765b` on the same host and CPython 3.13.1. Scores are UZP / strict micro-F1. [Main measurements](merged-main-725765b.json)

| Gate | Main | Branch |
|---|---:|---:|
| Organizer training | 1.00000 / 1.00000, 196/196 exact | 1.00000 / 1.00000, 196/196 exact |
| Organizer scans, raw | 1.00000 / 0.99742, 29/30 exact | 1.00000 / 0.99742, 29/30 exact |
| Organizer scans after serial replay | 1.00000 / 0.99742, 29/30 exact | 1.00000 / 0.99742, 29/30 exact |
| Fixed variants | 0.95123 / 0.92644 | 0.95123 / 0.92644 |
| Linked development | 0.97288 / 0.96671, 90/112 exact | 0.97288 / 0.96671, 90/112 exact |
| Corpus 1 development | 0.92857 / 0.88211, 10/22 exact | 0.92857 / 0.88211, 10/22 exact |
| Corpus 2 development | 0.92437 / 0.89514, 22/39 exact | 0.92437 / 0.89514, 22/39 exact |
| 150 PDFs, two workers | 343.5 s | 586.7 s |

The training output digest matched on all 196 files. The sole nonexact organizer scan was transfer 0008. Its serial output matched the raw batch bytes. Both real development panels matched main byte for byte across all 61 files. All PDF inputs and predictions created for measurement were removed after scoring.
