# Worklog

Shared state of the project. Rules: `CLAUDE.md` → Worklog.

## Now

- Task brief, FAQ and details PDF in `docs/task/`; organizer repo copied into `data/uzp` (`make data` refreshes);
  template example in `input/case1`.
- Eval harness (`evals/`, field-level F1 on the training cases, working definition) with tests. No app yet:
  the eval's default command (`uv run python -m odwolania2json`) does not exist.
- Claude Code setup: skills `hacknation-judging`, `odwolania2json-eval`, `build`, `verify`, `humanizer`;
  agents `judge`, `builder`, `reviewer`, `researcher`; pre-push hook in `.githooks/`.

## Last eval

None yet.

## Next

| Item | Owner |
|---|---|
| CLI skeleton: `input/` → `output/`, empty JSON for unknown documents | — |
| Text extraction + OCR fallback for scans (CPU only) | — |
| Classification by content, config-driven classes | — |
| Extraction per class with an open-weight LLM on an EU API (pydantic-ai) | — |
| Ask the UZP stand: F1 formula, stage II weights (README 50/50 vs PDF 50/30/20) | — |

## Decisions

- 21.11.2026: Python 3.13, uv, pydantic-ai 2.71.0. Cases 51–60 are the holdout for prompt work.

## Log

- 21.11.2026 · Claude · brief, eval harness, judge/eval skills, pre-push hook · f6db304
- 21.11.2026 · Claude · stricter F1 normalisation (types, formats), invented test fixture, organizer data copied into the repo (UZP e8b7a67)
