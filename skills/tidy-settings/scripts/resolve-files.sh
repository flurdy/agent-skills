#!/usr/bin/env bash
# Resolve every settings file the tidy-settings skill operates on, grouped by
# role. Sections are delimited by `---<NAME>---` markers for easy parsing.
set -uo pipefail

# User-level: always checked.
echo "---USER---"
for f in ~/.claude/settings.json ~/.claude/settings.local.json; do
    test -e "$f" && echo "$f"
done

# Canonical project-level: the main worktree's settings. Not
# `git rev-parse --show-toplevel` — inside a linked worktree that points at the
# worktree's own checkout. The first `git worktree list` entry is always the
# main worktree; realpath follows the .claude symlink, if any.
echo "---CANONICAL---"
main_wt=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')
if [ -n "${main_wt:-}" ]; then
    canon=$(realpath "$main_wt/.claude" 2>/dev/null) || canon=""
    if [ -n "$canon" ]; then
        for base in settings.json settings.local.json; do
            test -e "$canon/$base" && echo "$canon/$base"
        done
    fi
fi

# Per-worktree: every other worktree's own real .claude settings — the files
# whose permissions are lost when that worktree is pruned.
echo "---WORKTREE---"
git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' | tail -n +2 \
  | while IFS= read -r wt; do
      for base in settings.json settings.local.json; do
          test -e "$wt/.claude/$base" && echo "$wt/.claude/$base"
      done
    done

exit 0
