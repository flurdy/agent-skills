#!/usr/bin/env bash
# trello-pull.sh — Pull cards from Trello triage list into Beads
# Requires: TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID env vars
# Optional: TRELLO_LIST_TRIAGE (default: "Triage")
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TRELLO_API="$SCRIPT_DIR/trello-api.sh"

TRIAGE_LIST="${TRELLO_LIST_TRIAGE:-Triage}"
BUGS_LIST="${TRELLO_LIST_BUGS:-Bugs}"

die() { echo "ERROR: $*" >&2; exit 1; }

# Map Trello label color to bead type
map_type() {
  local colors="$1"
  local source_list="$2"

  # Cards from Bugs column are always bugs
  [[ "$source_list" == "$BUGS_LIST" ]] && echo "bug" && return

  case "$colors" in
    *red*)    echo "bug" ;;
    *green*)  echo "feature" ;;
    *blue*)   echo "feature" ;;
    *yellow*) echo "task" ;;
    *orange*) echo "task" ;;
    *)        echo "task" ;;
  esac
}

# Map Trello label color to bead priority
map_priority() {
  local colors="$1"
  case "$colors" in
    *red*)    echo "2" ;;
    *purple*) echo "3" ;;
    *)        echo "2" ;;
  esac
}

pull_card() {
  local card_id="$1"
  local card_name="$2"
  local card_desc="$3"
  local card_url="$4"
  local label_colors="$5"
  local source_list="$6"
  local move_after="${7:-}"

  local bead_type bead_priority bead_desc

  bead_type=$(map_type "$label_colors" "$source_list")
  bead_priority=$(map_priority "$label_colors")

  # Build description with Trello reference
  bead_desc="From Trello: ${card_url}"
  if [[ -n "$card_desc" ]]; then
    bead_desc="${bead_desc}

${card_desc}"
  fi

  # Check for existing bead with same title and trello label
  if bd list --status=open --label=trello 2>/dev/null | grep -qF "$card_name"; then
    echo "SKIP: Bead already exists for card: $card_name"
    return 0
  fi

  # Create the bead
  local result
  result=$(bd create \
    --title="$card_name" \
    --type="$bead_type" \
    --priority="$bead_priority" \
    --description="$bead_desc" \
    --external-ref "trello-${card_id}" \
    --labels "trello" 2>&1)

  echo "$result"

  # Move card if requested
  if [[ -n "$move_after" ]]; then
    "$TRELLO_API" move "$card_id" "$move_after" >/dev/null 2>&1
    echo "  Moved Trello card to: $move_after"
  fi
}

cmd_list() {
  local list_name="${1:-$TRIAGE_LIST}"
  echo "Cards in '$list_name':"
  echo ""
  "$TRELLO_API" cards-summary "$list_name"
}

cmd_pull() {
  local card_filter="${1:-}"
  local move_after="${2:-}"
  local list_name="$TRIAGE_LIST"

  # Get cards as JSON
  local cards
  cards=$("$TRELLO_API" cards "$list_name")

  local count
  count=$(echo "$cards" | jq 'length')

  if [[ "$count" -eq 0 ]]; then
    echo "No cards in '$list_name' to pull."
    return 0
  fi

  echo "Pulling $count card(s) from '$list_name'..."
  echo ""

  echo "$cards" | jq -c '.[]' | while read -r card; do
    local id name desc url label_colors

    id=$(echo "$card" | jq -r '.id')
    name=$(echo "$card" | jq -r '.name')
    desc=$(echo "$card" | jq -r '.desc // ""')
    url=$(echo "$card" | jq -r '.shortUrl')
    label_colors=$(echo "$card" | jq -r '[.labels[].color] | join(",")')

    # If a specific card ID was given, skip others
    if [[ -n "$card_filter" && "$id" != "$card_filter" ]]; then
      continue
    fi

    pull_card "$id" "$name" "$desc" "$url" "$label_colors" "$list_name" "$move_after"
    echo ""
  done
}

cmd_help() {
  cat <<'USAGE'
Usage: trello-pull.sh <command> [args...]

Commands:
  list [list-name]           Show cards in triage list (default: $TRELLO_LIST_TRIAGE)
  pull [card-id] [move-to]   Pull triage cards into beads
                              card-id: optional, pull only this card
                              move-to: optional, move card to this list after pull
  pull-all [move-to]         Pull all triage cards (shorthand)
  help                       Show this help

Environment variables:
  TRELLO_LIST_TRIAGE   Triage column name (default: "Triage")
  TRELLO_LIST_BUGS     Bugs column name (default: "Bugs")

Examples:
  trello-pull.sh list                          # Show triage cards
  trello-pull.sh pull                          # Pull all, don't move
  trello-pull.sh pull "" "Backlog"             # Pull all, move to Backlog
  trello-pull.sh pull 69b8b8d7... "Backlog"   # Pull one card, move to Backlog
USAGE
}

# --- main ---
command="${1:-help}"
shift || true

case "$command" in
  list)      cmd_list "${1:-}" ;;
  pull)      cmd_pull "${1:-}" "${2:-}" ;;
  pull-all)  cmd_pull "" "${1:-}" ;;
  help|--help|-h) cmd_help ;;
  *)         die "Unknown command: $command. Run with 'help' for usage." ;;
esac
