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

oauth_encode() {
  printf '%s' "$1" | jq -sRr '@uri'
}

trello_request() {
  local method="$1"
  local path="$2"
  shift 2

  check_auth
  case "$method" in
    GET|POST|PUT) ;;
    *) die "Unsupported Trello request method: $method" ;;
  esac
  [[ "$path" == /* && "$path" != *$'\n'* && "$path" != *$'\r'* ]] \
    || die "Trello request path must be a single-line absolute path"

  local encoded_key encoded_token
  encoded_key=$(oauth_encode "$TRELLO_API_KEY")
  encoded_token=$(oauth_encode "$TRELLO_TOKEN")

  printf 'header = "Authorization: OAuth oauth_consumer_key=\\"%s\\", oauth_token=\\"%s\\""\n' \
    "$encoded_key" "$encoded_token" \
    | curl --disable --config - --silent --show-error --fail --request "$method" \
      "${BASE_URL}${path}" "$@"
}

require_board() {
  [[ -n "${TRELLO_BOARD_ID:-}" ]] || die "TRELLO_BOARD_ID not set"
}

validate_apply_mode() {
  case "${1:-}" in
    ""|--apply) ;;
    *) die "Unknown mutation option: $1. Use --apply only after reviewing the plan." ;;
  esac
}

# Resolve a list name to its ID on the current board
resolve_list_id() {
  local name="$1"
  require_board

  local lists list_id
  lists=$(trello_request GET "/boards/${TRELLO_BOARD_ID}/lists" \
    --get --data-urlencode "fields=name")
  if ! jq -e '
    type == "array" and
    all(.[];
      type == "object" and
      (.name | type == "string") and
      (.id | type == "string" and length > 0)
    )
  ' <<<"$lists" >/dev/null; then
    die "Trello returned an invalid list lookup payload"
  fi
  if ! list_id=$(jq -er --arg name "$name" '
    map(select(.name == $name)) |
    if length == 1 then .[0].id else empty end
  ' <<<"$lists"); then
    die "Expected exactly one Trello list named: $name"
  fi
  echo "$list_id"
}

cmd_boards() {
  echo "Fetching your boards..."
  trello_request GET "/members/me/boards" --get --data-urlencode "fields=name,url,shortUrl" \
    | jq -r '.[] | "\(.name)\t\(.id)\t\(.shortUrl)"' \
    | column -t -s $'\t'
}

cmd_lists() {
  require_board
  trello_request GET "/boards/${TRELLO_BOARD_ID}/lists" --get --data-urlencode "fields=name" \
    | jq -r '.[] | "\(.name)\t\(.id)"' \
    | column -t -s $'\t'
}

cmd_cards() {
  local list_name="${1:-}"
  require_board

  if [[ -z "$list_name" ]]; then
    # All cards on board
    trello_request GET "/boards/${TRELLO_BOARD_ID}/cards" \
      --get --data-urlencode "fields=name,idList,labels,desc,shortUrl" | jq '.'
  else
    local list_id
    list_id=$(resolve_list_id "$list_name")
    [[ -n "$list_id" ]] || die "List not found: $list_name"
    trello_request GET "/lists/${list_id}/cards" \
      --get --data-urlencode "fields=name,labels,desc,shortUrl" | jq '.'
  fi
}

cmd_cards_summary() {
  local list_name="${1:-}"
  require_board

  if [[ -z "$list_name" ]]; then
    trello_request GET "/boards/${TRELLO_BOARD_ID}/cards" \
      --get --data-urlencode "fields=name,idList,labels,shortUrl" \
      | jq -r '.[] | "\(.name)\t\(.labels | map(.name) | join(","))\t\(.shortUrl)"' \
      | column -t -s $'\t'
  else
    local list_id
    list_id=$(resolve_list_id "$list_name")
    [[ -n "$list_id" ]] || die "List not found: $list_name"
    trello_request GET "/lists/${list_id}/cards" \
      --get --data-urlencode "fields=name,labels,shortUrl" \
      | jq -r '.[] | "\(.name)\t\(.labels | map(.name) | join(","))\t\(.shortUrl)"' \
      | column -t -s $'\t'
  fi
}

cmd_card() {
  local card_id="$1"
  [[ -n "$card_id" ]] || die "Usage: trello-api.sh card <card-id>"
  trello_request GET "/cards/${card_id}" \
    --get --data-urlencode "fields=name,desc,labels,idList,shortUrl" | jq '.'
}

cmd_move() {
  (($# >= 2 && $# <= 3)) || die "Usage: trello-api.sh move <card-id> <list-name> [--apply]"
  local card_id="$1"
  local target_list_name="$2"
  local mode="${3:-}"
  [[ -n "$card_id" && -n "$target_list_name" ]] \
    || die "Usage: trello-api.sh move <card-id> <list-name> [--apply]"
  validate_apply_mode "$mode"

  if [[ "$mode" != "--apply" ]]; then
    echo "WOULD MOVE: $card_id → $target_list_name"
    return 0
  fi

  require_board
  local list_id
  list_id=$(resolve_list_id "$target_list_name")
  [[ -n "$list_id" ]] || die "List not found: $target_list_name"

  trello_request PUT "/cards/${card_id}" \
    -H "Content-Type: application/json" \
    -d "{\"idList\": \"${list_id}\"}" \
    | jq '{id, name, idList}'
  echo "Moved card to: $target_list_name"
}

cmd_create() {
  (($# >= 2 && $# <= 4)) \
    || die "Usage: trello-api.sh create <list-name> <title> [description] [--apply]"
  local list_name="$1"
  local title="$2"
  local desc=""
  local mode=""
  [[ -n "$list_name" && -n "$title" ]] \
    || die "Usage: trello-api.sh create <list-name> <title> [description] [--apply]"

  if (($# == 3)); then
    if [[ "$3" == --* ]]; then mode="$3"; else desc="$3"; fi
  elif (($# == 4)); then
    desc="$3"
    mode="$4"
  fi
  validate_apply_mode "$mode"

  if [[ "$mode" != "--apply" ]]; then
    echo "WOULD CREATE: $title in $list_name"
    return 0
  fi

  require_board
  local list_id
  list_id=$(resolve_list_id "$list_name")
  [[ -n "$list_id" ]] || die "List not found: $list_name"

  local payload
  payload=$(jq -n --arg name "$title" --arg desc "$desc" --arg idList "$list_id" \
    '{name: $name, desc: $desc, idList: $idList}')

  trello_request POST "/cards" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    | jq '{id, name, shortUrl}'
}

cmd_labels() {
  require_board
  trello_request GET "/boards/${TRELLO_BOARD_ID}/labels" \
    | jq -r '.[] | "\(.name)\t\(.color)\t\(.id)"' \
    | column -t -s $'\t'
}

# Ensure a label exists on the board (by name), return its ID
ensure_label() {
  local label_name="$1"
  local label_color="${2:-}"
  require_board

  local labels match_count label_id
  labels=$(trello_request GET "/boards/${TRELLO_BOARD_ID}/labels")
  if ! jq -e '
    type == "array" and
    all(.[];
      type == "object" and
      (.name | type == "string") and
      (.id | type == "string" and length > 0)
    )
  ' <<<"$labels" >/dev/null; then
    die "Trello returned an invalid label lookup payload"
  fi

  match_count=$(jq --arg name "$label_name" '[.[] | select(.name == $name)] | length' <<<"$labels")
  if ((match_count > 1)); then
    die "Expected at most one Trello label named: $label_name"
  fi
  if ((match_count == 1)); then
    jq -r --arg name "$label_name" '.[] | select(.name == $name) | .id' <<<"$labels"
    return
  fi

  local payload created_label
  payload=$(jq -n --arg name "$label_name" --arg color "$label_color" '{name: $name, color: $color}')
  created_label=$(trello_request POST "/boards/${TRELLO_BOARD_ID}/labels" \
    -H "Content-Type: application/json" \
    -d "$payload")
  if ! label_id=$(jq -er '
    if type == "object" and (.id | type == "string" and length > 0)
    then .id
    else empty
    end
  ' <<<"$created_label"); then
    die "Trello returned an invalid created-label payload"
  fi
  echo "$label_id"
}

cmd_add_label() {
  (($# >= 2 && $# <= 4)) \
    || die "Usage: trello-api.sh add-label <card-id> <label-name> [color] [--apply]"
  local card_id="$1"
  local label_name="$2"
  local label_color=""
  local mode=""
  [[ -n "$card_id" && -n "$label_name" ]] \
    || die "Usage: trello-api.sh add-label <card-id> <label-name> [color] [--apply]"

  if (($# == 3)); then
    if [[ "$3" == --* ]]; then mode="$3"; else label_color="$3"; fi
  elif (($# == 4)); then
    label_color="$3"
    mode="$4"
  fi
  validate_apply_mode "$mode"

  if [[ "$mode" != "--apply" ]]; then
    echo "WOULD ENSURE LABEL: '$label_name' (color: ${label_color:-none})"
    echo "WOULD ADD LABEL: '$label_name' to card $card_id"
    return 0
  fi

  local label_id
  label_id=$(ensure_label "$label_name" "$label_color")
  [[ -n "$label_id" ]] || die "Could not find or create label: $label_name"

  trello_request POST "/cards/${card_id}/idLabels?value=${label_id}" >/dev/null
  echo "Added label '$label_name' to card"
}

cmd_comment() {
  (($# >= 2 && $# <= 3)) || die "Usage: trello-api.sh comment <card-id> <text> [--apply]"
  local card_id="$1"
  local text="$2"
  local mode="${3:-}"
  [[ -n "$card_id" && -n "$text" ]] || die "Usage: trello-api.sh comment <card-id> <text> [--apply]"
  validate_apply_mode "$mode"

  if [[ "$mode" != "--apply" ]]; then
    echo "WOULD COMMENT on card $card_id: $text"
    return 0
  fi

  trello_request POST "/cards/${card_id}/actions/comments" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$text" '{text: $text}')" \
    | jq '{id, type: .type, text: .data.text}'
}

cmd_comments() {
  local card_id="$1"
  [[ -n "$card_id" ]] || die "Usage: trello-api.sh comments <card-id>"
  trello_request GET "/cards/${card_id}/actions" \
    --get --data-urlencode "filter=commentCard" --data-urlencode "fields=data,memberCreator" \
    | jq '[.[] | {author: .memberCreator.fullName, text: .data.text}]'
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
  move <card-id> <list-name> [--apply]  Plan or apply a card move
  create <list> <title> [desc] [--apply]  Plan or apply card creation
  add-label <card-id> <name> [color] [--apply]  Plan or apply a label
  comment <card-id> <text> [--apply]  Plan or apply a comment
  comments <card-id>          List all comments on a card
  labels                      List labels on the board
  list-id <list-name>         Resolve a list name to its ID

Environment variables:
  TRELLO_API_KEY   (required) Your Trello API key
  TRELLO_TOKEN     (required) Your Trello auth token
  TRELLO_BOARD_ID  (required for most commands) Board ID

Mutations render a plan by default. Rerun with --apply only after confirmation.
USAGE
}

main() {
  local command="${1:-help}"
  shift || true

  case "$command" in
    help|--help|-h) cmd_help; return 0 ;;
  esac

  check_auth

  case "$command" in
    boards)        cmd_boards ;;
    lists)         cmd_lists ;;
    cards)         cmd_cards "${1:-}" ;;
    cards-summary) cmd_cards_summary "${1:-}" ;;
    card)          cmd_card "${1:-}" ;;
    move)          cmd_move "$@" ;;
    create)        cmd_create "$@" ;;
    add-label)     cmd_add_label "$@" ;;
    comment)       cmd_comment "$@" ;;
    comments)      cmd_comments "${1:-}" ;;
    labels)        cmd_labels ;;
    list-id)       resolve_list_id "${1:-}" ;;
    *)             die "Unknown command: $command. Run with 'help' for usage." ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
