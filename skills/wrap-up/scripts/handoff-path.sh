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

dir="$HOME/.claude/handoffs"
mkdir -p "$dir"

base="$dir/${date}-${slug}.md"
if [ ! -e "$base" ]; then
    echo "$base"
    exit 0
fi

# Collision — find the first free -N suffix (starting at 2).
n=2
while [ -e "$dir/${date}-${slug}-${n}.md" ]; do
    n=$((n + 1))
done
echo "$dir/${date}-${slug}-${n}.md"
