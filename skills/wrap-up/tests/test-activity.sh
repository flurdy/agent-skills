#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPT="$TEST_DIR/../scripts/activity.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local text=$1
  grep -Fq -- "$text" "$TMP/output" || fail "expected '$text' in output"
}

assert_not_contains() {
  local text=$1
  if grep -Fq -- "$text" "$TMP/output"; then
    fail "did not expect '$text' in output"
  fi
}

assert_section_value() {
  local section=$1
  local expected=$2
  local actual
  actual=$(awk -v marker="---${section}---" '$0 == marker { getline; print; exit }' "$TMP/output")
  [[ "$actual" == "$expected" ]] || fail "expected ${section} '$expected', got '$actual'"
}

section_body() {
  local section=$1
  awk -v marker="---${section}---" '
    $0 == marker { emit=1; next }
    /^---.*---$/ { emit=0 }
    emit
  ' "$TMP/output"
}

assert_section_contains() {
  local section=$1
  local text=$2
  section_body "$section" | grep -Fq -- "$text" || fail "expected '$text' in ${section}"
}

assert_section_not_contains() {
  local section=$1
  local text=$2
  if section_body "$section" | grep -Fq -- "$text"; then
    fail "did not expect '$text' in ${section}"
  fi
}

make_repo() {
  local dir=$1
  local message=$2
  git init -q "$dir"
  git -C "$dir" config user.name Tester
  git -C "$dir" config user.email tester@example.com
  printf '%s\n' "$message" >"$dir/file.txt"
  git -C "$dir" add file.txt
  git -C "$dir" commit -qm "$message"
}

make_dated_commit() {
  local dir=$1
  local message=$2
  local timestamp=$3
  printf '%s\n' "$message" >>"$dir/file.txt"
  git -C "$dir" add file.txt
  GIT_AUTHOR_DATE="$timestamp" GIT_COMMITTER_DATE="$timestamp" \
    git -C "$dir" commit -qm "$message"
}

mkdir -p "$TMP/bin" "$TMP/workspace/repos"
make_repo "$TMP/workspace" "workspace commit"
make_repo "$TMP/workspace/repos/service" "service commit"
make_repo "$TMP/workspace/repos/no-author" "unattributed commit"
git -C "$TMP/workspace/repos/no-author" config user.email ''
mkdir -p "$TMP/workspace/.beads" "$TMP/workspace/repos/service/.beads" \
  "$TMP/workspace/repos/no-author/.beads"
printf 'services=repos/service,repos/no-author,repos/missing\n' >"$TMP/workspace/.mgit.conf"

cat >"$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "auth" ]]; then
  exit 0
fi
printf '%s\n' "$*" >>"$GH_CALLS"
if [[ "${GH_FAIL:-}" == "1" && " $* " == *" --merged-at="* ]]; then
  exit 7
fi
if [[ "${GH_WINDOW_FIXTURE:-}" == "1" ]]; then
  if [[ " $* " == *" --created="* ]]; then
    printf '%s\n' '[{"number":1,"title":"before created","createdAt":"2026-07-31T03:59:59Z"},{"number":2,"title":"inside created","createdAt":"2026-07-31T04:00:00Z"},{"number":3,"title":"end created","createdAt":"2026-08-01T04:00:00Z"}]'
  elif [[ " $* " == *" --merged-at="* ]]; then
    printf '%s\n' '[{"number":4,"title":"inside merged","closedAt":"2026-07-31T16:00:00Z"},{"number":5,"title":"end merged","closedAt":"2026-08-01T04:00:00Z"}]'
  else
    printf '%s\n' '[{"number":6,"title":"inside closed","closedAt":"2026-07-31T20:00:00Z"},{"number":7,"title":"before closed","closedAt":"2026-07-31T03:59:59Z"}]'
  fi
else
  printf '[]\n'
fi
EOF
chmod +x "$TMP/bin/gh"

cat >"$TMP/bin/bd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir=""
if [[ "${1:-}" == "-C" ]]; then
  dir=$2
  shift 2
fi
printf '%s\n' "$*" >>"$BD_CALLS"
readonly=0
for arg in "$@"; do
  [[ "$arg" == "--readonly" ]] && readonly=1
done
[[ $readonly -eq 1 ]] || { printf 'missing --readonly\n' >&2; exit 9; }
id=$(basename "$dir")
id=${id:-solo}
if [[ "$id" == "no-author" ]]; then
  printf 'not-json\n'
  exit 0
fi
if [[ "${BD_FAIL_CLOSED:-}" == "1" && " $* " == *" --closed-after="* ]]; then
  exit 7
fi
if [[ "${BD_MANY:-}" == "1" ]]; then
  if [[ " $* " == *" --created-after="* ]]; then
    python3 - <<'PY'
