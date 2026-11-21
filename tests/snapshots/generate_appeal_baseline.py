"""Regenerate the text differential from a clean, detached integration baseline.

Run from the feature root (replace /tmp/appeal-base with an unused path):
    git worktree add --detach /tmp/appeal-base origin/baseline/rule-based-extraction
    uv run --project /tmp/appeal-base python tests/snapshots/generate_appeal_baseline.py /tmp/appeal-base
    git worktree remove /tmp/appeal-base
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def extract_page(text, definitions, *, direct_appeal=False):
    from kio2json import appeal
    from kio2json.class_config import route
    from kio2json.engines import extract
    from kio2json.pdf_text import join_pages

    pages = [text]
    if direct_appeal:
        return {"class": "appeal", "output": appeal.extract(join_pages(pages))}
    definition = route(pages, definitions)
    if definition is None:
        return {"class": None, "output": {}}
    return {"class": definition.id, "output": extract(definition, join_pages(pages))}


def main(checkout):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()

    head = git("rev-parse", "HEAD")
    if head != git("rev-parse", "origin/baseline/rule-based-extraction") or git("status", "--porcelain"):
        raise SystemExit("Use a clean checkout of origin/baseline/rule-based-extraction")
    sys.path.insert(0, str(checkout.resolve()))
    from kio2json.class_config import load_classes

    definitions = load_classes(checkout / "config" / "classes")
    inputs = json.loads((HERE / "appeal_review_inputs.json").read_text(encoding="utf-8"))
    records = {
        key: extract_page(value, definitions, direct_appeal=key.startswith("direct-appeal-"))
        for key, value in inputs.items()
    }
    snapshot = {"commit": head, "records": records}
    (HERE / "appeal_baseline.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
