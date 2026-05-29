#!/usr/bin/env bash
# Move handoff files out of the active ~/.claude/handoffs/ listing into
# ~/.claude/handoffs/archive/ so the picker de-clutters without losing the
# grep log. Non-destructive: it MOVES, never deletes, and never overwrites.
# Shared by the wrap-up (supersede-at-save) and handoffs (archive sweep) skills.
#
# Usage: archive.sh NAME [NAME...]
#   NAME   a handoff filename (e.g. 2026-05-27-foo.md) or an absolute path to
#          one. Anything that doesn't resolve to a direct child of the handoffs
#          dir is refused (SKIPPED), so a stray path can't move arbitrary files.
#
# Output is delimited for the calling skill to parse:
#   ---ARCHIVE-DIR---   the destination directory
#   ---ARCHIVED---      one `{basename}|{dest-path}` line per moved file
#   ---SKIPPED---       one `{arg}|{reason}` line per refused/missing file
set -uo pipefail

HANDOFFS_DIR="${HOME}/.claude/handoffs"
ARCHIVE_DIR="${HANDOFFS_DIR}/archive"

if [ $# -eq 0 ]; then
    echo "usage: archive.sh NAME [NAME...]" >&2
    exit 2
fi

ARCHIVED=()
SKIPPED=()

for arg in "$@"; do
    # Resolve to a path. A bare name (no slash) is taken relative to the
    # handoffs dir; anything with a slash must already point inside it.
    case "$arg" in
        */*) src="$arg" ;;
        *)   src="${HANDOFFS_DIR}/${arg}" ;;
    esac

    if [ ! -f "$src" ]; then
        SKIPPED+=("${arg}|not found")
        continue
    fi

    # Canonicalise and confirm the file is a *direct* child of the handoffs dir
    # (not already in archive/, not somewhere else on disk).
    abs=$(realpath "$src" 2>/dev/null || true)
    parent=$(dirname "$abs" 2>/dev/null || true)
    if [ -z "$abs" ] || [ "$parent" != "$HANDOFFS_DIR" ]; then
        SKIPPED+=("${arg}|outside handoffs dir")
        continue
    fi

    base=$(basename "$abs")
    mkdir -p "$ARCHIVE_DIR" 2>/dev/null || true

    # Never overwrite: insert -2, -3, … before the .md extension if needed.
    dest="${ARCHIVE_DIR}/${base}"
    if [ -e "$dest" ]; then
        stem="${base%.md}"
        n=2
        while [ -e "${ARCHIVE_DIR}/${stem}-${n}.md" ]; do
            n=$((n+1))
        done
        dest="${ARCHIVE_DIR}/${stem}-${n}.md"
    fi

    if mv "$abs" "$dest" 2>/dev/null; then
        ARCHIVED+=("${base}|${dest}")
    else
        SKIPPED+=("${arg}|move failed")
    fi
done

echo "---ARCHIVE-DIR---"
echo "$ARCHIVE_DIR"
echo "---ARCHIVED---"
for line in "${ARCHIVED[@]:-}"; do
    [ -n "$line" ] && echo "$line"
done
echo "---SKIPPED---"
for line in "${SKIPPED[@]:-}"; do
    [ -n "$line" ] && echo "$line"
done
