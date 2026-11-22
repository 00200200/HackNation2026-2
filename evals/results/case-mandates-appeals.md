# Mandates and appeals on linked cases

## Development errors before tuning

The initial table was compiled on starting main `a84258d` before any extractor edits. Its 14 development cases contain paired native text and scanned renderings. Fourteen cases produce 28 PDFs per class. FP and FN count incorrect extractions and missing reference values under the UZP matching rules. A missing document routing decision can affect several fields.

| Class / field | TP | FP | FN | Observed mechanism |
|---|---:|---:|---:|---|
| odwolanie / OdwolanieKIO.czynnosc_opis | 0 | 0 | 28 | Action described in a dated clause or first charge outside the recognized action patterns |
| odwolanie / OdwolanieKIO.czynnosc_powod_id | 0 | 0 | 28 | Action described in a dated clause or first charge outside the recognized action patterns |
| odwolanie / OdwolanieKIO.czynnosc_dzien | 0 | 0 | 24 | Action described in a dated clause or first charge outside the recognized action patterns |
| odwolanie / Odwolujacy[].pelnomocnik.imie_nazwisko | 13 | 0 | 15 | Attorney title, name or contact share a tightly set row or a labelled role section |
| odwolanie / ZamowieniePubliczne.numer_postepowania | 13 | 1 | 14 | Reference or publication label is joined to its value, or OCR distorts the identifier |
| odwolanie / Odwolujacy[].krs | 14 | 0 | 14 | Concatenated registry cells or an unrecognized grantor card |
| odwolanie / Odwolujacy[].nip | 14 | 0 | 14 | Concatenated registry cells or an unrecognized grantor card |
| odwolanie / Odwolujacy[].regon | 14 | 0 | 14 | Concatenated registry cells or an unrecognized grantor card |
| odwolanie / Zamawiajacy[].nip | 14 | 0 | 14 | Concatenated registry cells or an unrecognized grantor card |
| odwolanie / Zamawiajacy[].regon | 14 | 0 | 14 | Concatenated registry cells or an unrecognized grantor card |
| odwolanie / OdwolanieKIO.data | 11 | 0 | 11 | Place and date run together on the native text layer |
| odwolanie / OdwolanieKIO.miejscowosc | 11 | 0 | 11 | Place and date run together on the native text layer |
| odwolanie / Odwolujacy[].pelnomocnik.mail | 18 | 0 | 10 | Attorney title, name or contact share a tightly set row or a labelled role section |
| odwolanie / Odwolujacy[].pelnomocnik.nazwa | 27 | 1 | 0 | Attorney title, name or contact share a tightly set row or a labelled role section |
| odwolanie / ZamowieniePubliczne.numer_bzp | 19 | 0 | 1 | Reference or publication label is joined to its value, or OCR distorts the identifier |
| odwolanie / Odwolujacy[].nazwa | 28 | 0 | 0 | No UZP error on development |
| odwolanie / Odwolujacy[].przez-pelnomocnika | 28 | 0 | 0 | No UZP error on development |
| odwolanie / Zamawiajacy[].krs | 0 | 0 | 0 | No UZP error on development |
| odwolanie / Zamawiajacy[].nazwa | 28 | 0 | 0 | No UZP error on development |
| odwolanie / Zamawiajacy[].prowadzacy_postepowanie | 0 | 0 | 0 | No UZP error on development |
| odwolanie / ZamowieniePubliczne.numer_ted | 20 | 0 | 0 | No UZP error on development |
| odwolanie / ZamowieniePubliczne.tytul | 28 | 0 | 0 | No UZP error on development |
| pelnomocnictwo / mocodawca[].podpisujacy[].imie_nazwisko | 8 | 0 | 34 | Officer names are in separately labelled signature rows |
| pelnomocnictwo / pelnomocnicy[].imie_nazwisko | 22 | 0 | 22 | Attorney title, name or contact share a tightly set row or a labelled role section |
| pelnomocnictwo / mocodawca[].data.nazwa | 18 | 4 | 6 | Grantor role/name boundary or organization description |
| pelnomocnictwo / mocodawca[].data.krs | 22 | 0 | 6 | Concatenated registry cells or an unrecognized grantor card |
| pelnomocnictwo / mocodawca[].data.nip | 22 | 0 | 6 | Concatenated registry cells or an unrecognized grantor card |
| pelnomocnictwo / mocodawca[].data.typ | 22 | 0 | 6 | Grantor role/name boundary or organization description |
| pelnomocnictwo / mocodawca[].data.imie_nazwisko | 0 | 0 | 0 | No UZP error on development |
| pelnomocnictwo / pelnomocnicy[].pesel | 0 | 0 | 0 | No UZP error on development |

