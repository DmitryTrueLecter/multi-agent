#!/usr/bin/env bash
# dma plugin — per-project install.
#
# Copies project-local scaffolding into <project>/.claude/ when it is missing.
# Idempotent: existing files are never overwritten.
#
# Usage:
#   bash install.sh            # install into the current directory
#   bash install.sh <project>  # install into <project>

set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT="${1:-$PWD}"
DEST="$PROJECT/.claude"

copy_if_missing() {
    local src="$1" dst="$2"
    mkdir -p "$(dirname "$dst")"
    if [ -e "$dst" ]; then
        echo "skip (exists): $dst"
    else
        cp "$src" "$dst"
        echo "created:       $dst"
    fi
}

copy_if_missing "$ROOT/config.example.yml"       "$DEST/config.yml"
copy_if_missing "$ROOT/Justfile"                 "$DEST/Justfile"
copy_if_missing "$ROOT/scripts/claude-resume.sh" "$DEST/scripts/claude-resume.sh"
chmod +x "$DEST/scripts/claude-resume.sh" 2>/dev/null || true
