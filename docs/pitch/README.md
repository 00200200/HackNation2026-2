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

Slides reference images by paths relative to `index.html`; slide 8 shows `../gui/appeal.png`.

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
| 2 (notes), 7 (notes), 10 | 5986 appeals and 5881 accessions filed with KIO in 2025 | *Informacja o działalności Krajowej Izby Odwoławczej za 2025 r.*, UZP, published 26.06.2026, [gov.pl](https://www.gov.pl/web/uzp/informacja-roczna-z-dzialalnosci-krajowej-izby-odwolawczej-za-2025-r) |
| 6, 9 | Rules-only UZP-style / strict micro F1 at `2c00fbb`: 196 organizer training PDFs, printed-prefix references, 1.0000 / 1.0000. Thirty organizer scans, 1.0000 / 0.9974, 30/30 routed and 29/30 whole JSONs exact. Local corpus 1 all (39 PDFs), 0.9247 / 0.8921. Local corpus 2 dev (39 PDFs), 0.9244 / 0.8951. Routing across both was 78/78 including 22 unrelated PDFs. On 240 generated layout variants the keyless score was 0.9125 / 0.8743. The project pools fields across documents and uses normalized Levenshtein at 0.80 for five long fields. UZP has not confirmed the aggregation or similarity function. | [Integrated results, `stages.final`](../../evals/results/variant-robustness.json), [variant counts](../../evals/results/variants.json), [scoring rules](../task/BRIEF.md#judging), [negative counts](../../evals/results/round2-integration.json) |
| 6 (notes) | An earlier comparison at `55dc2a1` scored training at 0.9758 with the published references and 1.0000 with references matching the printed account prefix. The published references omit the printed `PL` in 48 transfers. | [Printed-prefix comparison, `integration`](../../evals/results/p0-conventions.json) |
| 6 (notes) | An earlier run on `f7f3ee9` routed 29/30 scans (0.9869 UZP); one scan batch needed an isolated OCR timeout retry | `evals/results/uzp-metric.json`, `WORKLOG.md` "Last eval" |
| 6 | The reported datasets were used during development. The hidden-set score is unknown | `README.md` (results sections), `WORKLOG.md` "Last eval" |
| 5 | OCR limits: 180 s per page with one retry at 150 dpi, up to 300 s of optional rereads per document, a shared batch cutoff | `kio2json/pdf_text.py`, `kio2json/ocr_budget.py` |
| 7, 8 | `examples/classes/accession.toml` turns the invented `zgloszenie_przystapienia.pdf` into the JSON shown; without `--classes` the notice gets no fields; dropping the file into a `--classes` folder applies on the next analysis in the viewer | CLI and browser checked on main `a7dce92`; [demo and expected JSON](demo.md), [class file](../../examples/classes/accession.toml), [viewer reload](../../kio2json/gui.py) |
| 9 | Ministral 3B added 0.0087 and 0.0131 strict micro F1 on the real development sets in round 2 | `evals/results/round2-integration.json` |
| 5 (notes), 10 | A two-worker keyless CLI run on a shared Apple M1 took 299.76 s for 120 native PDFs and 30 organizer scans. The time on the 2-vCPU jury VM remains unverified. | [Mixed batch at `aa49e8c`, `runtime`](../../evals/results/appeal-party-headings.json), [VM rehearsal status](../../evals/results/vm-2vcpu.json) |
| 10 | UZP's limit of 45 minutes for the 150 test PDFs; the evaluation VM has 2 vCPU (notes) | `data/uzp/README.md`, "Maksymalny czas przetwarzania"; `data/uzp/VM.md`, CPU / RAM row |
| 9, 10 | `--explain` gives the page and a text snippet where a value occurs in the text and says so when the value is not there verbatim, for example a name converted to the nominative or a derived code | [Field trace](../../kio2json/trace.py), CLI check on the invented accession on main `a7dce92` |
| 11 | Components and licenses, including Leptonica and the image libraries bundled in the tesserocr wheel, the PP-OCRv6 models bundled with RapidOCR and the Mistral AI API used by the optional profile | Package metadata of the pinned `requirements.txt`; `rapidocr-*.dist-info/licenses/MODEL_LICENSES.md` (Apache-2.0); `kio2json/tessdata/LICENSE`; `frontend/public/fonts/LICENSE-Geist.txt`; [Morfeusz 2 licence](http://morfeusz.sgjp.pl/doc/license/en) (BSD-2-Clause for the program and its data); `docs/small-model-providers.md` for Ministral 3B; Regulamin § 4 ust. 1 |
| 9 | Stage II is 50% F1 and 50% flexibility, judged on the architecture description, code and presentation; the hidden set has at least 10 appeal cases | `docs/task/regulamin.pdf`, § 2 ust. 4 |
| 9 | 1–20 points for model size (smaller scores more, rules under revision), 1–20 for new classes, 1–10 for other features. The rules-only score has no confirmed point allocation | `data/uzp/README.md`, section 7 |

## Before presenting

- Rehearse the [two-minute demo](demo.md) on the release being presented. The class example, `--classes` and
  `--explain` are on main via #95.
- Slides 6 and 9 cite the measured extractor revisions above. Update the numbers and their source together after
  a comparable release run.
- Once #66 has run the solution on the evaluation VM, add it to slide 10 (native Python 3.13 from the VM kit or the
  Compose fallback, 2 vCPU, no GPU, no LLM) with the time measured there. The Ubuntu 2-vCPU rehearsal is still
  unverified (`evals/results/vm-2vcpu.json`).
- Slide 12: verify the jury’s access to the GitHub repository (#48). The QR code
  leads to https://doc2json.pl.