## Class results by split

| Split | Class | PDFs | UZP F1, main → final | Strict F1, main → final | Exact JSON, main → final | Correct routes, main → final |
|---|---|---:|---:|---:|---:|---:|
| development | overall | 112 | 0.7699 → 0.9603 | 0.7026 → 0.9566 | 52 → 88 | 106 → 106 |
| development | odwolanie | 28 | 0.7458 → 0.9875 | 0.6510 → 0.9773 | 0 → 17 | 28 → 28 |
| development | pelnomocnictwo | 28 | 0.7308 → 0.9468 | 0.7315 → 0.9555 | 3 → 22 | 28 → 28 |
| development | przelew | 28 | 0.8805 → 0.8805 | 0.8733 → 0.8733 | 21 → 21 | 22 → 22 |
| development | negatywny | 28 | — → — | — → — | 28 → 28 | 28 → 28 |
| reserved | overall | 96 | 0.6564 → 0.7923 | 0.6131 → 0.7705 | 33 → 41 | 82 → 82 |
| reserved | odwolanie | 24 | 0.7072 → 0.8666 | 0.6221 → 0.8073 | 0 → 1 | 24 → 24 |
| reserved | pelnomocnictwo | 24 | 0.5993 → 0.7470 | 0.6169 → 0.7807 | 1 → 8 | 24 → 24 |
| reserved | przelew | 24 | 0.5591 → 0.5591 | 0.5588 → 0.5588 | 8 → 8 | 10 → 10 |
| reserved | negatywny | 24 | — → — | — → — | 24 → 24 | 24 → 24 |

## Full panel

The published baseline and candidate use the same 26 case identities, each rendered twice. Exact includes empty output for unrelated documents. UZP F1 scores positive fields and can therefore be undefined for an entirely rejected negative class.

| Class | PDFs | UZP F1, main → final | Strict F1, main → final | Exact JSON, main → final |
|---|---:|---:|---:|---:|
| overall | 208 | 0.7191 → 0.8876 | 0.6617 → 0.8720 | 85 → 129 |
| odwolanie | 52 | 0.7285 → 0.9355 | 0.6377 → 0.8991 | 0 → 18 |
| pelnomocnictwo | 52 | 0.6667 → 0.8531 | 0.6763 → 0.8736 | 4 → 30 |
| przelew | 52 | 0.7557 → 0.7557 | 0.7460 → 0.7460 | 29 → 29 |
| negatywny | 52 | — → — | — → — | 52 → 52 |
| view/native | 104 | 0.6086 → 0.9076 | 0.5339 → 0.8926 | 44 → 75 |
| view/scan | 104 | 0.8133 → 0.8670 | 0.7865 → 0.8508 | 41 → 54 |

## Change by field

Each cell shows UZP F1 followed by the change in false positives and false negatives. A dash means the panel had no scored positive or erroneous value for the field. The reserved figures were collected after the rule changes and organizer compatibility correction were frozen.

