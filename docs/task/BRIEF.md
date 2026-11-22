# Odwołania2json: task brief

Task of HackNation 2026 set by Urząd Zamówień Publicznych (UZP). One main prize: 20 000 zł gross.

Sources (read 21 and 22.11.2026):
- Regulamin Zadania Konkursowego: [`docs/task/regulamin.pdf`](regulamin.pdf) (5 pages, signed electronically between
  12 and 18.11.2026; "Regulamin" below). It sets the judging stages and the prize conditions.
- UZP's answers on the HackNation Discord on 21 and 22.11.2026 ("Discord" below). No transcript is in the repo. The
  team copied them into issues #57, #58, #59, #62, #63 and #64, which record the times and quote or paraphrase them.
- Task details PDF: `docs/task/odwolania2json-szczegoly.pdf` (from hacknation.pl/zadania).
- FAQ v1.0: `docs/task/FAQ.md` (Polish original, pasted by the team).
- Organizer repo: https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026, copied into `data/uzp` (without
  `.git`; source commit in `data/uzp/UPSTREAM`). The copy was refreshed on 22.11.2026 to upstream commit `eadffbc`,
  which adds `VM.md` (commits `a44e3cb` and `eadffbc`, 21.11.2026 23:38 UTC). Nothing else changed since `0b360a9`:
  README, schemas, training data and gold JSONs are the same. The organizer is still committing: `make data`
  refreshes the copy, then review `git diff data/uzp` (gold fixes change the eval) and commit it.
- Template example `szablon-aplikacja/input/case1` (one appeal, one negative) is also in our `input/case1`.

The signed Regulamin decides judging and the prize. Its § 5.2 only ranks it above the general HackNation Regulamin;
how it ranks against the README, the FAQ and the task PDF is our reading, not a UZP statement. For everything else we
follow the most recent organizer statement and read the Discord answers as clarifications of the README; the FAQ and
the task PDF are the oldest. UZP has not stated that order. This is noted per item. Where the order cannot be told, for
example a Discord answer with no recorded time against `VM.md`, the item stays UNCONFIRMED.

## What to build

A Python app that takes the PDFs of a KIO appeal case, classifies each PDF by **content** (file names vary; do
not use them), extracts the fields for its class and writes one JSON per PDF.

Classes and schemas (`data/uzp/oczekiwane-json/`):

