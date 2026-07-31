#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILL_DIR=$(dirname -- "$TEST_DIR")
SKILL="$SKILL_DIR/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local expected=$1
    grep -Fq -- "$expected" "$SKILL" || fail "expected '$expected' in $SKILL"
}

line_of() {
    local heading=$1
    grep -nF -- "$heading" "$SKILL" | head -1 | cut -d: -f1
}

[[ -f "$SKILL" ]] || fail "missing reply-comments skill"

for invariant in \
    'version: "1.2.0"' \
    '`owner/repo#number`' \
    'stable `identity`' \
    '`updateKey`' \
    '`stateKey`' \
    '500 handled actions' \
    'partial' \
    're-fetch' \
    'If an item is changed,' \
    'do not retry automatically' \
    'manual reconciliation' \
    '### 5. Push Confirmation' \
    'explicit permission immediately before' \
    'standalone `git push`' \
    '### 6. Reply Confirmation' \
    'exact reply body' \
    'inline review' \
    'top-level conversation' \
    'review summary' \
    'CI annotation' \
    'approval' \
    'automated status' \
    'Human' \
    'AI/bot' \
    'gh-pr-reply-comment.sh' \
    'gh-pr-conversation-comment.sh' \
    '### 7. Resolution Confirmation' \
    'Resolve only inline' \
    'false positive' \
    'gh-pr-resolve-thread.sh' \
    'AskUserQuestion' \
    'Feedback ID' \
    'Validation' \
    'Files/tests/commit' \
    'Push state' \
    'Reply' \
    'Resolution'; do
    assert_contains "$invariant"
done

push_line=$(line_of '### 5. Push Confirmation')
reply_line=$(line_of '### 6. Reply Confirmation')
resolve_line=$(line_of '### 7. Resolution Confirmation')
[[ -n "$push_line" && -n "$reply_line" && -n "$resolve_line" ]] || fail 'remote gate sections must exist'
((push_line < reply_line && reply_line < resolve_line)) || fail 'push, reply, and resolution gates must stay separate and ordered'

if grep -Eq -- '--force(-with-lease)?' "$SKILL"; then
    fail 'reply-comments must not introduce force push'
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
cat >"$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$GH_ARGS_LOG"
EOF
chmod +x "$TMP/bin/gh"
export GH_ARGS_LOG="$TMP/args"

PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-conversation-comment.sh" acme widgets 42 'Thanks — fixed.'
mapfile -t args <"$GH_ARGS_LOG"
expected=(api repos/acme/widgets/issues/42/comments -f 'body=Thanks — fixed.')
[[ "${args[*]}" == "${expected[*]}" ]] || fail "unexpected conversation endpoint: ${args[*]}"

PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-reply-comment.sh" acme widgets 42 101 'Fixed.'
mapfile -t args <"$GH_ARGS_LOG"
expected=(api repos/acme/widgets/pulls/42/comments/101/replies -f 'body=Fixed.')
[[ "${args[*]}" == "${expected[*]}" ]] || fail "unexpected inline endpoint: ${args[*]}"

PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-resolve-thread.sh" THREAD_1
mapfile -t args <"$GH_ARGS_LOG"
[[ "${args[0]}" == api && "${args[1]}" == graphql ]] || fail 'resolution helper did not use GraphQL'
printf '%s\n' "${args[@]}" | grep -Fq 'threadId=THREAD_1' || fail 'resolution helper lost thread ID'

if PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-conversation-comment.sh" acme widgets 42 >/dev/null 2>&1; then
    fail 'conversation helper accepted missing body'
fi
if PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-reply-comment.sh" acme widgets 42 101 >/dev/null 2>&1; then
    fail 'inline helper accepted missing body'
fi
if PATH="$TMP/bin:$PATH" "$SKILL_DIR/scripts/gh-pr-resolve-thread.sh" >/dev/null 2>&1; then
    fail 'resolution helper accepted missing thread ID'
fi

printf '%s\n' 'reply-comments attended contract tests passed'