| Field | Development F1 | Dev FP | Dev FN | Reserved F1 | Reserved FP | Reserved FN |
|---|---:|---:|---:|---:|---:|---:|
| OdwolanieKIO.czynnosc_dzien | 0.0000 → 0.9787 | 0 → 0 | 24 → 1 | 0.0952 → 0.0952 | 0 → 0 | 19 → 19 |
| OdwolanieKIO.czynnosc_opis | 0.0000 → 0.9434 | 0 → 0 | 28 → 3 | 0.2857 → 0.2857 | 0 → 0 | 20 → 20 |
| OdwolanieKIO.czynnosc_powod_id | 0.0000 → 0.9434 | 0 → 0 | 28 → 3 | 0.2857 → 0.2857 | 0 → 0 | 20 → 20 |
| OdwolanieKIO.data | 0.6667 → 1.0000 | 0 → 0 | 11 → 0 | 0.6667 → 1.0000 | 0 → 0 | 9 → 0 |
| OdwolanieKIO.miejscowosc | 0.6667 → 1.0000 | 0 → 0 | 11 → 0 | 0.6667 → 1.0000 | 0 → 0 | 9 → 0 |
| Odwolujacy[].krs | 0.6667 → 1.0000 | 0 → 0 | 14 → 0 | 0.6087 → 0.9677 | 0 → 0 | 9 → 1 |
| Odwolujacy[].nazwa | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 | 0.9787 → 0.9787 | 0 → 0 | 1 → 1 |
| Odwolujacy[].nip | 0.6667 → 1.0000 | 0 → 0 | 14 → 0 | 0.6286 → 0.9787 | 0 → 0 | 13 → 1 |
| Odwolujacy[].pelnomocnik.imie_nazwisko | 0.6341 → 0.9818 | 0 → 0 | 15 → 1 | 0.4516 → 0.7692 | 0 → 0 | 17 → 9 |
| Odwolujacy[].pelnomocnik.mail | 0.7826 → 0.9818 | 0 → 0 | 10 → 1 | 0.5455 → 0.6667 | 0 → 0 | 15 → 12 |
| Odwolujacy[].pelnomocnik.nazwa | 0.9818 → 0.9630 | 1 → 2 | 0 → 0 | 0.7368 → 0.7368 | 1 → 1 | 9 → 9 |
| Odwolujacy[].przez-pelnomocnika | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 | 0.7692 → 0.7692 | 8 → 8 | 1 → 1 |
| Odwolujacy[].regon | 0.6667 → 1.0000 | 0 → 0 | 14 → 0 | 0.6286 → 0.9787 | 0 → 0 | 13 → 1 |
| Zamawiajacy[].krs | — → — | 0 → 0 | 0 → 0 | — → — | 0 → 0 | 0 → 0 |
| Zamawiajacy[].nazwa | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 |
| Zamawiajacy[].nip | 0.6667 → 1.0000 | 0 → 0 | 14 → 0 | 0.6667 → 1.0000 | 0 → 0 | 12 → 0 |
| Zamawiajacy[].prowadzacy_postepowanie | — → — | 0 → 0 | 0 → 0 | — → — | 0 → 0 | 0 → 0 |
| Zamawiajacy[].regon | 0.6667 → 1.0000 | 0 → 0 | 14 → 0 | 0.6286 → 0.9787 | 1 → 1 | 12 → 0 |
| ZamowieniePubliczne.numer_bzp | 0.9744 → 0.9744 | 0 → 0 | 1 → 1 | 0.9744 → 0.9744 | 0 → 0 | 1 → 1 |
| ZamowieniePubliczne.numer_postepowania | 0.6341 → 0.9818 | 1 → 1 | 14 → 0 | 0.6667 → 1.0000 | 0 → 0 | 12 → 0 |
| ZamowieniePubliczne.numer_ted | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 |
| ZamowieniePubliczne.tytul | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 | 1.0000 → 1.0000 | 0 → 0 | 0 → 0 |
| mocodawca[].data.imie_nazwisko | — → — | 0 → 0 | 0 → 0 | 0.0000 → 0.0000 | 0 → 0 | 8 → 8 |
| mocodawca[].data.krs | 0.8800 → 0.9434 | 0 → 0 | 6 → 3 | 0.8000 → 0.8000 | 0 → 0 | 8 → 8 |
| mocodawca[].data.nazwa | 0.7826 → 0.9434 | 4 → 0 | 6 → 3 | 0.6667 → 0.6667 | 0 → 0 | 16 → 16 |
| mocodawca[].data.nip | 0.8800 → 0.9434 | 0 → 0 | 6 → 3 | 0.6667 → 0.6667 | 0 → 0 | 16 → 16 |
| mocodawca[].data.typ | 0.8800 → 0.9434 | 0 → 0 | 6 → 3 | 0.6667 → 0.6667 | 0 → 0 | 16 → 16 |
| mocodawca[].podpisujacy[].imie_nazwisko | 0.3200 → 0.8947 | 0 → 0 | 34 → 8 | 0.2500 → 0.6875 | 0 → 0 | 36 → 20 |
| pelnomocnicy[].imie_nazwisko | 0.6667 → 1.0000 | 0 → 0 | 22 → 0 | 0.6667 → 1.0000 | 0 → 0 | 19 → 0 |
| pelnomocnicy[].pesel | — → — | 0 → 0 | 0 → 0 | — → — | 0 → 0 | 0 → 0 |

