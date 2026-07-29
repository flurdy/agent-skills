#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
HASH_HELPER="$SKILL_DIR/scripts/sha256-stdin.sh"
UTC_HELPER="$SKILL_DIR/scripts/utc-now.sh"
WRITE_HELPER="$SKILL_DIR/scripts/confirmed-bd.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
BD_LOG="$TMP/bd.log"
export BD_LOG

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file=$1 expected=$2
    grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

cat >"$TMP/bin/bd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$BD_LOG"
if [[ $1 == create && $* == *'Fail child'* ]]; then
    printf '%s\n' 'injected create failure' >&2
    exit 17
fi
case "$1" in
    create) printf '%s\n' '{"id":"agents-new"}' ;;
    update) printf '%s\n' '{"id":"agents-existing"}' ;;
    dep) printf '%s\n' '{"status":"ok"}' ;;
    *) exit 9 ;;
esac
EOF
chmod +x "$TMP/bin/bd"
PATH="$TMP/bin:$PATH"
export PATH

expected_hash=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
actual_hash=$(printf 'abc' | "$HASH_HELPER")
[[ $actual_hash == "$expected_hash" ]] || fail "stdin hash mismatch: $actual_hash"
canonical_hash=$(printf 'abc' | "$HASH_HELPER" --canonical-text)
canonical_newline_hash=$(printf 'abc\n' | "$HASH_HELPER" --canonical-text)
canonical_crlf_hash=$(printf 'abc\r\n' | "$HASH_HELPER" --canonical-text)
[[ $canonical_hash == "$canonical_newline_hash" && $canonical_hash == "$canonical_crlf_hash" ]] || \
    fail 'canonical text hashing did not normalize terminal newline and CRLF'