| Class | Schema | Key fields |
|---|---|---|
| appeal (odwołanie do KIO) | `odwolanie.json` | `OdwolanieKIO` (date, place, challenged action date, `czynnosc_powod_id` 1–12 + canonical `czynnosc_opis`, both from the **first** charge only), `Odwolujacy[]` (KRS/NIP/REGON, consortium leader, `przez-pelnomocnika`, attorney name, firm, e-mail), `Zamawiajacy[]` (+ `prowadzacy_postepowanie` null/0/1), `ZamowieniePubliczne` (BZP no. `YYYY/BZP########`, internal no., TED no. `NNNNNN-YYYY`, title) |
| power of attorney (pełnomocnictwo) | `pelnomocnictwo.json` | `mocodawca[]` (`data`: name/KRS/NIP/`typ` osoba_prawna/osoba_fizyczna, `podpisujacy[]`), `pelnomocnicy[]` (name in nominative, PESEL) |
| transfer confirmation (potwierdzenie przelewu) | `przelew.json` | `przelew_bankowy`: `data_operacji`, `kwota`, `na_rachunek`, `z_rachunku`, `numer_transakcji`, `tytul` |
| anything else (negative) | none | a JSON file containing only `{}`, no class (Discord, #57; the README says "empty `.json` file") |

`czynnosc_powod_id` dictionary: `data/uzp/oczekiwane-json/czynnosc_powod_id_dict.md`. The schema files contain
`//` comments with the extraction rules for each field; treat them as the spec.

Missing information: never invent it; use `null` where the schema allows (FAQ 6).

Value conventions (Discord):
- Personal names in the nominative: "Jan Kowalski", not "Jana Kowalskiego".
- The grantor's (`mocodawca`) company name exactly as printed in the document, even when it differs from CEIDG.
- Account numbers as printed in the document: keep the country code when one is printed (`PL` or another country's
  code) and remove all whitespace. The CLI preserves the printed prefix. [Account convention](https://github.com/00200200/HackNation2026-2/issues/58)

## Input and output contract (organizer README, section 3)

- `input/` and `output/` folders in the app root. The jury drops cases into `input/<case>/*.pdf`.
- Output: `output/<case>/<input stem>.json`, one per input PDF, same tree (README, "Wynik działania"). The Discord
  answer in #64 gives the example `potwierdzenie_przelewu.pdf` → `potwierdzenie_przelewu.json`.
- Negatives: the README says "empty `.json` file". UZP clarified on Discord that the file must contain only `{}`,
  not zero bytes (#57).
- A CLI with instructions is **required** (FAQ 12a); a wrapper script (e.g. `start.bat`) is fine.
- GUI is optional and scores extra: upload PDF, run, see JSON, ideally side by side with the source (FAQ 12b).

## Technical requirements

- **Python 3.13+** and a `requirements.txt` installable with `pip install` (README; not in the PDF). The organizer VM
  ships Python 3.12 and `VM.md` lets teams install what they need, so 3.13 has to be installed there or run in a
  container.
- Open-source components only, including open-weight LLMs (FAQ 11, PDF section 5).
- Test machine and delivery. README section 6 says only "we have to change the planned evaluation method, stay
  tuned" (about 30 interested teams); the earlier "16 GB RAM, Intel i7" line is gone. Upstream `VM.md` then set the
  method. Each team may request an Azure VM (one request per team, form https://forms.cloud.microsoft/e/HRFJjEcqMF):
  Ubuntu 24.04 LTS, 2 vCPU, 16 GB RAM, 64 GB disk, no GPU, internet access, ports 22, 80, 443, 8000 and 8080 open,
  `sudo`, Docker with Compose v2, git and Python 3.12. **Team access is cut on 22.11.2026 at 11:00** and the solution
  is judged as left on the VM; background containers keep running. The evaluators log in, put their secret documents
  into `/opt/solution/input`, run the command from `/opt/solution/RUN.md` in `/opt/solution` with `sudo` (no
  interaction; it must end on its own) and read `/opt/solution/output`. The project and its config belong in
  `/opt/solution`; models, Docker images and dependencies must already be on the VM, because `VM.md` says not to count
  on downloads during the evaluation. Deployment is tracked in #66. UNCONFIRMED: whether a team without a VM is
  evaluated from its GitHub link, whether the 45-minute limit is measured on this VM, and the format of `RUN.md`
  (`VM.md` points to a template that the file does not contain). FAQ 11 still calls the test machine an "office"
  computer without GPU.
- The solution must run locally (on-premise) without GPU. A solution that uses an LLM calls it through an API (README
  section 5); a rules-only solution needs no API. `VM.md` names a container with a model as an example of a
  background service on the VM.
- An LLM is optional. When a solution uses one (README section 6, FAQ 11, Discord):
  - the model is open-source, and FAQ 11 also expects it to be installable locally;
  - it is called through the API of a company whose privacy policy states the scope and place of data processing,
    with servers in the EU/EEA (README). On Discord UZP said EU servers and **no private hosting**. UNCONFIRMED:
    where private hosting ends, for example a team-run VPS versus a company's inference service, and whether a model
    running on the evaluation VM counts;
  - the solution ships with the API key, and the organizers promise to use it only for testing (README). `VM.md`: the
    keys go into `/opt/solution/.env`, and `RUN.md` names the services used. On Discord UZP said the key goes into a
    field of the HackNation submission form, not into the repo. UNCONFIRMED: whether the form field, `.env` or both
    apply (#48). The time of that Discord answer is not recorded, so we cannot tell whether `VM.md` is newer.
- A small local model for named-entity recognition, about 0.2B parameters, is allowed when it runs locally like OCR
  (Discord). UNCONFIRMED: whether it counts toward the LLM-size score.
- OCR by API is allowed, but its parameters are scored like an LLM's (README, "Wyjątki"). Local OCR is not
  affected.
- Limit: the solution is tested on **150 PDF files**; the whole set must finish within **45 minutes** (README,
  "Wyjątki"). On Discord UZP added that each solution gets a fixed time and may not finish, and that API rate limits
  are not scored. UNCONFIRMED: how files left unprocessed at the cutoff count.
- Both text PDFs and scans that need OCR occur (FAQ 7).
- Bonus: new document classes and fields through configuration files only, no code change; transparent extraction.
  On Discord UZP said a new class should be added through a configuration file, and that configurable recognition,
  validation and field-mapping rules will be taken into account.

## Data

- `data/uzp/dane/przyklad_01` … `przyklad_60`: synthetic cases, each `odwolanie.pdf`, `pelnomocnictwo.pdf`, a
  transfer PDF with gold `odwolanie.json`, `pelnomocnictwo.json`, `przelew.json`. The transfer PDF name is mixed:
  `potwierdzenie_przelewu.pdf` in 58 cases, `przelew.pdf` in `przyklad_01` and `_02` (counted 21.11.2026). Names
  must not matter anyway, since classification is by content.
  (FAQ says "at least 39"; 60 in the repo on 21.11.2026.)
- 48 of the 60 training transfers print `PL` before an account number, yet all 60 gold files hold bare digits
  (counted 21.11.2026, #58). UZP called the missing `PL` an error in the references and said the hidden set will not
  repeat it.
- Negatives: 12 PDFs in `data/uzp/dane/negatywne/` (plus a `readme.md`) and one extra PDF each in `przyklad_04`, `_10`,
  `_24`, `_37`: 16 in all.
- `data/uzp/dane/skany/`: 30 labelled scans (10 each in `odwolania`, `pelnomocnictwa`, `potwierdzenia`, one
  folder per scan with `NNNN.pdf` and gold `NNNN.json`). The README does not describe them; the folder is in the
  repo only.
- `data/uzp/szablon-aplikacja/`: the expected folder layout (`input/case1`, `output/case1`). Its `output/case1`
  holds only `przyklad odwolanie.json`: the template has no output file for its `negatywny przyklad.pdf`, so it
  does not show the `{}` convention.
- Hidden test set: not published. The task PDF (section 6) says it contains real appeal cases prepared by the
  organizer, and README section 6 calls it complete cases, scored against references written by subject experts. The
  #63 relay of UZP's Discord answers (two Discord speakers, roles not recorded) says the documents are **synthetic, generated
  from real cases**, include both text PDFs and scans, and contain no PDF that merges a document with an attachment;
  we follow that later answer. Regulamin § 2.4a: at least
  10 appeal cases. The UZP stand can show it (FAQ 9).

## Judging

Source: Regulamin § 2.4 to 2.6, which takes precedence over the general HackNation Regulamin (§ 5.2).

| Stage | Criterion | Weight |
|---|---|---|
| I (preselection) | Extraction quality, F1 on the hidden test set (at least 10 appeal cases) | 100% |
| II (final) | Extraction quality, F1 | 50% |
| II | Flexibility and ease of adding new document classes | 50% |

At most three teams, the best of Stage I, present in the final. The jury judges the flexibility part from the
architecture description, the source code and the team's presentation, then picks the winner. Its decisions are final.

FAQ 10 and the README give the same 50/50 split. Only the task PDF divides the non-F1 half into 30% flexibility and
20% architecture and technical quality. The Regulamin has no separate architecture criterion: the architecture
description is evidence for the flexibility criterion. Our reading is that the PDF split is superseded.
UNCONFIRMED that UZP withdrew it.

README breakdown of the flexibility part: 1-20 pts for LLM size (**smaller model scores more**: balance
extraction quality against cost), 1-20 pts for adding new document types and data classes without rebuilding,
1-10 pts for other features (e.g. GUI). The #64 relay of UZP's Discord answers says a solution **without an LLM gets
the maximum LLM-size score** (the answer "Tak, dokładnie" at 13:51; the question and the speaker are not recorded, and
no organizer document says it), so we treat it as UNCONFIRMED. For solutions that use an LLM the rule is **under
revision**: the README ("Sposób punktacji LLM")
says the organizers are working on new guidelines after discussion with participants and reports of possible
manipulation, "stay tuned". UNCONFIRMED: the new rule, and how these three parts fit into the Regulamin's single
50% flexibility criterion, which names only new document classes.

How F1 is computed: neither the README nor the Regulamin (§ 2.4a: F1 against the real data on the documents) says.
UZP described it on Discord:
- TP: the value is in our JSON and matches the reference. Five long-string fields match at **80% similarity**: the
  attorney's firm name (`Odwolujacy[].pelnomocnik.nazwa`), the transfer title (`przelew_bankowy.tytul`), the
  appellant's name (`Odwolujacy[].nazwa`), the contracting authority's name (`Zamawiajacy[].nazwa`) and the
  procurement title (`ZamowieniePubliczne.tytul`).
- TN: the value is absent from both. TN does not enter F1.
- FP: the value is only in our JSON, or it is in both but wrong.
- FN: the value is absent from our JSON but present in the reference.
- Lists are matched by content, not by position.

Our reading of the FP and FN rules together: a wrong value counts as one FP and no FN. The scorer (PR #71, #59) relies
on it; UZP did not state it in so many words.

UNCONFIRMED: the similarity measure behind the 80% rule (RapidFuzz normalised Levenshtein is our stand-in), and how
the counts are aggregated across fields, documents and classes. Our scorer implements the rules above as pooled micro
F1 and keeps the older strict score for comparison; its definition is in `.claude/skills/odwolania2json-eval/SKILL.md`.

## Deliverables

- Required: project title, GitHub link to a working prototype (upload documents, read the extraction result).
- Optional: technical documentation incl. the LLM used, own quality test results.
- Delivery for evaluation (`VM.md`): the project in `/opt/solution` on the team VM, with `RUN.md`, `input/` and
  `output/`, ready before 22.11.2026 at 11:00 (#66).
- API key of an LLM solution: `/opt/solution/.env` (`VM.md`) or a field of the HackNation submission form, not the repo
  (Discord). UNCONFIRMED which applies.
- Finalists (at most three): an architecture description, the source code and a presentation (Regulamin § 2.4b).
  The presentation has to say which external solutions were used (§ 4.1).
- Prize payout, winners only (Regulamin § 3.5): paid within 7 days of signing the copyright transfer agreement and
  handing over the source code, the run instructions, the Docker Compose configuration and the documentation. The
  documentation covers the architecture, the extraction configuration of a document class and how to add a new class.
- Copyright transfer (Regulamin § 3.9, § 4): all co-authors sign it in writing, and a winner who does not sign within
  7 days of receiving it loses the prize. The template (Załącznik nr 1) is not in our files; UNCONFIRMED what it requires.
- Not required: a full KIO case-management system (FAQ 14).
