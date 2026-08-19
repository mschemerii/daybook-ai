#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "Daybook AI is not installed yet. Run: bash install.sh" >&2
    exit 1
fi
exec "$PY" "$ROOT/run.py" "$@"
