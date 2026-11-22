---
name: hacknation-judging
description: "How HackNation 2026 judges the Odwołania2json (UZP) task, and the pre-push compliance check. Use before every git push, before submitting, when planning scope, or when asking 'would the jury accept this?'. The pre-push git hook refuses a push until the judge agent has passed the commit being pushed."
---

# HackNation 2026 judging: Odwołania2json (UZP)

Sources (read 21.11.2026): task details PDF `docs/task/odwolania2json-szczegoly.pdf`, FAQ v1.0 `docs/task/FAQ.md`,
organizer README `data/uzp/README.md` (https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026), summary
`docs/task/BRIEF.md`. Submission window: 21.11.2026 11:00 – **22.11.2026 11:00** (HackNation 2026 general rules).

## How the jury decides

- **Stage I (preselection):** F1 on a hidden test set of real KIO cases decides **100%**. Nothing else counts here,
  so a broken run or a wrong output layout on the jury's laptop is fatal.
- **Stage II (final):**

| Weight | Criterion | What the jury looks at |
|---|---|---|
| 50% | Extraction quality | F1 on the hidden test set |
| 50% (README) / 30% (PDF) | Flexibility and extensibility | README: 1–20 pts LLM size (smaller model scores **more**), 1–20 pts new document types and data classes without rebuilding (config only), 1–10 pts other features such as GUI |
| — (README) / 20% (PDF) | Architecture and technical quality | clarity, modularity, maintainability, documentation |

Which split applies is UNCONFIRMED; build for both. UZP published its F1 counts and 80% threshold in #59. The eval uses normalized Levenshtein as the similarity proxy.

## Basic requirements (miss one and the run scores nothing)

- Python **3.13+**; `requirements.txt` installable with `pip install` and in sync with `uv.lock`
  (`make requirements`).
- CLI with instructions in the README that runs from a clean clone on Windows-class office hardware: 16 GB RAM,
  Intel i7, **no GPU**. A wrapper script (`start.bat`, `start.sh`) is welcome.
- `input/` and `output/` folders in the app root. `input/<case>/<file>.pdf` → `output/<case>/<file>.json`, same file
  name, same tree, one JSON per PDF.
- Classification by **content**, not file name. Three classes: appeal, power of attorney, transfer confirmation.
  Anything else → a JSON file containing `{}`.
- JSON per class exactly as `data/uzp/oczekiwane-json/` (keys, nesting, types, formats from the `//` comments).
- `null` where the document does not state a value; never invent data (FAQ 6).
- Text PDFs **and** scans (OCR) both work (FAQ 7).
- Open-source components only, including an **open-weight** LLM that can also be installed locally. LLM by API:
  provider company and servers in the **EU/EEA**; the submission ships with a working API key (handed over
  privately, never committed). A local large model on CPU is a risk, not a plan.

## Prohibited (always a blocking finding)

- API keys, tokens or personal data in the repo, history, logs or demo material. (Training data is synthetic; real
  cases seen at the UZP stand stay out of the repo.)
- Closed-weight models (e.g. GPT, Claude, Gemini) or a non-EU API endpoint in the extraction path.
- Classification by file name or path.
- Gold values, case-specific names, numbers or account numbers from `data/uzp` hard-coded in prompts, configs or
  code; few-shot examples from the holdout cases 51–60.
- Invented values to fill fields; outputs that pass the schema but are not in the document.
- F1 or speed numbers in README, docs or pitch without a matching `evals/results/latest.json`; training-set F1
  presented as the test-set score.
- A crash or an API failure that silently writes wrong JSON. On failure: log it, write nothing or the documented
  fallback, and exit non-zero with a clear message.

## What raises the stage II score

- New document class or field = a new config file (schema + extraction instructions + classification hints), no
  code change. Show it live: add a fourth class in front of the jury.
- Transparency: per field the source page and quoted text span, confidence, which step (rule, OCR, LLM) produced it.
- Smallest open-weight model that keeps F1; report model, size, provider, region, cost per 100 documents.
- GUI: upload PDF, run, side-by-side source and JSON (FAQ 12b).
- Docs: architecture, data flow, model and provider, limits, how to add a class, own test results.

## Required deliverables

- Project title.
- GitHub link to a working prototype: upload documents and read extraction results.
- Optional, but expected by us: technical documentation incl. the LLM used; own quality test results
  (`evals/results/latest.json` + method).

## Pre-push check (coordinator)

1. `git fetch`, then look at what will be pushed: `git log --oneline @{u}..HEAD` and `git diff --stat @{u}..HEAD`
   (for a new branch, compare with `origin/main`).
2. Run the checks that exist: `make check` (ruff format, ruff check, pytest, requirements.txt in sync). If the push
   touches product code, commit first, then run the eval on the committed state (`odwolania2json-eval` skill):
   `uv run python -m evals.run --quick` (full run before submitting). Keep the real output.
3. Start a **fresh** `judge` agent with: the push range, the diff summary, the check output and the eval results
   (`.git/eval-latest.json`). Do not replace it with your own review.
4. Verdict `BLOCK`: fix, commit, repeat from 1. Verdict `PASS`: record it for the hook, then push:
   ```bash
   printf '%s PASS %s\n' "$(git rev-parse HEAD)" "$(date -u +%FT%TZ)" > "$(git rev-parse --git-dir)/judge-pass"
   git push
   ```
5. Never `--force`. Never write `judge-pass` without a real `PASS` from a judge run on that commit.

The hook (`.githooks/pre-push`) also blocks on its own: secrets in pushed lines, tracked `.env` files, files over
10 MB, failing ruff (lint or format) or pytest, `requirements.txt` out of sync with `uv.lock`, product code without a
clean eval run on the pushed commit, and a missing `judge-pass` for the pushed commit. `HN_FINAL=1 git push` (the
submission) also requires a full eval with every required metric passing. Setup once per clone:
`git config core.hooksPath .githooks`. Emergency bypass: `HN_SKIP_JUDGE=1 git push` (judge only) — say so in the
team chat.
