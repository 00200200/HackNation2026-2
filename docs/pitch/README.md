# doc2json pitch (HackNation 2026 final)

Twelve slides in Polish for the UZP jury, black and white, set in Geist and Geist Mono. The slides
and the demo script are in Polish because the jury and the presenters speak Polish.

| File | What it is |
|---|---|
| `doc2json-pitch.pdf` | PDF export, 12 pages at 1920×1080 |
| `index.html` | All slides on one page, built by `build.py`. Open it in a browser. Fonts come from `frontend/public/fonts/` |
| `project/deck.json`, `project/deck.css`, `project/slides/*.html` | Slide sources in the claude.ai Slides format. Speaker notes are in each `<aside>` |
| `build.py` | Assembles `index.html` from the slide order in `deck.json` |
| `demo.md` | Two-minute live demo script with the commands; what was checked where is at the top |
| `demo/karta-uczestnika.pdf` | Additional invented form for `participation.toml`, printed from `demo/karta-uczestnika.html` |

Slides reference images by paths relative to `index.html`; slide 9 shows `../readme/web.png`.

## Rebuild

After editing a slide, rebuild the page and the PDF from the repository root (macOS path to Chrome
shown; on Linux use `google-chrome`):

```sh
python docs/pitch/build.py
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer \
  --print-to-pdf="$PWD/docs/pitch/doc2json-pitch.pdf" "file://$PWD/docs/pitch/index.html"
```

`@page` in `index.html` sets the page size, and print mode turns off the entry animations.

## Sources of the numbers and claims

| Slide | Claim | Source |
|---|---|---|
| 2 (notes), 8 (notes), 10 | 5986 appeals and 5881 accessions filed with KIO in 2025 | *Informacja o działalności Krajowej Izby Odwoławczej za 2025 r.*, UZP, published 26.06.2026, [gov.pl](https://www.gov.pl/web/uzp/informacja-roczna-z-dzialalnosci-krajowej-izby-odwolawczej-za-2025-r) |
| 6 | Rules-only UZP-style / strict micro F1 at `725765b`: 196 organizer training PDFs, printed-prefix references, 1.0000 / 1.0000. Thirty organizer scans, 1.0000 / 0.9974, 29/30 whole JSONs exact. Local corpus 1 dev (22 PDFs), 0.9286 / 0.8821. Local corpus 2 dev (39 PDFs), 0.9244 / 0.8951; both with every class routed and unrelated PDFs empty. On 240 generated layout variants (60 cases, seed 63059) 0.9512 / 0.9264, with all 180 documents routed and all 60 unrelated documents written as `{}`. Main `b2fd9c6` repeats 1.0000 on training and scans. The project pools fields across documents and uses normalized Levenshtein at 0.80 for five long fields. UZP has not confirmed the aggregation or similarity function. | [Merged-main baseline](../../evals/results/merged-main-725765b.json), [latest gates](../../evals/results/rotation-textlayer.json), [scoring rules](../task/BRIEF.md#judging) |
| 6 (notes) | An earlier comparison at `55dc2a1` scored training at 0.9758 with the published references and 1.0000 with references matching the printed account prefix. The published references omit the printed `PL` in 48 transfers. | [Printed-prefix comparison, `integration`](../../evals/results/p0-conventions.json) |
| 6 (notes) | An earlier run on `f7f3ee9` routed 29/30 scans (0.9869 UZP); one scan batch needed an isolated OCR timeout retry | `evals/results/uzp-metric.json`, `WORKLOG.md` "Last eval" |
| 6 | The reported datasets were used during development. The hidden-set score is unknown | `README.md` (results sections), `WORKLOG.md` "Last eval" |
| 8, 9 | `examples/classes/accession.toml` turns the invented `zgloszenie_przystapienia.pdf` into the JSON shown; without `--classes` the notice gets no fields; dropping the file into a `--classes` folder applies on the next analysis in the viewer | CLI and browser checked on main `a7dce92`; [demo and expected JSON](demo.md), [class file](../../examples/classes/accession.toml), [viewer reload](../../kio2json/gui.py) |
| 10 (notes) | The keyed Ministral 3B profile runs only with a key in `/opt/solution/.env`. On organizer training and scans it sent 0 requests: training files were byte-identical to rules only, and no scan value changed. Before the merge it scored 0.9221 against 0.9256 for rules on corpus 1 dev and replaced one correct reason code with a wrong one | [Jury profile evaluation](../../evals/results/jury-keyed-profile.md) |
| 10 | The `RUN.md` command on a rebooted Ubuntu 24.04.5 guest with 2 vCPU and 5 GiB, run on an Apple M1 through Rosetta, processed 150 organizer example PDFs (120 native, 30 scans) in 412.174 s: UZP F1 1.000000, 149/150 exact. The guest had 5 GiB against 16 GB on the UZP VM; real development cases run slower (22 PDFs in 393.4 s), so this is not a margin for the hidden set. The UZP evaluation VM itself has not been measured. | [Jury profile evaluation, post-reboot mixed150](../../evals/results/jury-keyed-profile.md) |
| 10 | UZP's limit of 45 minutes for the 150 test PDFs; the evaluation VM has 2 vCPU (notes) | `data/uzp/README.md`, "Maksymalny czas przetwarzania"; `data/uzp/VM.md`, CPU / RAM row |
| 7, 10 | `--explain` gives the page and a text snippet where a value occurs in the text and says so when the value is not there verbatim, for example a name converted to the nominative or a derived code | [Field trace](../../kio2json/trace.py), CLI check on the invented accession on main `a7dce92` |
| 11 | Components and licenses, including Leptonica and the image libraries bundled in the tesserocr wheel, the PP-OCRv6 models bundled with RapidOCR and the Mistral AI API used by the optional profile | Package metadata of the pinned `requirements.txt`; `rapidocr-*.dist-info/licenses/MODEL_LICENSES.md` (Apache-2.0); `kio2json/tessdata/LICENSE`; `frontend/public/fonts/LICENSE-Geist.txt`; [Morfeusz 2 licence](http://morfeusz.sgjp.pl/doc/license/en) (BSD-2-Clause for the program and its data); `docs/small-model-providers.md` for Ministral 3B; Regulamin § 4 ust. 1 |

## Before presenting

- Rehearse the [two-minute demo](demo.md) on the release being presented. The class example, `--classes` and
  `--explain` are on main via #95.
- Slide 6 cites the measured extractor revisions above. Update the numbers and their source together after
  a comparable release run.
- Slide 10 cites the post-reboot 2-vCPU guest rehearsal. Once #66 has run the solution on the UZP evaluation VM,
  replace it with the time measured there.
- Slide 12: verify the jury’s access to the GitHub repository (#48). The QR code
  leads to https://doc2json.pl.
