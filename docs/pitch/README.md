# doc2json pitch (HackNation 2026 final)

Eleven slides in Polish for the UZP jury, black and white, set in Geist and Geist Mono. The slides
and the demo script are in Polish because the jury and the presenters speak Polish.

| File | What it is |
|---|---|
| `doc2json-pitch.pdf` | PDF export, 11 pages at 1920×1080 |
| `index.html` | All slides on one page, built by `build.py`. Open it in a browser. Fonts come from `frontend/public/fonts/` |
| `project/deck.json`, `project/deck.css`, `project/slides/*.html` | Slide sources in the claude.ai Slides format. Speaker notes are in each `<aside>` |
| `build.py` | Assembles `index.html` from the slide order in `deck.json` |
| `demo.md` | Two-minute live demo script with the commands, checked on `main` on 22.11.2026 |
| `demo/karta-uczestnika.pdf` | Invented form for the fourth-class demo, printed from `demo/karta-uczestnika.html` |

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
| 2 (notes), 10 | 5986 appeals and 5881 accessions filed with KIO in 2025 | *Informacja o działalności Krajowej Izby Odwoławczej za 2025 r.*, UZP, published 26.06.2026, [gov.pl](https://www.gov.pl/web/uzp/informacja-roczna-z-dzialalnosci-krajowej-izby-odwolawczej-za-2025-r) |
| 6, 9 | F1 under the UZP formula of #59 (main `6ff2966`, local rules, two workers; #74 kept every default output byte for byte): 1.000 on 196 synthetic training PDFs, 1.000 on the 30 organizer scans (29/30 exact), 0.9231 and 0.9244 on the two real development sets (0.92 for both); strict F1 on the same predictions 1.000, 0.9974, 0.8900 and 0.8951. UZP has not confirmed its similarity function; the scorer uses normalized Levenshtein at 0.80 | `evals/results/case-siblings.json`, `WORKLOG.md` Log 22.11 (#61) |
| 6 (notes) | An earlier run on `f7f3ee9` misrouted one transfer scan: scans 0.9869 UZP, 0.9740 strict | `evals/results/uzp-metric.json` |
| 6 (notes) | Round 3: strict F1 0.9974 on the 30 scans with all 30 routed, routing 78/78 on the real development sets including 22 unrelated PDFs | `evals/results/round3.json` (`steps.verified`) |
| 6 | All three sets are development data, so none predicts the hidden-set score | `README.md` (results sections), `WORKLOG.md` "Last eval" |
| 9 | Ministral 3B added 0.0087 and 0.0131 micro F1 on the real development sets in round 2 | `evals/results/round2-integration.json` |
| 5 (notes), 10 | 150 PDFs in 83 s with four workers | `evals/results/round3.json` (`timing`); that entry does not record the machine |
| 10 | 150 PDFs in 402 s with one worker under eight CPU busy loops, Apple M1 with 16 GB | `evals/results/adaptive-ocr-budget.json` (`runs`, profile `loaded-serial`) |
| 5 | Open-source components named on the slide, as the Regulamin requires for external solutions | `pyproject.toml`, `uv.lock`, the imports in `kio2json/`, `compose.yaml`, `packaging/polish_ocr_data/`, `frontend/public/fonts/`; `docs/task/regulamin.pdf`, § 4 ust. 1 |
| 7, 8 | The fourth class turns an invented form into the JSON shown, with no code change and no GUI restart | Run on `main` on 22.11.2026, steps in `demo.md` |
| 9 | Stage II is 50% F1 and 50% flexibility, judged on the architecture description, code and presentation; the hidden set has at least 10 appeal cases | `docs/task/regulamin.pdf`, § 2 ust. 4 |
| 9 | Up to 20 points for model size (a smaller model scores more, rules under revision), up to 20 for new classes, up to 10 for other features | `data/uzp/README.md`, section 7 |
| 10 | About 900 hours per year if every PDF were retyped by hand | Estimate, not a measurement: 5986 appeals × 3 PDFs × 3 minutes per PDF |

Not on the slides because no written source exists: a second-hand relay in issue #64 says that without an
LLM the model-size criterion gets the maximum score ("Tak, dokładnie", 13:51; no author or original question
recorded). The same table says the hidden set is synthetic. Both stay UNCONFIRMED until someone with Discord
access records the original messages.

## Open items

- Slides 6 and 9 use the UZP-formula F1 measured on main `6ff2966`. Re-measure on the final commit before the
  final and update both slides if the numbers move.
- Slides 3 and 5 say "pusty wynik" for unrelated documents. That is true both for today's empty file and
  for the `{}` that #57 introduces; the demo shows whichever is on `main`.
- Slide 10 names per-field evidence as the next step: #40 is not on `main`.
- Once #66 deploys the solution on the evaluation VM, add it to slide 10 (Docker, 2 vCPU, no GPU, no LLM)
  with the measured 150-PDF time there, and the GUI address on the VM if one is served.
- Slide 11: the GitHub link works for the jury only after the team grants access (#48). The QR code
  leads to https://doc2json.pl.
