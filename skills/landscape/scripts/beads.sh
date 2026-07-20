#!/usr/bin/env bash
# Emit beads state for the landscape skill.
# Single entry point so the skill never chains `bd` probes + listings inline.
# Sections are delimited by `---<NAME>---` markers for easy parsing.
#
# Exit code is always 0 — beads being absent is not an error.
set -uo pipefail

if ! command -v bd >/dev/null 2>&1; then
    echo "---STATUS---"
    echo "NO_BD"
    exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
if [ ! -d "$REPO_ROOT/.beads" ]; then
    echo "---STATUS---"
    echo "NO_BEADS_IN_REPO"
    exit 0
fi

echo "---STATUS---"
echo "OK"

echo "---IN-PROGRESS---"
bd list --status=in_progress 2>/dev/null || true

echo "---READY---"
if [ -x "$HOME/.agents/skills/next/scripts/next-bd" ]; then
    "$HOME/.agents/skills/next/scripts/next-bd" --json 2>/dev/null || bd list --ready 2>/dev/null || true
else
    bd list --ready 2>/dev/null || true
fi
