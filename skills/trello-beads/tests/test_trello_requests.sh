#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPTS="$TEST_DIR/../scripts"
API="$SCRIPTS/trello-api.sh"
SYNC="$SCRIPTS/trello-sync.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/curl"
REAL_JQ=$(command -v jq)
export REAL_JQ

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

cat >"$TMP/bin/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
set -euo pipefail

original_args=("$@")
[[ "${original_args[0]:-}" == "--disable" ]] || {
  printf 'curl must disable user configuration before every request\n' >&2
  exit 2
}

has_arg() {
  local expected="$1"
  local arg
  for arg in "${original_args[@]}"; do
    [[ "$arg" != "$expected" ]] || return 0
  done
  return 1
}

require_arg() {
  has_arg "$1" || {
    printf 'missing curl argument for %s: %s\n' "$url" "$1" >&2
    exit 3
  }
}

counter_file="$FAKE_CURL_DIR/counter"
counter=0
[[ ! -f "$counter_file" ]] || counter=$(<"$counter_file")
counter=$((counter + 1))
printf '%s\n' "$counter" >"$counter_file"

printf '%q ' "$@" >"$FAKE_CURL_DIR/$counter.args"
printf '\n' >>"$FAKE_CURL_DIR/$counter.args"
cat >"$FAKE_CURL_DIR/$counter.config"

method=GET
url=
while (($#)); do
  case "$1" in
    --request|-X)
      method=$2
      shift 2
      ;;
    https://*)
      url=$1
      shift
      ;;
    *)
      shift
      ;;
  esac
done

case "$method $url" in
  "GET https://api.trello.com/1/members/me/boards"*)
    require_arg --get
    require_arg 'fields=name,url,shortUrl'
    printf '%s\n' '[{"id":"board-id","name":"Board one","shortUrl":"https://trello.com/b/board-id"}]'
    ;;
  "GET https://api.trello.com/1/cards/card-1/actions"*)
    require_arg --get
    require_arg 'filter=commentCard'
    require_arg 'fields=data,memberCreator'
    printf '%s\n' '[{"memberCreator":{"fullName":"Reviewer"},"data":{"text":"Looks good"}}]'
    ;;
  "GET https://api.trello.com/1/cards/card-1"*)
    require_arg --get
    if ! has_arg 'fields=name,desc,labels,idList,shortUrl' && ! has_arg 'fields=closed,idList,name'; then
      printf 'missing card fields for %s\n' "$url" >&2
      exit 3
    fi
    printf '%s\n' '{"id":"card-1","name":"Card one","desc":"","labels":[],"idList":"todo-list","shortUrl":"https://trello.com/c/card-1","closed":false}'
    ;;
  "GET https://api.trello.com/1/boards/board-id/lists"*)
    require_arg --get
    require_arg 'fields=name'
    if [[ "${FAKE_MALFORMED_LIST_LOOKUP:-0}" == 1 ]]; then
      printf '%s\n' '[{"name":"Done"}]'
    elif [[ "${FAKE_DUPLICATE_LIST_LOOKUP:-0}" == 1 ]]; then
      printf '%s\n' '[{"id":"done-list","name":"Done"},{"id":"other-list","name":"Done"}]'
    else
      printf '%s\n' '[{"id":"done-list","name":"Done"}]'
    fi
    ;;
  "GET https://api.trello.com/1/boards/board-id/cards"*)
    require_arg --get
    if ! has_arg 'fields=name,idList,labels,desc,shortUrl' && ! has_arg 'fields=name,idList,labels,shortUrl'; then
      printf 'missing board card fields for %s\n' "$url" >&2
      exit 3
    fi
    printf '%s\n' '[{"id":"card-1","name":"Card one","desc":"","labels":[],"idList":"todo-list","shortUrl":"https://trello.com/c/card-1"}]'
    ;;
  "GET https://api.trello.com/1/boards/board-id/labels"*)
    if [[ "${FAKE_MALFORMED_LABEL_LOOKUP:-0}" == 1 ]]; then
      printf '%s\n' '[{"name":"bead","color":"sky"}]'
    elif [[ "${FAKE_DUPLICATE_LABEL_LOOKUP:-0}" == 1 ]]; then
      printf '%s\n' '[{"id":"label-id","name":"bead","color":"sky"},{"id":"other-label","name":"bead","color":"blue"}]'
    else
      printf '%s\n' '[{"id":"label-id","name":"bead","color":"sky"}]'
    fi
    ;;
  "GET https://api.trello.com/1/lists/done-list/cards"*)
    require_arg --get
    require_arg 'filter=all'
    require_arg 'fields=id'
    printf '%s\n' '[]'
    ;;
  "POST https://api.trello.com/1/cards/card-1/idLabels?value=label-id"*)
    printf '%s\n' '{}'
    ;;
  "POST https://api.trello.com/1/cards/card-1/actions/comments"*)
    require_arg -d
    printf '%s\n' '{"id":"comment-id","type":"commentCard","data":{"text":"New comment"}}'
    ;;
  "POST https://api.trello.com/1/cards")
    require_arg -d
    printf '%s\n' '{"id":"new-card","name":"New card","shortUrl":"https://trello.com/c/new-card"}'
    ;;
  "PUT https://api.trello.com/1/cards/card-1"*)
    require_arg -d
    printf '%s\n' '{"id":"card-1","name":"Card one","idList":"done-list"}'
    ;;
  *)
    printf 'unexpected fake curl request: %s %s\n' "$method" "$url" >&2
    exit 2
    ;;
