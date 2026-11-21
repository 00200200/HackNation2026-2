---
name: build
description: "Implements a working slice of the hackathon product, SDK-first: finds the official SDK or a maintained library before writing custom code, wires UI, logic and data on one real example, and removes blockers against the deadline. Use whenever writing, changing or fixing code."
---

# Build a working slice, SDK-first

Read the assigned task, decisions from the conversation and the code you will touch. Keep the
chosen stack and contracts. If the product or track is not chosen yet, settle that with the team
before scaffolding anything.

## 1. Look for existing code before writing it

For every piece of infrastructure the slice needs, go down this list and stop at the first hit:

1. **Already in the repo**: dependencies in the manifest, framework built-ins, existing helpers.
2. **Official SDK** of the service or model provider. Read its current docs (Context7 MCP or the
   docs site) for exact names, signatures and the recommended pattern. Training-data memory of an
   API is a hypothesis; check it.
3. **Maintained library**: widely used, recent release, permissive license, fits the stack.
   For a non-trivial choice, ask the `researcher` agent for a short comparison.
4. **Custom code**, only for the remaining gap. State in one line why 1–3 did not cover it.

Typical cases where a library is the right answer: HTTP clients and retries, schema validation,
config and env loading, auth, LLM calls, tool use and agent loops (provider SDKs, Claude Agent SDK,
Pydantic AI and the like), structured output, embeddings and vector search, file parsing (PDF,
DOCX, CSV), background jobs, caching, UI components, forms, tables, charts, maps.

Use the SDK directly. Do not wrap it in a new abstraction "in case we switch providers"; do not
add a dependency for something the standard library does in a line or two.

## 2. Build the thinnest path that works

- Pick the smallest slice that ends in a useful, visible result. UI, logic and data connect on one
  concrete example before anything gets widened.
- Probe the riskiest integration first with a minimal call: auth, quota, latency, response shape.
  Decide what success, timeout and missing data look like for the user.
- Real integration and fixture share one contract. In fallback mode the UI shows where the result
  came from. A fixture does not prove the integration works.
- Bound external calls: timeout, a small retry count at one layer only, no blind retries of
  operations with side effects. A valid schema does not replace permission checks.
- Keep code plain: clear names, flat control flow, repo conventions, no dead code, no options
  nobody asked for.
- UI text says what the user can do and what happened. Run user-facing copy through `/humanizer`.

## 3. Check it

Run the checks that match the change and walk the path from input to visible result. For a web UI,
look at the rendered page in a browser if one is available; otherwise report that as unverified.
When comparing variants (prompts, models, parameters), use the same inputs, change one thing at a
time and keep held-out cases for the final numbers. Measure time and cost when they matter;
missing cost data is not zero.

## When blocked

Reproduce the error, time-box the diagnosis against the deadline, then choose: fix, explicit
fallback or scope cut. Say what it costs in terms of requirements. Re-run the original scenario
after the workaround.

## Hand-over

Report the changed paths, how to run it, the checks you actually ran and their results, and which
libraries you chose (and any custom code with its reason). Before committing, run `/verify` with an
independent `reviewer`.
