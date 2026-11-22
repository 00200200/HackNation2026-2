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
| `demo/karta-uczestnika.pdf` | Invented form for the fallback demo with `participation.toml`, printed from `demo/karta-uczestnika.html` |

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
| 6, 9 | F1 under the UZP formula of #59 on main after #57 and #58 (product `55dc2a1`; local rules, two workers): 1.000 on the 196 training PDFs with references corrected to the printed account form and 0.9758 against the published references (48 transfers lack the printed `PL`); 1.000 on the 30 organizer scans with strict 0.9974 and 30/30 routed; 0.9212 and 0.9244 on the two real development sets, strict 0.8880 and 0.8951, 78/78 routed including 22 unrelated PDFs. `final_verification` (`97dc53e` over main `328f705`) re-checked training and scans only. UZP has not confirmed its similarity function; the scorer uses normalized Levenshtein at 0.80 | `evals/results/p0-conventions.json` (`integration`, `final_verification`), `WORKLOG.md` "Last eval" |
| 6 (notes) | An earlier run on `f7f3ee9` routed 29/30 scans (0.9869 UZP); one scan batch needed an isolated OCR timeout retry | `evals/results/uzp-metric.json`, `WORKLOG.md` "Last eval" |
| 6 | All three sets are development data, so none predicts the hidden-set score | `README.md` (results sections), `WORKLOG.md` "Last eval" |
| 5 | OCR limits: 180 s per page with one retry at 150 dpi, up to 300 s of optional rereads per document, a shared batch cutoff | `kio2json/pdf_text.py`, `kio2json/ocr_budget.py` |
| 7, 8 | `examples/classes/accession.toml` turns the invented `zgloszenie_przystapienia.pdf` into the JSON shown; without `--classes` the notice gets no fields; dropping the file into a `--classes` folder applies on the next analysis in the viewer | Run on the #76 branch (`461a269`, rerun on `718a2aa` with the same JSON) on 22.11.2026, steps in `demo.md` |
| 9 | Ministral 3B added 0.0087 and 0.0131 micro F1 on the real development sets in round 2 | `evals/results/round2-integration.json` |
| 9 (notes only) | Without an LLM the model-size criterion gets the maximum score | Second-hand: UZP's Discord answer "Tak, dokładnie" (13:51) as recorded in issue #64; the original message, its author and the question are not archived. The slide says only that the default uses 0 LLM parameters |
| 5 (notes), 10 | About 0.7 s per PDF with two workers: all 226 organizer PDFs in 160.75 s on the shared Apple M1, no added load | `evals/results/first-pass-watchdog.json` (`public_batch.watchdog`, the #79 change) |
| 10 | UZP's limit of 45 minutes for the 150 test PDFs; the evaluation VM has 2 vCPU (notes) | `data/uzp/README.md`, "Maksymalny czas przetwarzania"; `data/uzp/VM.md`, CPU / RAM row |
| 9, 10 | `--explain` gives the page and line where a value occurs in the text and says so when the value is not there verbatim, for example a name converted to the nominative or a derived code | `kio2json/trace.py` on #76; run on the #76 branch on 22.11.2026 over four organizer documents |
| 11 | Components and licenses, including Leptonica and the image libraries bundled in the tesserocr wheel, the PP-OCRv6 models bundled with RapidOCR and the Mistral AI API used by the optional profile | Package metadata of the pinned `requirements.txt`; `rapidocr-*.dist-info/licenses/MODEL_LICENSES.md` (Apache-2.0); `kio2json/tessdata/LICENSE`; `frontend/public/fonts/LICENSE-Geist.txt`; [Morfeusz 2 licence](http://morfeusz.sgjp.pl/doc/license/en) (BSD-2-Clause for the program and its data); `docs/small-model-providers.md` for Ministral 3B; Regulamin § 4 ust. 1 |
| 9 | Stage II is 50% F1 and 50% flexibility, judged on the architecture description, code and presentation; the hidden set has at least 10 appeal cases | `docs/task/regulamin.pdf`, § 2 ust. 4 |
| 9 | Up to 20 points for model size (a smaller model scores more, rules under revision), up to 20 for new classes, up to 10 for other features | `data/uzp/README.md`, section 7 |

## Open items

- Slides 7, 8 (step 3), 9 (rows 3 and 5) and 10 (points 03 and 04 and the notes) describe #76. Merge #76
  before the final and run `demo.md` once on `main`. If #76 does not merge, follow the fallback section of
  `demo.md`, which lists the setup, the spoken lines and the slides to change.
- Slides 6 and 9 use the UZP-formula F1 measured after #57 and #58. Re-measure on the final commit before the
  final and update both slides if the numbers move.
- Once #66 has run the solution on the evaluation VM, add it to slide 10 (native Python 3.13 from the VM kit or the
  Compose fallback, 2 vCPU, no GPU, no LLM) with the time measured there. The Ubuntu 2-vCPU rehearsal is still
  unverified (`evals/results/vm-2vcpu.json`).
- Slide 12: the GitHub link works for the jury only after the team grants access (#48). The QR code
  leads to https://doc2json.pl.