esac
FAKE_CURL
chmod 0755 "$TMP/bin/curl"

cat >"$TMP/bin/jq" <<'FAKE_JQ'
#!/usr/bin/env bash
set -euo pipefail
printf '%q ' "$@" >>"$FAKE_JQ_LOG"
printf '\n' >>"$FAKE_JQ_LOG"
exec "$REAL_JQ" "$@"
FAKE_JQ
chmod 0755 "$TMP/bin/jq"

cat >"$TMP/bin/bd" <<'FAKE_BD'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  list)
    if [[ "$*" == *'--json'* ]]; then
      printf '%s\n' '[]'
    else
      printf '%s\n' 'skills-test · Card one   [closed]'
    fi
    ;;
  show)
    cat <<'BEAD'
✓ skills-test · Card one   [closed]
External: trello-card-1
BEAD
    ;;
  *)
    exit 2
    ;;
esac
FAKE_BD
chmod 0755 "$TMP/bin/bd"

export PATH="$TMP/bin:$PATH"
export FAKE_CURL_DIR="$TMP/curl"
export FAKE_JQ_LOG="$TMP/jq.args"
mkdir -p "$TMP/home"
printf '%s\n' 'trace-ascii = -' >"$TMP/home/.curlrc"
export HOME="$TMP/home"
export TRELLO_API_KEY='key+/?:& value'
export TRELLO_TOKEN='token&=% /?value'
export TRELLO_BOARD_ID='board-id'
export TRELLO_LIST_DONE='Done'

