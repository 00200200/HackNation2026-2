# Firm names and signers in sole-trader mandates

The frozen branch recovered 5/10 firms and 2/10 signer lists on both native PDFs and scans. Starting main recovered 4/10 and 1/10. The panel required 8/10 on each field and both controls correct. Both builds missed both controls, with zero attorney or firm substitutions into personal roles.

The organizer records the full firm name in `mocodawca[].data.nazwa` and each person who signed for that grantor in `mocodawca[].podpisujacy[].imie_nazwisko`. The appointees have their own list. Four natural-person grantor rows in the public training references contain both a firm and a signer. The FAQ instructs extractors to leave missing information empty. [Organizer schema](../../data/uzp/oczekiwane-json/pelnomocnictwo.json) · [FAQ, questions 4–7](../../docs/task/FAQ.md)

PR #123 supplied the proprietor’s identity and NIP. This follow-up reads a printed business name from the grantor’s declaration, registry card, letterhead or stamp. It links separate stationery to the grantor using the issuer designation, printed owner name or matching NIP. A conflicting NIP or owner, contradictory stamp names, blank field or unreadable legend can leave the firm empty. A proprietor or authorized proxy can sign. Recipient acceptance, copy certification, witness and contact sections supply no issuer signature. [Prior results](sole-trader-grantors.md)

## Development fixtures

Nine independently worded fictional grants were rendered as native PDFs. One CEIDG card was also read with Tesseract forced. Runs used the document pipeline and the original test fixtures on both revisions.

| Exact per PDF | Starting main | Candidate |
|---|---:|---:|
| Route, grantor type, personal name and NIP | 10/10 | 10/10 |
| Firm name, including correct abstentions | 8/10 | 10/10 |
| Ordered signer list, including correct abstentions | 9/10 | 10/10 |
| Complete grantor row | 7/10 | 10/10 |

The two recovered firms were printed above the grantor card on issuer stationery and below the declaration in the grantor’s stamp. The recovered signer was a named proxy who signed on behalf of the grantor. Additional native and OCR-text fixtures cover conflicts, foreign stamps, blank signature boxes, acceptance, certification and mixed-page signatures.

A separate development probe exposed an existing identity error. A counterparty card containing an explicitly labelled personal name can replace the grantor’s personal name while retaining the grantor’s NIP. Starting main and the candidate produced the same result with both firm and signer empty. This task evaluated the two requested fields on already identified grantors.

## Independent panel

The coordinator supplied the wording and acceptance thresholds after the grammar froze at `9446b32`. We ran each snapshot once against the same 24 PDFs, with `027e2d6` as paired main. Each of the 12 fictional grants was rendered as native text and as a 300 dpi image-only PDF in its own case folder. The CEIDG form used printed labels, the letterhead preceded the title, and the stamp-only firm appeared in a boxed stamp above the signature. The grants used synthetic checksum-valid identifiers. SN2 printed a personal identifier and no firm or NIP. Native transcriptions, scan text-layer absence, DPI and input hashes were verified before extraction.

For the first grantor we scored the firm at normalized Levenshtein similarity ≥0.80, the nominative personal name, type, NIP and the full ordered signer list. A missing grantor fails every field. An absent firm or NIP needs an explicit null when the panel calls for it. A complete control requires one grantor and all five fields. The fixed thresholds apply to ten positive grants for each representation.

| Positive field | Main native | Frozen native | Main scan | Frozen scan | Frozen correct in both |
|---|---:|---:|---:|---:|---:|
| nazwa | 4/10 | 5/10 | 4/10 | 5/10 | 5/10 |
| podpisujacy | 1/10 | 2/10 | 1/10 | 2/10 | 2/10 |
| imie_nazwisko | 5/10 | 5/10 | 5/10 | 5/10 | 5/10 |
| typ | 6/10 | 6/10 | 6/10 | 6/10 | 6/10 |
| nip | 6/10 | 6/10 | 6/10 | 6/10 | 6/10 |

Each cell lists the fields that missed. ✓ means all five fields matched. F = firm, S = signer list, P = proprietor’s personal name, T = type, N = NIP.

