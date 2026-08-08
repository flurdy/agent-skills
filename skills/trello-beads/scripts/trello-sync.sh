#!/usr/bin/env bash
# trello-sync.sh — Sync closed beads back to Trello (move cards to Done)
# Requires: TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID env vars
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TRELLO_API="$SCRIPT_DIR/trello-api.sh"
# shellcheck source=trello-api.sh
source "$TRELLO_API"

DONE_LIST="${TRELLO_LIST_DONE:-Done}"

die() { echo "ERROR: $*" >&2; exit 1; }

# Get the list ID for Done column
get_done_list_id() {
  resolve_list_id "$DONE_LIST"
}

# Extract trello card ID from external ref (trello-<card-id>)
extract_card_id() {
  local ref="$1"
  echo "${ref#trello-}"
}

cmd_sync() {
  (($# <= 1)) || die "Usage: trello-sync.sh sync [--dry-run|--apply]"
  local option="${1:-}"
  local mode
  case "$option" in
    ""|--dry-run) mode="plan" ;;
    --apply) mode="apply" ;;
    *) die "Unknown sync option: $option. Use --apply only after reviewing the plan." ;;
  esac

  local done_list_id
  done_list_id=$(get_done_list_id)
  [[ -n "$done_list_id" ]] || die "Could not find '$DONE_LIST' list on board"

  # Batch-fetch all card IDs already in Done (including archived) — single API call
  local done_cards
  done_cards=$(trello_request GET "/lists/${done_list_id}/cards" \
    --get --data-urlencode "filter=all" --data-urlencode "fields=id")
  if ! jq -e '
    type == "array" and
    all(.[]; type == "object" and (.id | type == "string" and length > 0))
  ' <<<"$done_cards" >/dev/null; then
    echo "FAILED: Trello returned an invalid Done-list card payload" >&2
    return 1
  fi

  local done_card_ids
  done_card_ids=$(jq -r '.[].id' <<<"$done_cards")

  # Get closed beads with trello label
  local closed_beads
  if ! closed_beads=$(bd list --status=closed --label=trello); then
    echo "FAILED: Could not list closed Trello-linked Beads" >&2
    return 1
  fi

  if [[ -z "$closed_beads" ]]; then
    echo "No closed beads with trello label found."
    return 0
  fi

  # Get bead IDs from the list output (one per line, id is the first token)
  local bead_ids
  bead_ids=$(echo "$closed_beads" | grep -oP '^\s*\K[a-z0-9][a-z0-9-]*-\w+' || true)

  if [[ -z "$bead_ids" ]]; then
    echo "No closed trello-linked beads found."
    return 0
  fi

  local synced=0
  local skipped=0
  local archived=0
  local failed=0

  while read -r bead_id; do
    [[ -n "$bead_id" ]] || continue

    # Get external ref from bead
    local bead_info
    if ! bead_info=$(bd show "$bead_id"); then
      echo "FAILED: Could not read Bead $bead_id" >&2
      failed=$((failed + 1))
      continue
    fi

    local ext_ref
    ext_ref=$(echo "$bead_info" | grep -oP 'External: \Ktrello-\S+' || true)

    if [[ -z "$ext_ref" ]]; then
      echo "FAILED: Missing Trello external reference for Bead $bead_id" >&2
      failed=$((failed + 1))
      continue
    fi

    local card_id
    card_id=$(extract_card_id "$ext_ref")
    local bead_title
    bead_title=$(echo "$bead_info" | head -1 | sed 's/^[^·]*· //' | sed 's/   .*//')

    # Fast check: is this card already in Done? (no API call needed)
    # -x for whole-line equality and -- so a card_id starting with a dash is not
    # read as an option; a substring match would treat a malformed short external
    # ref as equal to any ID containing it.
    if printf '%s\n' "$done_card_ids" | grep -qxF -- "$card_id"; then
      skipped=$((skipped + 1))
      continue
    fi

    # Card is NOT in Done — fetch its state to check if archived
    local card_info
    card_info=$(trello_request GET "/cards/${card_id}" \
      --get --data-urlencode "fields=closed,idList,name" 2>/dev/null || true)

    if [[ -z "$card_info" ]]; then
      echo "FAILED: Could not fetch card for $bead_title (card: $card_id)"
      failed=$((failed + 1))
      continue
    fi

    if ! jq -e '
      type == "object" and
      (.closed | type == "boolean") and
      (.idList | type == "string" and length > 0) and
      (.name | type == "string" and length > 0)
    ' <<<"$card_info" >/dev/null; then
      echo "FAILED: Invalid card state for $bead_title (card: $card_id)" >&2
      failed=$((failed + 1))
      continue
    fi

    local is_archived
    is_archived=$(echo "$card_info" | jq -r '.closed')

    if [[ "$is_archived" == "true" ]]; then
      local card_name
      card_name=$(echo "$card_info" | jq -r '.name')
      echo "SKIPPED (archived in another list): $bead_title — Trello: \"$card_name\" (card: $card_id)"
      archived=$((archived + 1))
      continue
    fi

    if [[ "$mode" == "plan" ]]; then
      echo "WOULD MOVE: $bead_title → $DONE_LIST (card: $card_id)"
      synced=$((synced + 1))
    elif "$TRELLO_API" move "$card_id" "$DONE_LIST" --apply >/dev/null; then
      echo "MOVED: $bead_title → $DONE_LIST"
      synced=$((synced + 1))
    else
      echo "FAILED: Could not move card for $bead_title (card: $card_id)"
      failed=$((failed + 1))
    fi
  done <<< "$bead_ids"

  echo ""
  if [[ "$mode" == "plan" ]]; then
    echo "Sync plan: $synced would move, $skipped already done, $archived archived elsewhere, $failed unreadable"
    echo "No changes made. Obtain confirmation, then rerun with sync --apply."
  else
    echo "Sync complete: $synced moved, $skipped already done, $archived archived elsewhere, $failed failed"
  fi

  ((failed == 0))
}

cmd_help() {
  cat <<'USAGE'
Usage: trello-sync.sh <command>

Commands:
  sync [--dry-run]    Preview cards that would move to Done (default)
  sync --apply        Move cards after the preview is confirmed
  help                Show this help

Environment variables:
  TRELLO_LIST_DONE    Done column name (default: "Done")

Examples:
  trello-sync.sh sync              # Preview what would be moved
  trello-sync.sh sync --dry-run    # Explicit preview alias
  trello-sync.sh sync --apply      # Apply after confirmation
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
  sync)    cmd_sync "$@" ;;
  *)       die "Unknown command: $command. Run with 'help' for usage." ;;
esac
