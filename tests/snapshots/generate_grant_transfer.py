"""Regenerate the grant/transfer base snapshot in a temporary integration checkout.

Run from the PR checkout (the generated JSON goes to stdout)::

    src=$PWD
    dest=$(mktemp -d)
    git worktree add --detach "$dest/base" e051dfa11cde0139fdd75e3f104bbe74ffb0f6ca
    (cd "$dest/base" && PYTHONPATH="$PWD:$src/tests" uv run --frozen python -m snapshots.generate_grant_transfer) \
        > "$dest/base.json" && cp "$dest/base.json" "$src/tests/snapshots/grant_transfer_outputs.json"
    git worktree remove "$dest/base"

The pinned commit was origin/baseline/rule-based-extraction for this review.
The native_cases.json inventory covers reviews 1/4/11/22/30 (see its README).
grant_transfer_cases.json adds review 32's ten layouts, controls and public
reproductions, plus additional synthetic confirmations and grants. A positioned
page gives each row's cells as [x coordinate in PDF points, printed text].
The base pipeline processes every PDF and checks the pre-existing snapshot
during generation. Expectations for intentional improvements live in the test.
"""

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from snapshots.generate_native import BASE as NATIVE_BASE
from snapshots.generate_native import CASES, write_native_pdf

from kio2json.pipeline import process_pdf


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


BASE = "e051dfa11cde0139fdd75e3f104bbe74ffb0f6ca"
EXTRA_CASES = CASES.with_name("grant_transfer_cases.json")
EXTRA_OUTPUTS = CASES.with_name("grant_transfer_outputs.json")
NATIVE_OUTPUTS = CASES.with_name("native_outputs.json")


def main():
    checkout = Path.cwd().resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if revision != BASE or Path(process_pdf.__code__.co_filename).resolve().parent.parent != checkout:
        raise SystemExit(f"Run in a temporary checkout of {BASE} using its own package.")
    os.environ.pop("KIO_CLASSES_DIR", None)
    native_cases = load_json(CASES)
    recorded = load_json(NATIVE_OUTPUTS)
    extra_cases = load_json(EXTRA_CASES)
    assert recorded["base"] == NATIVE_BASE and native_cases.keys() == recorded["outputs"].keys()
    assert not native_cases.keys() & extra_cases.keys()
    extra_outputs = {}
    with (
        TemporaryDirectory() as tmp,
        patch("kio2json.pdf_text._ocr", side_effect=AssertionError("Expected native PDF")),
    ):
        path = Path(tmp) / "document.pdf"
        for name, pages in (native_cases | extra_cases).items():
            write_native_pdf(path, pages)
            result = list(process_pdf(path))
            if name in native_cases:
                assert result == recorded["outputs"][name], f"Base replay differs for {name}"
            else:
                extra_outputs[name] = result
    print(json.dumps({"base": revision, "outputs": extra_outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
