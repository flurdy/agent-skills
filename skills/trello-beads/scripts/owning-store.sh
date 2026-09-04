#!/usr/bin/env bash
# owning-store.sh — prove which Beads store owns this Trello board before any bd call.
# The board configuration (.env.local) lives in one repository; that repository's own
# store owns the beads it creates. Fail closed rather than let bd walk up to a parent.
# Sourced by trello-pull.sh and trello-sync.sh; requires a `die` function.

require_owning_store() {
  local root
  root=$(git rev-parse --show-toplevel 2>/dev/null) \
    || die "Not inside a Git repository; run from the repository that holds the Trello board configuration"
  [[ -d "$root/.beads" && ! -L "$root/.beads" ]] \
    || die "No Beads store at $root/.beads; the repository holding the board configuration must own the store"
  BEADS_STORE_DIR="$root"
}

bd_store() {
  bd -C "$BEADS_STORE_DIR" "$@"
}