The reserved sole-trader family improved from 0.2069 to 0.3750 UZP on 8 PDFs. Exact grants changed from 0 to 0. The reserved grantor personal-name field still had 8 omissions and 0 matches, compared with 8 omissions and 0 matches on main. Independently written examples demonstrate the supported grammar; the reserved result measures its remaining coverage gap. The reserved documents were not used for further tuning.


## Mandate families and document rendering

| Split | Family or rendering | PDFs | UZP F1, main → final | Exact JSON, main → final |
|---|---|---:|---:|---:|
| development | family/early-modular | 28 | 0.7458 → 0.9875 | 0 → 17 |
| development | view/native | 56 | 0.6677 → 0.9805 | 26 → 53 |
| development | odwolanie/native | 14 | 0.5652 → 1.0000 | 0 → 14 |
| development | view/scan | 56 | 0.8575 → 0.9392 | 26 → 35 |
| development | odwolanie/scan | 14 | 0.8861 → 0.9748 | 0 → 3 |
| development | family/early-paragraphs | 6 | 0.5714 → 1.0000 | 0 → 6 |
| development | pelnomocnictwo/native | 14 | 0.6531 → 0.9688 | 0 → 13 |
| development | pelnomocnictwo/scan | 14 | 0.8000 → 0.9239 | 3 → 9 |
| development | family/early_order | 4 | 1.0000 → 1.0000 | 4 → 4 |
| development | family/request-for-authority | 14 | — → — | 14 → 14 |
| development | family/early-register | 6 | 0.6667 → 0.8169 | 0 → 3 |
| development | family/early_cards | 4 | 1.0000 → 1.0000 | 4 → 4 |
| development | family/payment-advice | 14 | — → — | 14 → 14 |
| development | family/early-procedural | 4 | 0.8000 → 1.0000 | 0 → 3 |
| development | family/early_thermal | 4 | 0.6667 → 0.6667 | 2 → 2 |
| development | family/early-letterhead | 4 | 0.8462 → 0.9831 | 1 → 3 |
| development | family/early_summary | 4 | 1.0000 → 1.0000 | 4 → 4 |
| development | family/early-panels | 4 | 0.8696 → 1.0000 | 1 → 4 |
| development | family/early_letter | 4 | 0.0000 → 0.0000 | 0 → 0 |
| development | family/early-short | 4 | 0.6667 → 0.8889 | 1 → 3 |
| development | family/early_sections | 4 | 1.0000 → 1.0000 | 4 → 4 |
| development | family/early_register | 4 | 0.9767 → 0.9767 | 3 → 3 |
| reserved | family/late-list | 24 | 0.7072 → 0.8666 | 0 → 1 |
| reserved | view/native | 48 | 0.5353 → 0.8115 | 18 → 22 |
| reserved | odwolanie/native | 12 | 0.5232 → 0.8737 | 0 → 0 |
| reserved | view/scan | 48 | 0.7591 → 0.7726 | 15 → 19 |
| reserved | odwolanie/scan | 12 | 0.8505 → 0.8593 | 0 → 1 |
| reserved | family/late-company | 8 | 0.8400 → 1.0000 | 1 → 8 |
| reserved | pelnomocnictwo/native | 12 | 0.4706 → 0.7545 | 0 → 4 |
| reserved | pelnomocnictwo/scan | 12 | 0.7081 → 0.7394 | 1 → 4 |
| reserved | family/late_table | 4 | 1.0000 → 1.0000 | 4 → 4 |
| reserved | family/decision-extract | 24 | — → — | 24 → 24 |
| reserved | family/late-consortium | 8 | 0.5899 → 0.7105 | 0 → 0 |
| reserved | family/scan_participants | 4 | 0.8108 → 0.8108 | 2 → 2 |
| reserved | family/late-trader | 8 | 0.2069 → 0.3750 | 0 → 0 |
| reserved | family/scan_history | 4 | 0.0000 → 0.0000 | 0 → 0 |
| reserved | family/scan_order | 4 | 0.0000 → 0.0000 | 0 → 0 |
| reserved | family/scan_operation | 4 | 0.0000 → 0.0000 | 0 → 0 |
| reserved | family/scan_bordered | 4 | 0.8293 → 0.8293 | 2 → 2 |

