#!/usr/bin/env bash
# Pick the next free handoff filename for the wrap-up skill, never overwriting.
#
# Usage: handoff-path.sh <YYYY-MM-DD> <slug>
#
# Prints the absolute path the resume block should be written to:
#   ~/.claude/handoffs/<date>-<slug>.md          if that name is free, else
#   ~/.claude/handoffs/<date>-<slug>-2.md, -3.md … the first non-existing one.
#
# This makes the "never overwrite — append -2/-3" rule mechanical instead of
# relying on the model to remember to check first. The -N collision suffix is a
# first-class convention the /handoffs picker understands: it uses the resume
# time first, then orders an established same-day collision family by suffix.
set -uo pipefail

date="${1:-}"
slug="${2:-}"

if [ -z "$date" ] || [ -z "$slug" ]; then
    echo "usage: handoff-path.sh <YYYY-MM-DD> <slug>" >&2
    exit 2
fi

# Both arguments are model-generated, and the printed path is written to
# verbatim. Enforce the documented shapes so a slug cannot traverse out of the
# handoffs directory or carry shell metacharacters into the picker.
case "$date" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) echo "handoff-path.sh: date must be YYYY-MM-DD, got: $date" >&2; exit 2 ;;
esac

# Matched with case, not grep: grep -E anchors per line, so a multi-line slug
# whose first line is valid would pass. case globs match the whole string.
case "$slug" in
    *[!a-z0-9-]* | -* | *- | *--* )
        echo "handoff-path.sh: slug must be kebab-case ([a-z0-9] and single hyphens), got: $slug" >&2
        exit 2
        ;;
esac

dir="$HOME/.claude/handoffs"
mkdir -p "$dir"

emit_contained() {
    local candidate="$1"
    if [ "$(dirname "$candidate")" != "$dir" ]; then
        echo "handoff-path.sh: refusing path outside handoffs dir: $candidate" >&2
        exit 2
    fi
    echo "$candidate"
}

base="$dir/${date}-${slug}.md"
if [ ! -e "$base" ]; then
    emit_contained "$base"
    exit 0
fi

# Collision — find the first free -N suffix (starting at 2).
n=2
while [ -e "$dir/${date}-${slug}-${n}.md" ]; do
    n=$((n + 1))
done
emit_contained "$dir/${date}-${slug}-${n}.md"
