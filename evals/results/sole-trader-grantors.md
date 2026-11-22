# Sole-trader grantors in powers of attorney

The candidate recovered all eight previously missed grantor names on the reserved sole-trader family, with zero false positives. It also recovered all eight NIPs and person types. Business names and signer names remained missing on all eight PDFs, so no complete record matched exactly.

The extractor was frozen at `ed4054d` on top of `cf67694` (PR #112). All PDF gates used the local keyless CLI. Batch runs used two workers unless identified as serial.

## Development evidence

The default case development split has 14 distinct mandates in six families. Each grantor is a legal entity. Native and scanned renderings yield 28 PDFs with zero reference personal names. Starting main reproduced 88/112 exact JSONs and 0.9603 UZP F1 on this split. Corpus 1 development has no natural-person grantor among four grantors. Corpus 2 development has two in one mandate among six grantors.

| Independently worded controls | Starting main | Frozen parser |
|---|---:|---:|
| Positive owner identifications | 7/17 | 17/17 |
| Correct abstentions | 8/9 | 9/9 |

The independent control set was written before the extractor changes. The positive cases cover a proprietor in a registration card, grammatical subject, business name, or explicitly identified signature. The negatives separate attorney, officer, witness and address evidence from the grantor. Additional regression cases cover a genitive repeated in the firm, ambiguous firms, attorney headings, business-only entrepreneur captions and registry numbers. An independently rendered PDF passed through the normal CLI with the correct personal name, firm and NIP.

On corpus 1, the only measured field change was one fewer false positive in an appeal representative’s firm name. Mandate F1 held at 0.9583. On corpus 2, the one mandate containing two natural-person grantors already scored 1.0000 on starting main.

## Linked case benchmark

The development comparison uses a fresh starting-main run. Reserved baseline values come from the aggregate published with PR #112. The default reserved split was scored once on the frozen extractor, after an AST-equivalent test fixture formatting change in `8f78494`. Only the aggregate report was read. Each distinct case contributes both a native PDF and a scan.

| Split or family | PDFs | UZP F1, baseline → frozen | Strict F1, baseline → frozen | Exact JSON, baseline → frozen |
|---|---:|---:|---:|---:|
| Development | 112 | 0.9603 → 0.9603 | 0.9566 → 0.9566 | 88 → 88 |
| Development mandates | 28 | 0.9468 → 0.9468 | 0.9555 → 0.9555 | 22 → 22 |
| Reserved | 96 | 0.7923 → 0.8141 | 0.7705 → 0.7895 | 41 → 41 |
| Reserved mandates | 24 | 0.7470 → 0.8315 | 0.7807 → 0.8468 | 8 → 8 |
| Reserved sole-trader mandates | 8 | 0.3750 → 0.8182 | unreported → 0.8235 | 0 → 0 |

### Reserved sole-trader fields

On the prior freeze the personal-name field had zero matches, zero false positives and eight omissions. The frozen candidate produced the following aggregate counts.

| Field | TP | FP | FN | UZP F1 |
|---|---:|---:|---:|---:|
| `mocodawca[].data.imie_nazwisko` | 8 | 0 | 0 | 1.0000 |
| `mocodawca[].data.krs` | 0 | 0 | 0 | — |
| `mocodawca[].data.nazwa` | 0 | 0 | 8 | 0.0000 |
| `mocodawca[].data.nip` | 8 | 0 | 0 | 1.0000 |
| `mocodawca[].data.typ` | 8 | 0 | 0 | 1.0000 |
| `mocodawca[].podpisujacy[].imie_nazwisko` | 0 | 0 | 8 | 0.0000 |
| `pelnomocnicy[].imie_nazwisko` | 12 | 0 | 0 | 1.0000 |
| `pelnomocnicy[].pesel` | 0 | 0 | 0 | — |

## Release gates on the original freeze

| Gate | Starting main | Frozen extractor |
|---|---:|---:|
| Organizer training, 196 PDFs | 196 exact | 196 exact and 196 byte-identical |
| Corpus 1 development | 0.9256 UZP, 10/22 exact | 0.9286 UZP, 10/22 exact |
| Corpus 2 development | 0.9244 UZP, 22/39 exact | 0.9244 UZP, 22/39 exact, 39/39 byte-identical |
| Organizer scan batch | 0.9785 UZP, 20/30 exact | 0.9785 UZP, 20/30 exact, 30/30 byte-identical |
| Organizer scans, individual serial reruns | — | 1.0000 UZP, 0.9974 strict, 29/30 exact |
| Fixed variants, 240 PDFs | 0.9090 UZP, 0.8689 strict | 0.9134 UZP, 0.8741 strict |

The variants gate passed the archived UZP threshold of 0.9125 on the candidate. Starting main fell below that threshold on the same host. The candidate recovered three of four personal names (starting main recovered zero) and three additional values each for firm, NIP and type. No additional false positives occurred on those four fields. The remaining three true-positive differences were bank accounts subject to timed OCR verification.

The 30-scan two-worker batch fell short of the organizer target on both builds, with identical output bytes. Two unclassified receipts accounted for all ten missing fields. The 30 independent serial invocations each received a fresh OCR deadline.

Development dataset SHA-256 was `78c3787a990fe7201ae26bb504d43e3a2f7ebda18b1c8d4c1a3c0fc4e4ce415c`. Reserved dataset SHA-256 was `0b0dd6dab52ebf8a2c745f3c52fb516bb51b23de14c4383e310988d2305b3895`. Fixed variants SHA-256 was `53414e5959d93426f1553cc36fcbe86968fca23edb80a959740654790b20dd03`.


The benchmark commands were `make eval-cases CASE_ARGS="--split development"`, `make eval-cases CASE_ARGS="--split reserved"` and `make eval-variants`. Each invocation used a separate aggregate destination.

## Integration with updated main

Commit `e5aa752` integrates main `725765b`, including the two-column appeal and bank-transfer changes. The two grantor extraction modules are byte-identical to the reserved freeze. The table below reports the merged run. The reserved figures above belong to the earlier freeze.

| Gate | Merged result |
|---|---|
| Organizer training | 196/196 exact and 196/196 byte-identical to the starting-main outputs |
| Organizer scans in a 150-PDF, two-worker batch | 1.0000 UZP, 0.9974 strict, 29/30 exact |
| Organizer scans, 30 individual serial invocations | 1.0000 UZP, 0.9974 strict, 29/30 exact |
| Case development | 0.9729 UZP, 0.9667 strict, 90/112 exact |
| Fixed variants | 0.9512 on `725765b` → 0.9545 merged, archived threshold 0.9512 |
| Corpus 1 development | 0.9286 UZP, 0.8821 strict, 10/22 exact |
| Corpus 2 development | 0.9244 UZP, 0.8951 strict, 22/39 exact |
| `make check` | Ruff checks passed and 2,434 tests passed |

The `725765b` variants run matched 0/4 personal names. The merged parser matched 3/4 with 0 false positives. The mixed organizer run took 125.9 seconds, and the 30 serial invocations took 381.7 seconds.
