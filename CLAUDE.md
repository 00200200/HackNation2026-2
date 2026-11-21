# CLAUDE.md

Hackathon repository. The challenge, stack and team roles are not fixed in this file on purpose:
read them from the brief, the code and the conversation. If something blocks a decision, ask once
and keep working on what does not depend on it.

## Workflow

| Situation | Use |
|---|---|
| Writing or changing code | `/build` (SDK-first) |
| Before every commit, or "does it actually work?" | `/verify` + `reviewer` agent |
| Any user-facing text: UI copy, pitch, docs, submission form | `/humanizer` |
| "Is there a library/SDK for X?", current API of a library | `researcher` agent |

Agents: `builder` (implements an assigned slice), `reviewer` (read-only, before every commit),
`researcher` (read-only, finds the SDK/library and its current API).

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
  or model weights.
- Use the package manager the repo already uses (lockfile wins). For new Python projects: `uv`.
  For new JS/TS projects: `pnpm`.

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
