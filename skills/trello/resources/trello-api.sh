#!/usr/bin/env bash
# trello-api.sh — Lightweight Trello REST API helper
# Requires: TRELLO_API_KEY, TRELLO_TOKEN env vars
# Optional: TRELLO_BOARD_ID (for board-specific commands)
set -euo pipefail

BASE_URL="https://api.trello.com/1"

die() { echo "ERROR: $*" >&2; exit 1; }

check_auth() {
  [[ -n "${TRELLO_API_KEY:-}" ]] || die "TRELLO_API_KEY not set"
  [[ -n "${TRELLO_TOKEN:-}" ]]   || die "TRELLO_TOKEN not set"
}

auth_params() {
  echo "key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}"
}

require_board() {
  [[ -n "${TRELLO_BOARD_ID:-}" ]] || die "TRELLO_BOARD_ID not set"
}

# Resolve a list name to its ID on the current board
resolve_list_id() {
  local name="$1"
  require_board
  curl -sf "${BASE_URL}/boards/${TRELLO_BOARD_ID}/lists?$(auth_params)" \
    | jq -r --arg name "$name" '.[] | select(.name == $name) | .id'
}

cmd_boards() {
  echo "Fetching your boards..."
  curl -sf "${BASE_URL}/members/me/boards?$(auth_params)&fields=name,url,shortUrl" \
    | jq -r '.[] | "\(.name)\t\(.id)\t\(.shortUrl)"' \
    | column -t -s $'\t'
}

cmd_lists() {
  require_board
  curl -sf "${BASE_URL}/boards/${TRELLO_BOARD_ID}/lists?$(auth_params)&fields=name" \
    | jq -r '.[] | "\(.name)\t\(.id)"' \
    | column -t -s $'\t'
}

cmd_cards() {
  local list_name="${1:-}"
  require_board

  if [[ -z "$list_name" ]]; then
    # All cards on board
    curl -sf "${BASE_URL}/boards/${TRELLO_BOARD_ID}/cards?$(auth_params)&fields=name,idList,labels,desc,shortUrl" \
      | jq '.'
  else
    local list_id
    list_id=$(resolve_list_id "$list_name")
    [[ -n "$list_id" ]] || die "List not found: $list_name"
    curl -sf "${BASE_URL}/lists/${list_id}/cards?$(auth_params)&fields=name,labels,desc,shortUrl" \
      | jq '.'
  fi
}

cmd_cards_summary() {
  local list_name="${1:-}"
  require_board

  if [[ -z "$list_name" ]]; then
    curl -sf "${BASE_URL}/boards/${TRELLO_BOARD_ID}/cards?$(auth_params)&fields=name,idList,labels,shortUrl" \
      | jq -r '.[] | "\(.name)\t\(.labels | map(.name) | join(","))\t\(.shortUrl)"' \
      | column -t -s $'\t'
  else
    local list_id
    list_id=$(resolve_list_id "$list_name")
    [[ -n "$list_id" ]] || die "List not found: $list_name"
    curl -sf "${BASE_URL}/lists/${list_id}/cards?$(auth_params)&fields=name,labels,shortUrl" \
      | jq -r '.[] | "\(.name)\t\(.labels | map(.name) | join(","))\t\(.shortUrl)"' \
      | column -t -s $'\t'
  fi
}

cmd_card() {
  local card_id="$1"
  [[ -n "$card_id" ]] || die "Usage: trello-api.sh card <card-id>"
  curl -sf "${BASE_URL}/cards/${card_id}?$(auth_params)&fields=name,desc,labels,idList,shortUrl" \
    | jq '.'
}

cmd_move() {
  local card_id="$1"
  local target_list_name="$2"
  [[ -n "$card_id" ]] || die "Usage: trello-api.sh move <card-id> <list-name>"
  [[ -n "$target_list_name" ]] || die "Usage: trello-api.sh move <card-id> <list-name>"

  require_board
  local list_id
  list_id=$(resolve_list_id "$target_list_name")
  [[ -n "$list_id" ]] || die "List not found: $target_list_name"

  curl -sf -X PUT "${BASE_URL}/cards/${card_id}?$(auth_params)" \
    -H "Content-Type: application/json" \
    -d "{\"idList\": \"${list_id}\"}" \
    | jq '{id, name, idList}'
  echo "Moved card to: $target_list_name"
}

cmd_create() {
  local list_name="$1"
  local title="$2"
  local desc="${3:-}"
  [[ -n "$list_name" ]] || die "Usage: trello-api.sh create <list-name> <title> [description]"
  [[ -n "$title" ]] || die "Usage: trello-api.sh create <list-name> <title> [description]"

  require_board
  local list_id
  list_id=$(resolve_list_id "$list_name")
  [[ -n "$list_id" ]] || die "List not found: $list_name"

  local payload
  payload=$(jq -n --arg name "$title" --arg desc "$desc" --arg idList "$list_id" \
    '{name: $name, desc: $desc, idList: $idList}')

  curl -sf -X POST "${BASE_URL}/cards?$(auth_params)" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    | jq '{id, name, shortUrl}'
}

cmd_labels() {
  require_board
  curl -sf "${BASE_URL}/boards/${TRELLO_BOARD_ID}/labels?$(auth_params)" \
    | jq -r '.[] | "\(.name)\t\(.color)\t\(.id)"' \
    | column -t -s $'\t'
}

cmd_help() {
  cat <<'USAGE'
Usage: trello-api.sh <command> [args...]

Commands:
  boards                      List all your boards (name, id, url)
  lists                       List columns on the board
  cards [list-name]           Cards as JSON (all or in a specific list)
  cards-summary [list-name]   Cards as one-line summary table
  card <card-id>              Show a single card detail
  move <card-id> <list-name>  Move a card to a different list
  create <list> <title> [desc] Create a new card in a list
  labels                      List labels on the board
  list-id <list-name>         Resolve a list name to its ID

Environment variables:
  TRELLO_API_KEY   (required) Your Trello API key
  TRELLO_TOKEN     (required) Your Trello auth token
  TRELLO_BOARD_ID  (required for most commands) Board ID
USAGE
}

# --- main ---
command="${1:-help}"
shift || true

case "$command" in
  help|--help|-h) cmd_help; exit 0 ;;
esac

check_auth

case "$command" in
  boards)        cmd_boards ;;
  lists)         cmd_lists ;;
  cards)         cmd_cards "${1:-}" ;;
  cards-summary) cmd_cards_summary "${1:-}" ;;
  card)          cmd_card "${1:-}" ;;
  move)          cmd_move "${1:-}" "${2:-}" ;;
  create)        cmd_create "${1:-}" "${2:-}" "${3:-}" ;;
  labels)        cmd_labels ;;
  list-id)       resolve_list_id "${1:-}" ;;
  *)             die "Unknown command: $command. Run with 'help' for usage." ;;
esac
