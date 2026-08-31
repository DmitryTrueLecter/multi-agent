#!/usr/bin/env bash
# SessionStart hook: make sure the plugin's venv exists and matches requirements.txt.
# Idempotent and silent on success (SessionStart stdout would land in the model's context).
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
VENV="$ROOT/.venv"
REQ="$ROOT/requirements.txt"
STAMP="$VENV/.requirements.sha"

want="$(shasum -a 256 "$REQ" | cut -d' ' -f1)"
if [ -x "$VENV/bin/python" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$want" ]; then
    exit 0
fi
python3 -m venv "$VENV" >/dev/null
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r "$REQ" >/dev/null
echo "$want" > "$STAMP"