count_mutations() {
  { grep -hE -- '--request (POST|PUT)' "$TMP/curl"/*.args 2>/dev/null || true; } \
    | wc -l | tr -d '[:space:]'
}

stdout="$TMP/stdout"
stderr="$TMP/stderr"
"$API" boards >"$stdout" 2>"$stderr"
"$API" lists >>"$stdout" 2>>"$stderr"
"$API" cards >>"$stdout" 2>>"$stderr"
"$API" cards-summary >>"$stdout" 2>>"$stderr"
"$API" card card-1 >>"$stdout" 2>>"$stderr"
"$API" labels >>"$stdout" 2>>"$stderr"
"$API" list-id Done >>"$stdout" 2>>"$stderr"
"$API" comments card-1 >>"$stdout" 2>>"$stderr"

mutations_before=$(count_mutations)
"$API" create Done 'New card' 'New description' >>"$stdout" 2>>"$stderr"
"$API" add-label card-1 bead sky >>"$stdout" 2>>"$stderr"
"$API" comment card-1 'New comment' >>"$stdout" 2>>"$stderr"
"$API" move card-1 Done >>"$stdout" 2>>"$stderr"
[[ "$(count_mutations)" == "$mutations_before" ]] || fail 'plan-only API commands performed mutations'

requests_before=$(<"$TMP/curl/counter")
if "$API" move card-1 Done --aply >>"$stdout" 2>>"$stderr"; then
  fail 'malformed apply option was accepted'
fi
[[ "$(<"$TMP/curl/counter")" == "$requests_before" ]] || fail 'malformed option made an API request'

"$API" create Done 'New card' 'New description' --apply >>"$stdout" 2>>"$stderr"
"$API" add-label card-1 bead sky --apply >>"$stdout" 2>>"$stderr"
"$API" comment card-1 'New comment' --apply >>"$stdout" 2>>"$stderr"
"$API" move card-1 Done --apply >>"$stdout" 2>>"$stderr"
"$SYNC" sync --dry-run >>"$stdout" 2>>"$stderr"

for malformed_lookup in \
  FAKE_MALFORMED_LIST_LOOKUP \
  FAKE_DUPLICATE_LIST_LOOKUP; do
  mutations_before=$(count_mutations)
  if env "$malformed_lookup=1" "$API" move card-1 Done --apply >>"$stdout" 2>>"$stderr"; then
    fail "$malformed_lookup was accepted for move apply"
  fi
  [[ "$(count_mutations)" == "$mutations_before" ]] \
    || fail "$malformed_lookup performed a mutation"
done

for malformed_lookup in \
  FAKE_MALFORMED_LABEL_LOOKUP \
  FAKE_DUPLICATE_LABEL_LOOKUP; do
  mutations_before=$(count_mutations)
  if env "$malformed_lookup=1" "$API" add-label card-1 bead sky --apply >>"$stdout" 2>>"$stderr"; then
    fail "$malformed_lookup was accepted for add-label apply"
  fi
  [[ "$(count_mutations)" == "$mutations_before" ]] \
    || fail "$malformed_lookup performed a mutation"
done

grep -Fq 'Board one' "$stdout" || fail 'board read behavior was not preserved'
grep -Fq 'WOULD CREATE: New card in Done' "$stdout" || fail 'create plan was not rendered'
grep -Fq "WOULD ADD LABEL: 'bead' to card card-1" "$stdout" || fail 'label plan was not rendered'
grep -Fq 'WOULD COMMENT on card card-1' "$stdout" || fail 'comment plan was not rendered'
grep -Fq 'WOULD MOVE: card-1 → Done' "$stdout" || fail 'move plan was not rendered'
grep -Fq 'New card' "$stdout" || fail 'card creation apply behavior was not preserved'
grep -Fq "Added label 'bead' to card" "$stdout" || fail 'label mutation apply behavior was not preserved'
grep -Fq 'New comment' "$stdout" || fail 'comment mutation apply behavior was not preserved'
grep -Fq 'WOULD MOVE: Card one → Done' "$stdout" || fail 'sync dry-run did not cover the shared request helper'

expected_key='key%2B%2F%3F%3A%26%20value'
expected_token='token%26%3D%25%20%2F%3Fvalue'
request_count=$(<"$TMP/curl/counter")
((request_count >= 18)) || fail "expected at least eighteen mocked requests, got $request_count"

for args in "$TMP/curl"/*.args; do
  grep -Eq '^--disable --config - ' "$args" || fail "curl did not disable user config before protected stdin config: $args"
  ! grep -Fq "$TRELLO_API_KEY" "$args" || fail "API key leaked into curl argv: $args"
  ! grep -Fq "$TRELLO_TOKEN" "$args" || fail "token leaked into curl argv: $args"
  ! grep -Eq '[?&](key|token)=' "$args" || fail "credentials remained in a request URL: $args"
done

for config in "$TMP/curl"/*.config; do
  grep -Fq 'Authorization: OAuth oauth_consumer_key=' "$config" || fail "missing OAuth Authorization header: $config"
  grep -Fq "$expected_key" "$config" || fail "API key was not OAuth-encoded: $config"
  grep -Fq "$expected_token" "$config" || fail "token was not OAuth-encoded: $config"
  ! grep -Fq "$TRELLO_API_KEY" "$config" || fail "raw API key was not encoded: $config"
  ! grep -Fq "$TRELLO_TOKEN" "$config" || fail "raw token was not encoded: $config"
done

for output in "$stdout" "$stderr"; do
  ! grep -Fq "$TRELLO_API_KEY" "$output" || fail "API key leaked to command output"
  ! grep -Fq "$TRELLO_TOKEN" "$output" || fail "token leaked to command output"
  ! grep -Fq "$expected_key" "$output" || fail "encoded API key leaked to command output"
  ! grep -Fq "$expected_token" "$output" || fail "encoded token leaked to command output"
done

! grep -Fq "$TRELLO_API_KEY" "$FAKE_JQ_LOG" || fail 'API key leaked into jq argv'
! grep -Fq "$TRELLO_TOKEN" "$FAKE_JQ_LOG" || fail 'token leaked into jq argv'

api_curl_calls=$(grep -Ec '(^|[|&;])[[:space:]]*(command[[:space:]]+)?curl[[:space:]]' "$API" || true)
sync_curl_calls=$(grep -Ec '(^|[|&;])[[:space:]]*(command[[:space:]]+)?curl[[:space:]]' "$SYNC" || true)
[[ "$api_curl_calls" -eq 1 ]] || fail "trello-api.sh must have one curl invocation, found $api_curl_calls"
[[ "$sync_curl_calls" -eq 0 ]] || fail "trello-sync.sh bypasses the shared request helper"

printf '%s\n' 'trello request security tests passed'
