#!/usr/bin/env bash
# Run as the deployment user from /opt/solution, with the release checked out.
set -euo pipefail

root=$(pwd -P)
if [[ ! -d "$root/input" || ! -d "$root/output" ]]; then
    echo "Run from /opt/solution, alongside the organizer's input and output directories." >&2
    exit 1
fi
source_repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
release=$(git -C "$source_repo" rev-parse HEAD)
repo="$root/repo"
if [[ ! -d "$repo/.git" ]]; then
    git clone --no-local --depth 1 "$source_repo" "$repo"
fi
if [[ -n $(git -C "$repo" status --porcelain --untracked-files=normal) ]]; then
    echo "The deployment checkout has local changes. Preserve them before updating." >&2
    exit 1
fi
if ! git -C "$repo" cat-file -e "$release^{commit}" 2>/dev/null; then
    git -C "$repo" fetch --depth 1 --no-tags "$source_repo" "$release"
fi
git -C "$repo" checkout --detach "$release"

python3 -m venv "$root/.bootstrap"
"$root/.bootstrap/bin/python" -m pip install --disable-pip-version-check 'uv==0.8.22'
uv="$root/.bootstrap/bin/uv"
export UV_PYTHON_INSTALL_DIR="$root/.python" UV_CACHE_DIR="$root/.cache/uv"
"$uv" python install 3.13.7
if [[ ! -x "$root/.venv/bin/python" ]]; then
    "$uv" venv --managed-python --python 3.13.7 "$root/.venv"
fi
python="$root/.venv/bin/python"
"$python" - "$UV_PYTHON_INSTALL_DIR" <<'PYTHON'
import sys
from pathlib import Path

if sys.version_info[:3] != (3, 13, 7) or not Path(sys.base_prefix).resolve().is_relative_to(Path(sys.argv[1])):
    raise SystemExit("The existing .venv uses a different Python. Move it aside and rerun setup.")
PYTHON
cd "$repo"
"$uv" pip sync --python "$python" requirements.txt

# Run without endpoint settings, even when updating an already keyed installation.
smoke=$(mktemp -d "$root/.smoke.XXXXXX")
trap 'rm -rf -- "$smoke"' EXIT
cd "$smoke"
# Initialize the optional stamp reader too, so a missing ONNX model fails setup.
env -i PATH="$PATH" HOME="$HOME" PYTHONPATH="$repo" "$python" -P -c 'from kio2json.pdf_text import _rapid_engine; _rapid_engine()'
mkdir -p input/nested
cp "$repo/data/uzp/dane/przyklad_01/przelew.pdf" input/transfer.pdf
cp "$repo/data/uzp/dane/skany/odwolania/0001/0001.pdf" input/nested/scan.pdf
env -i PATH="$PATH" HOME="$HOME" PYTHONPATH="$repo" "$python" -P -m kio2json --jobs 2
"$python" - <<'PY'
import json
from pathlib import Path

for file, key in [("transfer.json", "przelew_bankowy"), ("nested/scan.json", "OdwolanieKIO")]:
    if key not in json.loads(Path("output", file).read_text(encoding="utf-8")):
        raise SystemExit(f"Smoke test failed to recognize {file}")
PY
install -m 644 "$repo/deploy/RUN.md" "$root/RUN.md"
echo "Installed $release. Run from $root:"
sed -n '/^sudo /p' "$root/RUN.md"
