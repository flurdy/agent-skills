#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
STATUS="$SKILL_DIR/scripts/status.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

cat >"$TMP/bin/git" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  config) printf '%s\n' 'git@github.com:owner/repo.git' ;;
  branch) printf '%s\n' 'main' ;;
  rev-parse) printf '%s\n' 'local-head' ;;
  *) exit 1 ;;
esac
EOF

cat >"$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$GH_LOG"
if [[ "$1 $2" == "auth status" ]]; then
  exit 0
fi
if [[ "$*" == *'/status'* ]]; then
  printf '%s\n' '{"state":"pending","statuses":[]}'
else
  printf '%s\n' '{"total_count":0,"check_runs":[]}'
fi
EOF

cat >"$TMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
url="${!#}"
case "$url" in
  *'/pipeline?branch=main')
    printf '%s\n' '{"items":[{"id":"newer-id","vcs":{"revision":"newer-sha"}},{"id":"target-id","vcs":{"revision":"target-sha"}}]}'
    ;;
  *'/pipeline/target-id/workflow')
    printf '%s\n' '{"items":[{"id":"target-workflow","status":"running"}]}'
    ;;
  *'/pipeline/newer-id/workflow')
    printf '%s\n' '{"items":[{"id":"wrong-workflow","status":"success"}]}'
    ;;
  *) exit 1 ;;
esac
EOF

chmod +x "$TMP/bin/git" "$TMP/bin/gh" "$TMP/bin/curl"
export GH_LOG="$TMP/gh.log"

output=$(PATH="$TMP/bin:$PATH" CIRCLECI_TOKEN=test "$STATUS" main target-sha)

grep -Fq '"id": "target-id"' <<<"$output" || fail 'did not select the target revision pipeline'
grep -Fq '"id": "target-workflow"' <<<"$output" || fail 'did not fetch workflows for the target pipeline'
if grep -Fq 'wrong-workflow' <<<"$output"; then
    fail 'used the branch latest pipeline instead of the target revision'
fi
grep -Fq 'commits/target-sha/status' "$GH_LOG" || fail 'GitHub status fallback did not use target SHA'
grep -Fq 'commits/target-sha/check-runs' "$GH_LOG" || fail 'GitHub checks fallback did not use target SHA'

missing=$(PATH="$TMP/bin:$PATH" CIRCLECI_TOKEN=test "$STATUS" main absent-sha)
grep -Fq '"pipeline":null' <<<"$missing" || fail 'missing target revision should not fall back to latest pipeline'

: >"$GH_LOG"
latest=$(PATH="$TMP/bin:$PATH" CIRCLECI_TOKEN=test "$STATUS" main)
grep -Fq '"id": "newer-id"' <<<"$latest" || fail 'default status should retain latest branch pipeline behavior'
grep -Fq '"id": "wrong-workflow"' <<<"$latest" || fail 'default status did not fetch latest pipeline workflows'
grep -Fq 'commits/main/status' "$GH_LOG" || fail 'default GitHub status lookup should retain branch behavior'

printf '%s\n' 'circleci-status exact revision tests passed'
