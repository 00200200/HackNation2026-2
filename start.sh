#!/bin/sh
set -eu
cd "$(dirname "$0")"
# The README creates .venv in the repository root. Use it even when it is not activated, for example under sudo.
# Otherwise take the first interpreter on PATH that is Python 3.13 or newer. Ubuntu and macOS install python3 only,
# and Ubuntu 24.04 ships 3.12.
py=
for candidate in .venv/bin/python python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 13))' 2>/dev/null; then
        py=$candidate
        break
    fi
done
[ -n "$py" ] || { echo "Python 3.13 or newer was not found. See Run in README.md." >&2; exit 1; }
case "$#:${1:-}" in
    0:) exec "$py" -m kio2json ;;
    1:gui) exec "$py" -m kio2json.gui ;;
    *) echo "Usage: $0 [gui]" >&2; exit 2 ;;
esac