import json
print(json.dumps([{"id": f"many-{number}", "status": "open", "created_at": "2026-08-03T12:00:00Z"} for number in range(1, 52)]))
PY
  elif [[ " $* " == *" --closed-after="* ]]; then
    printf '[]\n'
  else
    printf '[]\n'
  fi
  exit 0
fi
if [[ "${BD_WINDOW_FIXTURE:-}" == "1" ]]; then
  if [[ " $* " == *" --created-after="* ]]; then
    printf '%s\n' '[{"id":"before-created","status":"open","created_at":"2026-07-31T03:59:59Z"},{"id":"closed-created","status":"closed","created_at":"2026-07-31T04:00:00Z"},{"id":"open-created","status":"open","created_at":"2026-07-31T12:00:00Z"},{"id":"end-created","status":"open","created_at":"2026-08-01T04:00:00Z"}]'
  elif [[ " $* " == *" --closed-after="* ]]; then
    printf '%s\n' '[{"id":"start-closed","status":"closed","closed_at":"2026-07-31T04:00:00Z"},{"id":"inside-closed","status":"closed","closed_at":"2026-07-31T20:00:00Z"},{"id":"end-closed","status":"closed","closed_at":"2026-08-01T04:00:00Z"}]'
  else
    printf '[]\n'
  fi
  exit 0
