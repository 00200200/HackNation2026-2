#!/bin/sh
set -eu
cd "$(dirname "$0")"
case "$#:${1:-}" in
    0:) exec python -m kio2json ;;
    1:gui) exec python -m kio2json.gui ;;
    *) echo "Usage: $0 [gui]" >&2; exit 2 ;;
esac
