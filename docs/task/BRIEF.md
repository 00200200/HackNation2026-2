# Odwołania2json: task brief

Task of HackNation 2026 set by Urząd Zamówień Publicznych (UZP). Main prize: 20 000 zł.

Sources (read 21.11.2026):
- Task details PDF: `docs/task/odwolania2json-szczegoly.pdf` (from hacknation.pl/zadania).
- FAQ v1.0: `docs/task/FAQ.md` (Polish original, pasted by the team).
- Organizer repo: https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026, copied into `data/uzp` (without
  `.git`; source commit in `data/uzp/UPSTREAM`). The organizer was still committing on 21.11.2026: `make data`
  refreshes the copy, then review `git diff data/uzp` (gold fixes change the eval) and commit it.
- Template example `szablon-aplikacja/input/case1` (one appeal, one negative) is also in our `input/case1`.

Where the sources disagree, the organizer repo README is the most detailed and most recent; this is noted per item.

## What to build

A Python app that takes the PDFs of a KIO appeal case, classifies each PDF by **content** (file names vary; do
not use them), extracts the fields for its class and writes one JSON per PDF.

Classes and schemas (`data/uzp/oczekiwane-json/`):

| Class | Schema | Key fields |
|---|---|---|
| appeal (odwołanie do KIO) | `odwolanie.json` | `OdwolanieKIO` (date, place, challenged action date, `czynnosc_powod_id` 1–12 + canonical `czynnosc_opis`, both from the **first** charge only), `Odwolujacy[]` (KRS/NIP/REGON, consortium leader, `przez-pelnomocnika`, attorney name, firm, e-mail), `Zamawiajacy[]` (+ `prowadzacy_postepowanie` null/0/1), `ZamowieniePubliczne` (BZP no. `YYYY/BZP########`, internal no., TED no. `NNNNNN-YYYY`, title) |
| power of attorney (pełnomocnictwo) | `pelnomocnictwo.json` | `mocodawca[]` (`data`: name/KRS/NIP/`typ` osoba_prawna/osoba_fizyczna, `podpisujacy[]`), `pelnomocnicy[]` (name in nominative, PESEL) |
| transfer confirmation (potwierdzenie przelewu) | `przelew.json` | `przelew_bankowy`: `data_operacji`, `kwota`, `na_rachunek`, `z_rachunku`, `numer_transakcji`, `tytul` |
| anything else (negative) | — | `{}`, no class |

`czynnosc_powod_id` dictionary: `data/uzp/oczekiwane-json/czynnosc_powod_id_dict.md`. The schema files contain
`//` comments with the extraction rules for each field; treat them as the spec.

Missing information: never invent it; use `null` where the schema allows (FAQ 6).

## Input and output contract (organizer README, section 3)

- `input/` and `output/` folders in the app root. The jury drops cases into `input/<case>/*.pdf`.
- Output: `output/<case>/<same file name>.json`, one per input PDF, same tree. Unrelated documents produce `{}`. The implementation also writes `{}` when it cannot process a PDF. [UZP clarification](https://github.com/00200200/HackNation2026-2/issues/57)
- Transfer account numbers keep the printed country code, if present, and omit all whitespace. UZP confirmed that missing prefixes in the training references are labelling errors. [UZP clarification](https://github.com/00200200/HackNation2026-2/issues/58)
- A CLI with instructions is **required** (FAQ 12a); a wrapper script (e.g. `start.bat`) is fine.
- GUI is optional and scores extra: upload PDF, run, see JSON, ideally side by side with the source (FAQ 12b).

## Technical requirements

- **Python 3.13+** and a `requirements.txt` installable with `pip install` (README; not in the PDF).
- Open-source components only, including open-weight LLMs (FAQ 11, PDF section 5).
- Test machine: office laptop, 16 GB RAM, Intel i7, **no GPU**. LLM by API is expected; the submission must ship
  with the API key. The model must also be installable locally, and the API provider and server must be **in the
  EU/EEA** (README section 6, FAQ 11).
- Both text PDFs and scans that need OCR occur (FAQ 7).
- Bonus: new document classes and fields through configuration files only, no code change; transparent extraction.

## Data

- `data/uzp/dane/przyklad_01` … `przyklad_60`: synthetic cases, each `odwolanie.pdf`, `pelnomocnictwo.pdf`,
  `potwierdzenie_przelewu.pdf` with gold `odwolanie.json`, `pelnomocnictwo.json`, `przelew.json`.
  (FAQ says "at least 39"; 60 in the repo on 21.11.2026.)
- Negatives: 12 PDFs in `data/uzp/dane/negatywne/`, and one extra PDF each in `przyklad_04`, `_10`, `_24`, `_37`.
- `data/uzp/szablon-aplikacja/`: the expected folder layout (`input/case1`, `output/case1`).
- Hidden test set: real cases prepared by UZP experts. The UZP stand can show it (FAQ 9).

## Judging

| Stage | Criterion | Weight |
|---|---|---|
| I (preselection) | Extraction quality, F1 on the hidden test set | 100% |
| II (final) | Extraction quality, F1 | 50% |
| II | Flexibility and extensibility | 50% (README) / 30% (PDF) |
| II | Architecture and technical quality | — (README) / 20% (PDF) |

README breakdown of the 50% flexibility part: 1–20 pts for LLM size (**smaller model scores more**: balance
extraction quality against cost), 1–20 pts for adding new document types and data classes without rebuilding,
1–10 pts for other features (e.g. GUI). The PDF and FAQ instead give 30% flexibility + 20% architecture
(modularity, maintenance, documentation). UNCONFIRMED which split the jury uses; plan for both.

How F1 is computed (field matching, normalisation, lists, negatives) is **not published**. UNCONFIRMED; ask at the
UZP stand. Our working definition is in `.claude/skills/odwolania2json-eval/SKILL.md`.

## Deliverables

- Required: project title, GitHub link to a working prototype (upload documents, read the extraction result).
- Optional: technical documentation incl. the LLM used, own quality test results.
- Not required: a full KIO case-management system (FAQ 14).
