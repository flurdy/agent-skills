#!/usr/bin/env bash
# trello-pull.sh — Pull cards from Trello triage list into Beads
# Requires: TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID env vars
# Optional: TRELLO_LIST_TRIAGE (default: "Triage")
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TRELLO_API="$SCRIPT_DIR/trello-api.sh"

TRIAGE_LIST="${TRELLO_LIST_TRIAGE:-Triage}"
BUGS_LIST="${TRELLO_LIST_BUGS:-Bugs}"
BACKLOG_LIST="${TRELLO_LIST_BACKLOG:-Backlog}"
ICEBOX_LIST="${TRELLO_LIST_ICEBOX:-Icebox}"
BEAD_LABEL="${TRELLO_BEAD_LABEL:-bead}"

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

  # Append card comments if any
  local comments_json
  comments_json=$("$TRELLO_API" comments "$card_id" 2>/dev/null || echo "[]")
  local comment_count
  comment_count=$(echo "$comments_json" | jq 'length')
  if [[ "$comment_count" -gt 0 ]]; then
    bead_desc="${bead_desc}

## Trello Comments"
    while IFS= read -r comment; do
      local author text
      author=$(echo "$comment" | jq -r '.author')
      text=$(echo "$comment" | jq -r '.text')
      bead_desc="${bead_desc}

**${author}:** ${text}"
    done < <(echo "$comments_json" | jq -c '.[]')
  fi

  # Check for existing bead with same title and trello label
  if bd list --status=open --label=trello 2>/dev/null | grep -qF "$card_name"; then
    echo "SKIP: Bead already exists for: $card_name"
    echo "  Card remains in $TRIAGE_LIST — move manually or use:"
    echo "    ./scripts/trello-api move $card_id Shredder"
    echo "    ./scripts/trello-api move $card_id $BACKLOG_LIST"
    return 1
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

  # Extract bead ID from creation output
  local bead_id
  bead_id=$(echo "$result" | grep -oP 'letterbox-\w+' | head -1 || true)

  # Add 'bead' label, comment with bead ID, then move card
  "$TRELLO_API" add-label "$card_id" "$BEAD_LABEL" "sky" 2>/dev/null || true
  if [[ -n "$bead_id" ]]; then
    "$TRELLO_API" comment "$card_id" "Bead created: $bead_id" >/dev/null 2>&1 || true
  fi
  # Route card based on type: bugs→Bugs, rest→Backlog
  local dest="${move_after:-$BACKLOG_LIST}"
  if [[ -z "$move_after" && "$bead_type" == "bug" ]]; then
    dest="$BUGS_LIST"
  fi
  "$TRELLO_API" move "$card_id" "$dest" >/dev/null 2>&1
  echo "  Labelled '$BEAD_LABEL', commented, and moved to: $dest"
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

    pull_card "$id" "$name" "$desc" "$url" "$label_colors" "$list_name" "$move_after" || true
    echo ""
  done
}

cmd_help() {
  cat <<'USAGE'
Usage: trello-pull.sh <command> [args...]

Commands:
  list [list-name]           Show cards in triage list (default: $TRELLO_LIST_TRIAGE)
  pull [card-id] [move-to]   Pull triage cards into beads
                              - Creates bead, adds 'bead' label to card, moves to Backlog
                              - Skipped cards stay in Triage with move suggestions
                              card-id: optional, pull only this card
                              move-to: optional, override destination (default: Backlog)
  pull-all [move-to]         Pull all triage cards (shorthand)
  help                       Show this help

Environment variables:
  TRELLO_LIST_TRIAGE   Triage column name (default: "Triage")
  TRELLO_LIST_BUGS     Bugs column name (default: "Bugs")
  TRELLO_LIST_BACKLOG  Backlog column name (default: "Backlog")
  TRELLO_BEAD_LABEL    Label added to pulled cards (default: "bead")

Examples:
  trello-pull.sh list                          # Show triage cards
  trello-pull.sh pull                          # Pull all → label + move to Backlog
  trello-pull.sh pull "" "Icebox"              # Pull all → label + move to Icebox
  trello-pull.sh pull 69b8b8d7...             # Pull one card
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