## Measurements

### Development sequence

| Development run | Appeals, UZP (exact) | Mandates, UZP (exact) |
|---|---:|---:|
| Main, native only | 0.5652 (0/14) | 0.6531 (0/14) |
| Narrow PDF spacing only, native | 0.9180 (0/14) | 0.7702 (0/14) |
| Combined extraction, native | 1.0000 (14/14) | 0.9688 (13/14) |
| Main, both renderings | 0.7458 (0/28) | 0.7308 (3/28) |
| First integrated rules, both renderings | 0.9758 (15/28) | 0.9468 (22/28) |
| Frozen, both renderings | 0.9875 (17/28) | 0.9468 (22/28) |

Native extraction retries pdfplumber with a narrower horizontal tolerance only when it restores a fused registry label and preserves the entire glyph sequence. The paired scan uses the existing OCR entry point. Spacing alone recovered registry fields but yielded zero exact native appeals or mandates.

Appeals tie the opening account to an authority decision preceding a first-charge heading. A date must belong to the challenged act. Counsel contact repair requires the correct party block. Mandates reuse the existing Polish name inflector, appointment parser and registry reader. Grantor, attorney, witness and signer roles provide boundaries for identifiers and lists. The personal name and a separately printed business name occupy different fields. REGON provides evidence in the source, and the organizer grantor schema provides NIP and KRS output slots. A sole proprietor has null KRS.

The development split contained no natural-person grantor. Independently written cases exercised nominative conversion, identity cards, legal-entity officers, witnesses and signature attribution before the reserved evaluation.

### Real development splits

Corpus 1 dev (22 PDFs) scored 0.9256 → 0.9256 UZP and 0.8780 → 0.8780 strict. Final macro class F1 was 0.8998, with appeals 0.9412, mandates 0.9583 and transfers 0.8000. 22 outputs matched main byte for byte.

The first integration and the initial freeze scored 0.9256 and 0.9256 UZP, respectively.

Main macro class F1 was 0.8998, with appeals 0.9412, mandates 0.9583 and transfers 0.8000. Starting-main routing was negatywny 7/7, odwolanie 8/8, pelnomocnictwo 3/3, przelew 4/4. Final routing was negatywny 7/7, odwolanie 8/8, pelnomocnictwo 3/3, przelew 4/4.

Largest remaining development field errors by count were przelew_bankowy.tytul (4), Zamawiajacy.nazwa (4), ZamowieniePubliczne.tytul (3), Odwolujacy.pelnomocnik.nazwa (3), Odwolujacy.pelnomocnik.imie_nazwisko (2), mocodawca.podpisujacy.imie_nazwisko (2).

