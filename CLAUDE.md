# CLAUDE.md

Hackathon repository. The challenge, stack and team roles are not fixed in this file on purpose:
read them from the brief, the code and the conversation. If something blocks a decision, ask once
and keep working on what does not depend on it.

## Task

Odwołania2json (UZP): classify the PDFs of a KIO appeal case by content and write one JSON per PDF in the
organizer's schema. Facts, sources and open questions: `docs/task/BRIEF.md` (FAQ: `docs/task/FAQ.md`, details PDF:
`docs/task/odwolania2json-szczegoly.pdf`). Organizer data and schemas: `data/uzp/` (a committed copy of their repo; `make data` refreshes it).
Stage I is 100% F1 on a hidden set of real cases, so every extraction change goes through the eval.

## Worklog

`WORKLOG.md` is the shared state of the project: what works, branches, last eval, open work with
owners, decisions and a dated log. Read it before starting a task. Update it in the same commit when
you finish a task, take or drop an item from "Next", change a decision or run an eval: keep "Now"
and "Next" true, append one line to "Log" (date, who, what, commit). Before taking an item, check
nobody owns it. Parallel branches: on merge conflicts in `WORKLOG.md`, keep both log lines.

## Workflow

| Situation | Use |
|---|---|
| Writing or changing code | `/build` (SDK-first) |
| Before every commit, or "does it actually work?" | `/verify` + `reviewer` agent |
| Any user-facing text: UI copy, pitch, docs, submission form | `/humanizer` |
| "Is there a library/SDK for X?", current API of a library | `researcher` agent |
| Before every push, before submitting, "would the jury accept this?" | `/hacknation-judging` + `judge` agent |
| Extraction, OCR, prompts, schemas, model choice; "what is our F1?" | `/odwolania2json-eval` (`uv run python -m evals.run`) |

Agents: `builder` (implements an assigned slice), `reviewer` (read-only, before every commit),
`researcher` (read-only, finds the SDK/library and its current API),
`judge` (read-only, plays the Odwołania2json jury before every push and returns PASS or BLOCK).

Pre-push hook: `.githooks/pre-push` (setup once per clone: `git config core.hooksPath .githooks`). It refuses a push
without a judge PASS for the pushed commit, product code without a clean eval run on that commit (once an eval
has run in the clone), secrets, tracked `.env` files, files over 10 MB, failing ruff or pytest, and a
`requirements.txt` out of sync with `uv.lock`. Submission: `HN_FINAL=1 git push` (full eval, all metrics pass).
Never bypass it with `--no-verify`; `HN_SKIP_JUDGE=1` only in an emergency, and tell the team.

## SDK first, custom code last

The default answer to "we need X" is an existing, maintained library or the official SDK, not a new
function. Before writing more than a few lines of infrastructure (HTTP client, retries, parsing,
auth, queues, caching, agent loops, tool calling, vector search, UI components, charts, validation):

1. Check what the stack already has: dependencies in the manifest, the framework's built-ins.
2. Check the official SDK of the service you integrate with, in its **current** docs
   (Context7 MCP or the docs site), not from memory. APIs change; verify names and signatures.
3. Pick a widely used library with recent releases if neither covers it.
4. Write custom code only for the gap that is left, and say in one line why no library fits.

Thin glue around good libraries beats a clever framework of our own. Do not wrap an SDK in another
abstraction layer "for flexibility"; call it directly. Do not add a dependency for a one-liner.

## Engineering rules

- One working path from input to visible result first, then widen. A module that is not wired into
  the demo path is not done.
- Real integrations and fixtures share one contract. When the demo runs on a fixture or fallback,
  the UI says so. Never present sample data, estimates or mocks as live results.
- Keep code short and readable: clear names, flat control flow, no dead code, no speculative
  options. Follow the conventions already in the repo.
- Bound every external call: timeout, retry count, and what the user sees on failure.
- Secrets live in ignored `.env*` files. Never commit keys, tokens, datasets with personal data
  or model weights. The one exception is the two Tesseract `tessdata_fast` models in `kio2json/tessdata/`
  (Apache-2.0, 8.9 MB, SHA-256 checked before OCR): vendored so that `pip install -r requirements.txt` needs only PyPI.
- Use the package manager the repo already uses (lockfile wins). For new Python projects: `uv`.
  For new JS/TS projects: `pnpm`.
- Python 3.13+, `uv` for dependencies. The jury installs with `pip install -r requirements.txt`: after every
  dependency change run `make requirements` and commit both files.

## Facts and claims

- Separate confirmed facts from assumptions. Mark unconfirmed organizer details as UNCONFIRMED.
- Numbers in the UI, pitch or README come from a measurement in this repo or a cited source.
  Do not invent users, accuracy, savings or benchmarks.

## Git

- Small commits with a clear message. Run `/verify` with an independent `reviewer` before each one.
- Never force-push shared branches. Never submit the hackathon entry without an explicit go from
  the team.

## Language

Write code, comments, docs, skills and agent files in English. Answer team members in the language
they write in.