fi
for arg in "$@"; do
  case "$arg" in
    --created-after=*) field=created_at; after=${arg#*=} ;;
    --closed-after=*) field=closed_at; after=${arg#*=} ;;
  esac
done
if [[ -n "${field:-}" ]]; then
  python3 - "$id" "$field" "$after" <<'PY'
from datetime import datetime, timedelta
import json
import sys
repo, field, after = sys.argv[1:]
timestamp = datetime.fromisoformat(after.replace("Z", "+00:00")) + timedelta(seconds=1)
print(json.dumps([{"id": f"{repo}-today", "title": f"Activity in {repo}", "status": "open", field: timestamp.isoformat().replace("+00:00", "Z")}]))
PY
else
  printf '[{"id":"%s-today","title":"Activity in %s"}]\n' "$id" "$id"
fi
EOF
chmod +x "$TMP/bin/bd"

export GH_CALLS="$TMP/gh-calls"
export BD_CALLS="$TMP/bd-calls"
(
  cd "$TMP/workspace/repos/service"
  PATH="$TMP/bin:$PATH" MGIT_ROOT="$TMP/workspace" "$SCRIPT" --workspace >"$TMP/output"
)

assert_contains '---SCOPE---'
assert_contains 'WORKSPACE'
assert_contains '---REPOSITORIES---'
assert_contains "workspace|$TMP/workspace"
assert_contains "repos/service|$TMP/workspace/repos/service"
assert_contains "repos/no-author|$TMP/workspace/repos/no-author"
assert_contains 'Unavailable configured workspace member: repos/missing'
assert_contains 'repos/no-author|NO_AUTHOR'
assert_contains 'workspace|workspace|'
assert_contains 'repos/service|service|'
assert_contains 'workspace|[{"id":"workspace-today"'
assert_contains 'repos/service|[{"id":"service-today"'
assert_contains 'repos/no-author|ERROR'
[[ $(wc -l <"$GH_CALLS") -eq 3 ]] || fail "expected one global three-query GitHub collection"

(
  cd "$TMP/workspace/repos/service"
  PATH="$TMP/bin:$PATH" MGIT_ROOT="$TMP/workspace" TZ=America/New_York \
    ACTIVITY_TODAY=2026-08-03 GH_FAIL=1 GH_WINDOW_FIXTURE=1 \
    "$SCRIPT" --workspace --previous-workday >"$TMP/output"
)
assert_contains 'ERROR'
assert_contains 'Merged-PR query failed.'
assert_section_contains PRS-CREATED 'inside created'
assert_section_contains PRS-CLOSED-UNMERGED 'inside closed'

make_repo "$TMP/solo" "solo commit"
mkdir -p "$TMP/solo/.beads"
(
  cd "$TMP/solo"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' "$SCRIPT" --workspace >"$TMP/output"
)
assert_contains 'CURRENT_REPO'
assert_contains "solo|$TMP/solo"
assert_contains 'solo|solo|'

: >"$BD_CALLS"
(
  cd "$TMP/solo"
  PATH="$TMP/bin:$PATH" TZ=America/New_York ACTIVITY_TODAY=2026-08-03 \
    "$SCRIPT" >"$TMP/output"
)
if grep -Fq -- '---SCOPE---' "$TMP/output" || grep -Fq -- '---BEADS-CREATED---' "$TMP/output"; then
  fail 'default activity schema must not gain workspace-only sections'
fi
assert_contains '---BEADS-STALE-CANDIDATES---'
assert_section_contains BEADS-CREATED-TODAY 'solo-today'
grep -Fq -- '--created-after=2026-08-03T03:59:59Z --created-before=2026-08-04T04:00:00Z' "$BD_CALLS" || fail 'default Beads created query did not use the exact local window'
grep -Fq -- '--closed-after=2026-08-03T03:59:59Z --closed-before=2026-08-04T04:00:00Z' "$BD_CALLS" || fail 'default Beads closed query did not use the exact local window'

mkdir "$TMP/no-git"
(
  cd "$TMP/no-git"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' "$SCRIPT" --workspace >"$TMP/output"
)
assert_contains 'NO_GIT'
assert_contains 'CURRENT_REPO'
assert_contains '---PRS-CREATED---'

make_repo "$TMP/window" "setup commit"
mkdir -p "$TMP/window/.beads"
make_dated_commit "$TMP/window" "friday activity" "2026-07-31T12:00:00Z"
make_dated_commit "$TMP/window" "saturday boundary" "2026-08-01T04:00:00Z"
make_dated_commit "$TMP/window" "sunday activity" "2026-08-02T12:00:00Z"
: >"$GH_CALLS"
: >"$BD_CALLS"
(
  cd "$TMP/window"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' TZ=America/New_York ACTIVITY_TODAY=2026-08-03 \
    GH_WINDOW_FIXTURE=1 BD_WINDOW_FIXTURE=1 \
    "$SCRIPT" --workspace --previous-workday >"$TMP/output"
)
assert_section_value DATE '2026-07-31'
assert_section_value WINDOW-START '2026-07-31T00:00:00-04:00'
assert_section_value WINDOW-END '2026-08-01T00:00:00-04:00'
assert_contains 'friday activity'
assert_not_contains 'saturday boundary'
assert_not_contains 'sunday activity'
grep -Fq -- '--created=2026-07-31..2026-08-01' "$GH_CALLS" || fail 'GitHub created query did not cover the local Friday UTC range'
grep -Fq -- '--merged-at=2026-07-31..2026-08-01' "$GH_CALLS" || fail 'GitHub merged query did not cover the local Friday UTC range'
grep -Fq -- '--closed=2026-07-31..2026-08-01' "$GH_CALLS" || fail 'GitHub closed query did not cover the local Friday UTC range'
assert_section_contains PRS-CREATED 'inside created'
assert_section_not_contains PRS-CREATED 'before created'
assert_section_not_contains PRS-CREATED 'end created'
assert_section_contains PRS-MERGED 'inside merged'
assert_section_not_contains PRS-MERGED 'end merged'
assert_section_contains PRS-CLOSED-UNMERGED 'inside closed'
assert_section_not_contains PRS-CLOSED-UNMERGED 'before closed'
grep -Fq -- '--all --created-after=2026-07-31T03:59:59Z --created-before=2026-08-01T04:00:00Z --limit=0 --json' "$BD_CALLS" || fail 'Beads created query did not cover the complete local Friday UTC range'
grep -Fq -- '--closed-after=2026-07-31T03:59:59Z --closed-before=2026-08-01T04:00:00Z --limit=0 --json' "$BD_CALLS" || fail 'Beads closed query did not cover the complete local Friday UTC range'
assert_section_contains BEADS-CREATED 'closed-created'
assert_section_contains BEADS-CREATED 'open-created'
assert_section_not_contains BEADS-CREATED 'before-created'
assert_section_not_contains BEADS-CREATED 'end-created'
assert_section_contains BEADS-CREATED-TODAY 'open-created'
assert_section_not_contains BEADS-CREATED-TODAY 'closed-created'
assert_section_contains BEADS-CLOSED 'start-closed'
assert_section_contains BEADS-CLOSED 'inside-closed'
assert_section_not_contains BEADS-CLOSED 'end-closed'

(
  cd "$TMP/window"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' TZ=UTC ACTIVITY_TODAY=2026-08-04 \
    "$SCRIPT" --workspace --previous-workday >"$TMP/output"
)
assert_section_value DATE '2026-08-03'
assert_section_value WINDOW-END '2026-08-04T00:00:00+00:00'

(
  cd "$TMP/window"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' TZ=UTC ACTIVITY_TODAY=2026-08-04 BD_FAIL_CLOSED=1 \
    "$SCRIPT" --workspace --previous-workday >"$TMP/output"
)
assert_contains 'window|ERROR'
assert_section_contains BEADS-CREATED 'window-today'
assert_section_not_contains BEADS-CLOSED 'window-today'

(
  cd "$TMP/window"
  PATH="$TMP/bin:$PATH" MGIT_ROOT='' TZ=UTC ACTIVITY_TODAY=2026-08-04 BD_MANY=1 \
    "$SCRIPT" --workspace --previous-workday >"$TMP/output"
)
assert_section_contains BEADS-CREATED 'many-51'

printf 'wrap-up activity tests passed\n'