Corpus 2 dev (39 PDFs) scored 0.9244 → 0.9244 UZP and 0.8951 → 0.8951 strict. Final macro class F1 was 0.9485, with appeals 0.8977, mandates 0.9836 and transfers 0.9643. 39 outputs matched main byte for byte.

The first integration and the initial freeze scored 0.9244 and 0.9244 UZP, respectively.

Main macro class F1 was 0.9485, with appeals 0.8977, mandates 0.9836 and transfers 0.9643. Starting-main routing was negatywny 11/11, odwolanie 13/13, pelnomocnictwo 5/5, przelew 10/10. Final routing was negatywny 11/11, odwolanie 13/13, pelnomocnictwo 5/5, przelew 10/10.

Largest remaining development field errors by count were przelew_bankowy.tytul (5), Odwolujacy.przez-pelnomocnika (5), Odwolujacy.pelnomocnik.imie_nazwisko (5), ZamowieniePubliczne.tytul (5), Odwolujacy.pelnomocnik.nazwa (4), OdwolanieKIO.czynnosc_dzien (4).

### Release gates

The first training run on 19c9fcf was exact for 192/196 and scored 0.995 UZP. Two permitted organizer examples showed that a quoted definition of the grantor role could suppress a sole trader and that an explicitly introduced firm name could span a line break. After those structures were corrected, all 196 training outputs matched. The mixed organizer run then exposed a conflicting OCR spelling of a proprietor inside the printed business name. The final change abstains on that disputed field when the name is supported only by OCR and has no matching native corroboration. An isolated organizer scan and invented controls reproduced the issue. The final case rerun followed this correction.

The clean printed-prefix organizer run scored 1.0000 UZP and 1.0000 strict, with 196/196 exact. Byte-for-byte comparison with the starting-main output matched all 196 files. The 30 organizer scans scored 1.0000 UZP and 0.9974 strict, with 29/30 exact. The mixed 150-PDF CLI processed 120 native documents and those 30 scans in 528.8 seconds on the shared Mac with two workers.

The fixed 240-PDF variants scored 0.9090 UZP and 0.8689 strict. The separate, once-only corpus 1 test, run on freeze `47ec6e4` before the organizer OCR correction, scored 0.9203 UZP and 0.9023 strict, with 7/17 exact.

The stored variants reference is 0.9125 UZP and 0.8743 strict. Starting main re-run on the same shared host scored 0.9105 and 0.8712. Two earlier candidate runs scored 0.9110 and 0.9105 UZP. The frozen run differed from the stored reference on Odwolujacy[].nip, przelew_bankowy.na_rachunek, przelew_bankowy.z_rachunku.

Latest upstream main (`c6858e8`) scored 0.9102 UZP and 0.8707 strict. The overlapping candidate recheck scored 0.9102 and 0.8707. The two runs differed on przelew_bankowy.na_rachunek, przelew_bankowy.z_rachunku. The candidate recheck fell below the stored gate.

The keyed sample comprises one fact record per development family, each rendered natively and as a scan. All real development PDFs used the local keyless profile.

On the fixed public development sample using EU Ministral 3B, odwolanie scored 0.7636 → 1.0000 UZP and 0.7045 → 1.0000 strict across 2 PDFs.

On the fixed public development sample using EU Ministral 3B, pelnomocnictwo scored 0.9139 → 1.0000 UZP and 0.9252 → 1.0000 strict across 12 PDFs.


### Reproduction

The case runner used its default 26-case seed on starting main `a84258d` and the final product `8fdb0c5`. The final public dataset SHA-256 is `9a0290871b89fa10c691c4e6f84d84764bb0929bd72ac4be6419782a8bf0f1aa`. Both the per-field counts and the class metrics use predictions from the normal two-worker keyless CLI.

```sh
make eval-cases
make eval-variants
uv run python -m evals.run --correct-training-accounts
```
