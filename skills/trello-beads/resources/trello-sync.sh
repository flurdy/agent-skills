#!/usr/bin/env bash
# trello-sync.sh — Sync closed beads back to Trello (move cards to Done)
# Requires: TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID env vars
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TRELLO_API="$SCRIPT_DIR/trello-api.sh"

DONE_LIST="${TRELLO_LIST_DONE:-Done}"

die() { echo "ERROR: $*" >&2; exit 1; }

# Get the list ID for Done column
get_done_list_id() {
  "$TRELLO_API" list-id "$DONE_LIST"
}

# Extract trello card ID from external ref (trello-<card-id>)
extract_card_id() {
  local ref="$1"
  echo "${ref#trello-}"
}

# Get the list a card is currently in
get_card_list() {
  local card_id="$1"
  curl -sf "https://api.trello.com/1/cards/${card_id}?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}&fields=idList" \
    | jq -r '.idList'
}

cmd_sync() {
  local dry_run="${1:-}"
  local done_list_id
  done_list_id=$(get_done_list_id)
  [[ -n "$done_list_id" ]] || die "Could not find '$DONE_LIST' list on board"

  # Get closed beads with trello label
  local closed_beads
  closed_beads=$(bd list --status=closed --label=trello 2>/dev/null || true)

  if [[ -z "$closed_beads" ]]; then
    echo "No closed beads with trello label found."
    return 0
  fi

  # Get bead IDs from the list output
  local bead_ids
  bead_ids=$(echo "$closed_beads" | grep -oP 'letterbox-\w+' || true)

  if [[ -z "$bead_ids" ]]; then
    echo "No closed trello-linked beads found."
    return 0
  fi

  local synced=0
  local skipped=0
  local failed=0

  while read -r bead_id; do
    [[ -n "$bead_id" ]] || continue

    # Get external ref from bead
    local bead_info
    bead_info=$(bd show "$bead_id" 2>/dev/null || true)

    local ext_ref
    ext_ref=$(echo "$bead_info" | grep -oP 'External: \Ktrello-\S+' || true)

    if [[ -z "$ext_ref" ]]; then
      continue
    fi

    local card_id
    card_id=$(extract_card_id "$ext_ref")
    local bead_title
    bead_title=$(echo "$bead_info" | head -1 | sed 's/^[^·]*· //' | sed 's/   .*//')

    # Check if card is already in Done
    local current_list
    current_list=$(get_card_list "$card_id" 2>/dev/null || true)

    if [[ "$current_list" == "$done_list_id" ]]; then
      skipped=$((skipped + 1))
      continue
    fi

    if [[ "$dry_run" == "--dry-run" ]]; then
      echo "WOULD MOVE: $bead_title → $DONE_LIST (card: $card_id)"
      synced=$((synced + 1))
    else
      if "$TRELLO_API" move "$card_id" "$DONE_LIST" >/dev/null 2>&1; then
        echo "MOVED: $bead_title → $DONE_LIST"
        synced=$((synced + 1))
      else
        echo "FAILED: Could not move card for $bead_title (card: $card_id)"
        failed=$((failed + 1))
      fi
    fi
  done <<< "$bead_ids"

  echo ""
  echo "Sync complete: $synced moved, $skipped already done, $failed failed"
}

cmd_help() {
  cat <<'USAGE'
Usage: trello-sync.sh <command>

Commands:
  sync [--dry-run]    Move Trello cards to Done for closed beads
  help                Show this help

Environment variables:
  TRELLO_LIST_DONE    Done column name (default: "Done")

Examples:
  trello-sync.sh sync              # Move cards for closed beads to Done
  trello-sync.sh sync --dry-run    # Preview what would be moved
USAGE
}

# --- main ---
command="${1:-help}"
shift || true

case "$command" in
  help|--help|-h) cmd_help; exit 0 ;;
esac

# Auth check is handled by trello-api.sh calls
case "$command" in
  sync)    cmd_sync "${1:-}" ;;
  *)       die "Unknown command: $command. Run with 'help' for usage." ;;
esac
