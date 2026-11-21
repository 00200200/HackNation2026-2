# Native PDF differential test

Each key in `native_cases.json` names a document. Its array contains the selectable text of successive pages, in reading order. The test writes a temporary PDF with the same neutral filename for each case, verifies its text with pdfplumber and calls the normal PDF pipeline. The snapshot records the class and complete output object, including empty results, nulls and list order. The generator and the test each fail if the reader calls OCR.

| Key prefix | Origin of document text |
| --- | --- |
| `task1/` | `hn2_task1_review_baseline_result.md`. The three one-line reproduction commands are transcribed verbatim. Other cases use the report's quoted text and names in the described layout, including authority ownership, grantor order, the invoice, masked sender, citation and footer. The signer-identity and case-normalization probes render the review's scorer strings as document fields. |
| `task4/` | `hn2_task4_rereview_baseline_result.md`. Includes the P1 and P2 examples, both authority-ID variants and the control examples from the round-one disposition. The two printed accounts follow the review's repeating 21/34 pattern. Task 1 covers the earlier cases repeated in the disposition. |
| `task11/` | `hn2_task11_review_round3_result.md`. All 48 keys of the JSON appendix retain their original IDs and page strings. F0–F3 print the text from the raster and its corresponding selectable footer on the same native page. The three identifier cases use the review's invented numeric test fixture and its two formatting variants. |
| `task22/` | `hn2_task22_review_pr12_result.md`. Includes the original scan's printed lines, contact, receipt with duplicated account, receipt control without the memo, engine word-box text and the NRB, legal-form, heading, role, mail, representation and acceptance probes. Quoted repair fragments appear as printed text. |
| `task30/` | `hn2_task30_rereview_pr12_result.md`. Includes each changed signature and account block, the two sharp footers, the recognized counter spelling and the mixed document with PLAN SALI. The original contact, asterisk control, memo repeating the recipient, and original blurred page share their text with `task22/contact`, `task22/masked-sender-control`, `task22/repeated-recipient` and `task22/unblurred-original`. |
| `new/` | Forty independently invented documents. They exercise party and email boundaries, signer roles, transfer labels and status, unrelated documents, repeated headers and headings on later pages. |

Where a review gives a fragment or describes a layout, surrounding text is invented to exercise it through PDF routing. For image probes these fixtures print the underlying words, with any printed footer, as selectable text. Blur, a truly blank transcript, damaged PDFs, runtime deadlines and scorer-only numeric comparisons require their own tests. The inputs here contain no records from the private corpus or organizer reference examples. Expected values reflect the integration base, including its mistakes.

## Generate the snapshot

Run these commands from the feature worktree root. The pinned revision is the integration base of the reviewed PR. The feature checkout supplies the cases and PDF writer. The temporary detached checkout supplies the installed dependencies, class configurations and all product code.

```sh
src=$PWD
snapshot_root=$(mktemp -d)
git worktree add --detach "$snapshot_root/base" 32106434f746628c7080191597f0766d4151d786
(
  cd "$snapshot_root/base" &&
  PYTHONPATH="$PWD" uv run --frozen python "$src/tests/snapshots/generate_native.py" > "$snapshot_root/native_outputs.json"
) && cp "$snapshot_root/native_outputs.json" "$src/tests/snapshots/native_outputs.json"
git worktree remove "$snapshot_root/base"
```

Run `uv run pytest -q tests/test_native_snapshot.py` to compare the current pipeline against the recorded outputs. Test collection reads only the committed JSON and Python files.

## Grant and transfer differential

`tests/test_grant_transfer_differential.py` also replays the 175 native cases above, the ten layouts and eleven controls from review 32, and 41 additional synthetic grant or transfer cases, 12 execution-date, status and notice cases from review 40, 30 plain-label receipts and grants, and three receipts checking execution-date precedence from review 47. These last 45 cases require exact base output. A positioned page in `grant_transfer_cases.json` contains rows of `[x, text]` cells so two-column fixtures pass through actual PDF word extraction. The expected class and entire output for each of the 107 extra documents are recorded in `grant_transfer_outputs.json`.

The `grant_transfer_changes.py` module’s `INTENDED_CHANGES` table gives a case ID, field path, exact base and expected values, and evidence for each change. A list insertion preserves existing entries. The native snapshot test consults the same table and retains the serialized comparison and OCR-provenance checks. The base recording includes the original outputs for all 175 cases.

Generate the extra snapshot from the feature worktree root with the pinned integration commit. The generator replays all 282 PDFs and checks the original 175 outputs against their existing snapshot before writing the extra results.

```sh
src=$PWD
snapshot_root=$(mktemp -d)
git worktree add --detach "$snapshot_root/base" e051dfa11cde0139fdd75e3f104bbe74ffb0f6ca
(
  cd "$snapshot_root/base" &&
  PYTHONPATH="$PWD:$src/tests" uv run --frozen python -m snapshots.generate_grant_transfer > "$snapshot_root/extra.json"
) && cp "$snapshot_root/extra.json" "$src/tests/snapshots/grant_transfer_outputs.json"
git worktree remove "$snapshot_root/base"
```

Run `uv run pytest -q tests/test_grant_transfer_differential.py tests/test_native_snapshot.py` to exercise both comparisons.

The appeal differential uses `appeal_review_inputs.json` and `appeal_baseline.json`. The regeneration command is in `generate_appeal_baseline.py`. Each intended change in `test_appeal_differential.py` records its exact input, path, old value, new value and reason. The native PDF test applies the same table only when the text and complete baseline record match.
