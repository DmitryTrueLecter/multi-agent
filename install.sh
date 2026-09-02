#!/usr/bin/env bash
# dma plugin — per-project install.
#
# Copies project-local scaffolding into <project>/.claude/dma/ when it is missing.
# Idempotent: existing files are never overwritten.
#
# Usage:
#   bash install.sh            # install into the current directory
#   bash install.sh <project>  # install into <project>

set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT="${1:-$PWD}"
DEST="$PROJECT/.claude/dma"

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
copy_if_missing "$ROOT/agents/sentinel/templates/arch.yml" "$DEST/arch.yml"
copy_if_missing "$ROOT/Justfile"                 "$DEST/Justfile"

# The analyst's product description: templates for the tracked files, and the
# self-ignoring drafts directory for feature documents in progress.
for template in product glossary features rules non-goals; do
    copy_if_missing "$ROOT/agents/sentinel/templates/product/$template.md" "$DEST/product/$template.md"
done
copy_if_missing "$ROOT/agents/sentinel/templates/product/drafts/.gitignore" "$DEST/product/drafts/.gitignore"
