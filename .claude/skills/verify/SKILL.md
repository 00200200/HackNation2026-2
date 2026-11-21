---
name: verify
description: "Pre-commit and demo-readiness check: independent review of the staged diff by the reviewer agent, plus a walk through the real scenario from input to visible result. Use before every commit, when accepting changes, or when asking whether the MVP actually works."
---

# Verify before commit

## Pre-commit (always)

1. Stage the candidate explicitly. Read `git status` and `git diff --cached`, including new and
   deleted files.
2. Run the checks that match the change (tests, type check, linter, a manual run of the path).
   Results must come from the staged state; if unstaged changes could affect them, say so.
3. Start a **fresh** `reviewer` agent with: the staged diff, the goal of the change and the actual
   check output. Do not substitute your own review for it.
4. Fix confirmed findings, re-stage, and re-review the changed scope with a new `reviewer`.
5. Commit with a standalone `git commit` (no `-a`). Report anything left unverified.

If no reviewer can run, report that as an unmet condition, not as a passed review.

## What to check

- **Correctness** of the changed behaviour and its boundaries: empty input, missing data,
  integration error, timeout. For permissions, test both the allowed and the forbidden case.
- **Contracts** between components still match on both sides.
- **SDK-first**: new custom infrastructure that an existing dependency, the official SDK or a
  maintained library already covers is a finding. So is a wrapper layer around an SDK that adds
  nothing, and a new dependency with no concrete benefit.
- **Simplicity**: dead code, misleading names, duplication, needless layers, when they make the
  change harder to trust. Not style preferences.
- **Honest output**: UI and demo text do not present fixtures, fallbacks or estimates as live
  results or measurements. User-facing copy reads naturally (`/humanizer`).
- **Secrets**: no keys, tokens or `.env` content in the diff.

## Demo readiness

Walk the main scenario from the user's action through API and data to what appears on screen.
HTTP 200 or a green build alone proves nothing. Try at least one input that is not in the
rehearsed script. Check that numbers and logs match the operation actually performed. If a service
is unreachable, state the scope actually confirmed.

## Reporting

Only concrete, reproducible bugs: condition or input → actual → expected, with evidence and
location. Severity: P0 data loss or crash; P1 blocks the main scenario or demo; P2 wrong in an
important variant; P3 minor. List confirmed scenarios, the reproduce command and remaining gaps.
No findings means "no bugs found in the checked scope", nothing more.