| ID | Printed form | Main native | Frozen native | Main scan | Frozen scan |
|---|---|---|---|---|---|
| S01 | Business declaration | ✓ | ✓ | ✓ | ✓ |
| S02 | Owner of firm | FS | S | FS | S |
| S03 | CEIDG card | FSPTN | FSPTN | FSPTN | FSPTN |
| S04 | Letterhead | FSPTN | FSPTN | FSPTN | FSPTN |
| S05 | Quoted professional firm | FSPTN | FSPTN | FSPTN | FSPTN |
| S06 | Genitive opening | SP | SP | SP | SP |
| S07 | Firm on stamp | FSPTN | FSPTN | FSPTN | FSPTN |
| S08 | General proxy signs | S | S | S | S |
| S09 | Firm before proprietor | S | S | S | S |
| S10 | Attorney shares first name | FS | F | FS | F |
| SN1 | Company control | S | S | S | S |
| SN2 | Private person control | FSPTN | FSPTN | FSPTN | FSPTN |

**Acceptance failed on both renderings.** The panel required 8/10 firms, 8/10 signer lists, zero new wrong assignments and 2/2 complete controls. S02 recovered its firm and S10 recovered its signer. Both builds routed all 24 PDFs correctly. The appointed attorney appeared in zero grantor or signer fields, and the firm appeared in zero personal-name fields, across all 24 outputs from each build.

Four positives (S03, S04, S05 and S07) emitted no grantor on either build. Of the six with a grantor, the frozen build recovered five firms and two signer lists. S06 preserved the printed genitive in the personal-name field, and S08 omitted the general proxy who signed. Both builds scored 0/2 complete controls on each rendering. SN1 retained the legal-entity record but used the representative’s inflected name as signer. SN2 emitted no grantor, so the private individual, signer and expected null firm could not be credited. The panel was scored once per build. The branch received no subsequent extraction changes prompted by these results.

The coordinator’s source panel SHA-256 is `d8b6b06d0847fb49c005b62ba3b25299ca9eb77a61469f552554427eae9c87dc`. The native and scan manifest SHA-256 is `4f7f8b341619b570a3d990199eb60d519db958527c7724607b83411b6e7a6a71`.

## Paired regression gates

Main `13104c6` and the merged feature `59570b4` ran in the same keyless environment, one extraction workload at a time. The table gives UZP / strict micro F1. Each batch used two workers. Each serial scan ran in a separate CLI invocation. The mixed batch contained 120 organizer training positives and the 30 organizer scans.

| Workload | Main `13104c6` | Feature `59570b4` |
|---|---|---|
| Organizer training | 1.0000 / 1.0000, 196/196 exact | 1.0000 / 1.0000, 196/196 exact |
| Mixed organizer batch | 1.0000 / 0.9995, 149/150 exact, 430.0 s | 1.0000 / 0.9995, 149/150 exact, 239.1 s |
| Scans inside mixed batch | 1.0000 / 0.9974, 29/30 exact | 1.0000 / 0.9974, 29/30 exact |
| Organizer scans, raw standalone | 1.0000 / 0.9974, 29/30 exact, 215.6 s | 1.0000 / 0.9974, 29/30 exact, 159.7 s |
| Organizer scans, individual serial invocations | 1.0000 / 0.9974, 29/30 exact | Pending |
| Corpus 1 development | Pending | Pending |
| Corpus 2 development | Pending | Pending |
| Fixed variants | Pending | Pending |
| Case-linked development | Pending | Pending |

The paired builds produced byte-identical output across all 196 training PDFs, all 150 mixed PDFs and all 30 standalone scans. The raw batch results went to the coordinator before the serial measurements.

## Release integration

Release product `2c44f26` merged main `50d0419`. The four mandate extraction files are byte-identical to the panel freeze. The official training run on the clean merge was 196/196 exact, UZP and strict F1 1.0000, with every output byte-identical to both members of the earlier pair. The ordered 196-file SHA-256 digest `27ce5adb70df47f1961fc2ec316b6536f864ee1e305252ad97ae657184ce4f54` also matches the published delivery-proof branch measurement at `e35c57e`, whose product, data and evaluator match `50d0419`. [Full release training results](latest.json)

`make check` passed on this merge. Ruff lint and format, dependency synchronization and all 2,668 tests passed. Pytest reported three SWIG deprecation warnings.
