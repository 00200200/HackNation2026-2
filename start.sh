#!/bin/sh
set -eu
cd "$(dirname "$0")"
# The README creates .venv in the repository root. Use it even when it is not activated, for example under sudo.
# Otherwise take whichever interpreter the shell provides: Ubuntu and macOS install python3 only.
if [ -x .venv/bin/python ]; then
    py=.venv/bin/python
else
    py=$(command -v python || command -v python3) || { echo "Python 3.13 was not found. See Run in README.md." >&2; exit 1; }
fi
case "$#:${1:-}" in
    0:) exec "$py" -m kio2json ;;
    1:gui) exec "$py" -m kio2json.gui ;;
    *) echo "Usage: $0 [gui]" >&2; exit 2 ;;
esac