utc_now=$("$UTC_HELPER")
[[ $utc_now =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || \
    fail "invalid UTC timestamp: $utc_now"
set +e
"$UTC_HELPER" --set >"$TMP/utc.out" 2>"$TMP/utc.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "utc helper arguments should exit 2, got $status"

proposal=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
other=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
source_hash=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
metadata="{\"plan_source\":\"docs/plans/example.md\",\"plan_source_sha256\":\"$source_hash\",\"plan_proposal_ref\":\"owner\"}"
create_args=(
    --title 'Create durable outcome'
    --type task
    --priority P2
    --description 'Deliver the outcome. Source plan: docs/plans/example.md'
    --acceptance 'The outcome is observable.'
    --metadata "$metadata"
)

set +e
"$WRITE_HELPER" "$proposal" "$other" create "${create_args[@]}" >"$TMP/mismatch.out" 2>"$TMP/mismatch.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "mismatched confirmation should exit 2, got $status"
[[ ! -s $BD_LOG ]] || fail 'mismatched confirmation invoked bd'
assert_contains "$TMP/mismatch.err" 'confirmed fingerprint does not match proposal'

set +e
"$WRITE_HELPER" "$proposal" "$proposal" close agents-old >"$TMP/forbidden.out" 2>"$TMP/forbidden.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "forbidden action should exit 2, got $status"
[[ ! -s $BD_LOG ]] || fail 'forbidden action invoked bd'
assert_contains "$TMP/forbidden.err" 'unsupported action: close'

"$WRITE_HELPER" "$proposal" "$proposal" preflight-create "${create_args[@]}" >"$TMP/preflight.out"
assert_contains "$BD_LOG" 'create --title Create durable outcome --type task --priority P2'
assert_contains "$BD_LOG" '--dry-run --json'

"$WRITE_HELPER" "$proposal" "$proposal" create "${create_args[@]}" >"$TMP/create.out"
assert_contains "$TMP/create.out" '"id":"agents-new"'
"$WRITE_HELPER" "$proposal" "$proposal" update-type agents-existing >"$TMP/update.out"
"$WRITE_HELPER" "$proposal" "$proposal" set-parent agents-child agents-parent >"$TMP/parent.out"
"$WRITE_HELPER" "$proposal" "$proposal" add-blocker agents-dependent agents-prerequisite >"$TMP/dependency.out"
assert_contains "$BD_LOG" 'update agents-existing --type epic --json'
assert_contains "$BD_LOG" 'update agents-child --parent agents-parent --json'
assert_contains "$BD_LOG" 'dep add agents-dependent agents-prerequisite --type blocks --json'

before=$(wc -l <"$BD_LOG")
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create "${create_args[@]}" --deps agents-other >"$TMP/flags.out" 2>"$TMP/flags.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "unsupported create flag should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'unsupported create flag invoked bd'
assert_contains "$TMP/flags.err" 'unsupported create flag: --deps'

before=$(wc -l <"$BD_LOG")
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Missing metadata' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata '{}' >"$TMP/metadata.out" 2>"$TMP/metadata.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "missing traceability should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'missing traceability invoked bd'
assert_contains "$TMP/metadata.err" 'metadata must contain a valid non-empty plan_source'

before=$(wc -l <"$BD_LOG")
empty_metadata="{\"plan_source\":\"\",\"plan_source_sha256\":\"$source_hash\",\"plan_proposal_ref\":\"\"}"
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Empty metadata' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata "$empty_metadata" >"$TMP/empty-metadata.out" 2>"$TMP/empty-metadata.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "empty traceability should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'empty traceability invoked bd'
assert_contains "$TMP/empty-metadata.err" 'metadata must contain a valid non-empty plan_source'

before=$(wc -l <"$BD_LOG")
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Malformed metadata' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata '{not-json}' >"$TMP/malformed.out" 2>"$TMP/malformed.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "malformed metadata should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'malformed metadata invoked bd'
assert_contains "$TMP/malformed.err" 'metadata must be valid JSON'

before=$(wc -l <"$BD_LOG")
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Array metadata' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata '[]' >"$TMP/array.out" 2>"$TMP/array.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "array metadata should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'array metadata invoked bd'
assert_contains "$TMP/array.err" 'metadata must be a JSON object'

before=$(wc -l <"$BD_LOG")
invalid_hash_metadata='{"plan_source":"docs/plans/example.md","plan_source_sha256":"invalid","plan_proposal_ref":"owner"}'
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Invalid hash' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata "$invalid_hash_metadata" >"$TMP/hash.out" 2>"$TMP/hash.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "invalid source hash should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'invalid source hash invoked bd'
assert_contains "$TMP/hash.err" 'metadata must contain a valid non-empty plan_source_sha256'

before=$(wc -l <"$BD_LOG")
invalid_ref_metadata="{\"plan_source\":\"docs/plans/example.md\",\"plan_source_sha256\":\"$source_hash\",\"plan_proposal_ref\":\"bad ref\"}"
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create \
    --title 'Invalid ref' --type task --priority P2 \
    --description 'Source plan: docs/plans/example.md' --acceptance 'Observable' \
    --metadata "$invalid_ref_metadata" >"$TMP/ref.out" 2>"$TMP/ref.err"
status=$?
set -e
[[ $status -eq 2 ]] || fail "invalid proposal ref should exit 2, got $status"
[[ $(wc -l <"$BD_LOG") -eq $before ]] || fail 'invalid proposal ref invoked bd'
assert_contains "$TMP/ref.err" 'metadata must contain a valid non-empty plan_proposal_ref'

failure_args=(
    --title 'Fail child'
    --type task
    --priority P2
    --description 'Source plan: docs/plans/example.md'
    --acceptance 'Observable'
    --metadata "$metadata"
    --parent agents-parent
)
before=$(wc -l <"$BD_LOG")
set +e
"$WRITE_HELPER" "$proposal" "$proposal" create "${failure_args[@]}" >"$TMP/failure.out" 2>"$TMP/failure.err"
status=$?
set -e
[[ $status -eq 17 ]] || fail "bd failure should propagate exit 17, got $status"
[[ $(wc -l <"$BD_LOG") -eq $((before + 1)) ]] || fail 'failed action invoked unexpected extra commands'
assert_contains "$TMP/failure.err" 'injected create failure'

printf '%s\n' 'plan-to-backlog helper tests passed'
