#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
START="$ROOT/skills/start-ticket/SKILL.md"
STACK="$ROOT/skills/stack-branch/SKILL.md"
CREATE="$ROOT/skills/create-pr/SKILL.md"
STATUS="$ROOT/skills/pr-status/SKILL.md"
COMPLETE="$ROOT/skills/complete-task/SKILL.md"
REVIEW="$ROOT/skills/review-comments/SKILL.md"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

assert_contains() {
    local file=$1 expected=$2
    grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_contains() {
    local file=$1 unexpected=$2
    if grep -Fq -- "$unexpected" "$file"; then
        fail "did not expect '$unexpected' in $file"
    fi
}

line_of() {
    local file=$1 text=$2
    grep -nF -- "$text" "$file" | head -1 | cut -d: -f1
}

assert_order() {
    local file=$1
    shift
    local previous=0 current text
    for text in "$@"; do
        current=$(line_of "$file" "$text")
        [[ -n "$current" ]] || fail "missing '$text' in $file"
        ((current > previous)) || fail "expected '$text' after prior invariant in $file"
        previous=$current
    done
}

for file in "$START" "$STACK"; do
    assert_contains "$file" 'Bash(~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh:*)'
    assert_contains "$file" 'git-branch-preflight.sh {new-branch-name}'
    assert_contains "$file" 'Working tree gate'
    assert_contains "$file" 'Existing branch gate'
    assert_contains "$file" 'another worktree'
    assert_contains "$file" 'differs from `current_worktree`'
    assert_contains "$file" 'git switch --no-track -c {new-branch-name}'
    assert_contains "$file" '`target_published=true`'
    assert_contains "$file" 'exact `origin/{new-branch-name}` destination'
    assert_contains "$file" 'Confirm branch push'
    assert_contains "$file" 'git push -u origin {new-branch-name}'
    assert_contains "$file" 'Approval applies only to that one command'
    assert_order "$file" 'Confirm branch push' 'git push -u origin {new-branch-name}'
done

assert_contains "$START" 'AskUserQuestion'
assert_not_contains "$START" 'git checkout main'
assert_not_contains "$START" 'git pull origin main'

assert_contains "$STACK" 'After creating or resuming the branch'
assert_contains "$STACK" 'Offer draft PR handoff'
assert_contains "$STACK" '/create-pr --draft {parent-branch}'
assert_not_contains "$STACK" 'gh pr create'
assert_not_contains "$STACK" 'gh-pr-create.sh'
assert_order "$STACK" \
    'Confirm branch push' \
    'git push -u origin {new-branch-name}' \
    'Offer draft PR handoff' \
    '/create-pr --draft {parent-branch}'

assert_contains "$CREATE" '/create-pr --draft {base-branch}'
assert_contains "$CREATE" '{draft-flag}'
assert_contains "$CREATE" 'If the branch is empty, stop: HEAD is detached.'
assert_contains "$CREATE" 'Resolve the PR base'
assert_contains "$CREATE" 'Publication audit'
assert_contains "$CREATE" 'Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)'
assert_contains "$CREATE" 'artifact-hygiene/scripts/artifact_hygiene.py --pretty'
assert_contains "$CREATE" '../artifact-hygiene/SKILL.md#report'
assert_contains "$CREATE" 'coverage before findings'
assert_contains "$CREATE" 'partial is never clean'
assert_contains "$CREATE" 'Exit `0` alone is not clearance'
assert_contains "$CREATE" '`status: complete`, `verdict: clean`'
assert_contains "$CREATE" 'stop before push or PR creation'
assert_contains "$CREATE" 'Never recover raw evidence'
assert_contains "$CREATE" 'Remediation is a separate explicitly approved task'
assert_contains "$CREATE" 'A clean audit is not consent'
assert_contains "$CREATE" 'rerun §6a before the PR-creation confirmation'
assert_contains "$CREATE" 'not the PR diff or drafted title/body'
assert_order "$CREATE" \
    '### 6a. Publication audit' \
    'artifact-hygiene/scripts/artifact_hygiene.py --pretty' \
    '### 7. Confirm push' \
    'git push -u origin {branch-name}'
assert_contains "$CREATE" 'Confirm push'
assert_contains "$CREATE" 'Bash(~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh:*)'
assert_contains "$CREATE" 'git-branch-preflight.sh {branch-name}'
assert_contains "$CREATE" 'exact `origin/{branch-name}` destination'
assert_contains "$CREATE" 'Confirm PR creation'
assert_contains "$CREATE" '--base {base-branch}'
assert_contains "$CREATE" 'bd -C <directory> close <bead-id>'
assert_order "$CREATE" \
    'Confirm push' \
    'git push -u origin {branch-name}' \
    'Confirm PR creation' \
    'gh-pr-create.sh {draft-flag} --base {base-branch}'

assert_not_contains "$STATUS" '/request-review'
assert_contains "$STATUS" 'gh pr edit {n} --repo {owner}/{repo} --add-reviewer <handle>'
assert_contains "$STATUS" '| → 🔔 awaiting review'

assert_contains "$COMPLETE" 'git symbolic-ref --quiet --short HEAD'
assert_contains "$COMPLETE" '**Detached mode**'
assert_contains "$COMPLETE" 'leave the bead `in_progress`'
assert_contains "$COMPLETE" 'git switch -c {branch-name}'
assert_contains "$COMPLETE" '### 3. Select new work or an existing verified commit'
assert_contains "$COMPLETE" 'With task changes, HEAD may be unborn: stage and create the initial commit normally.'
assert_order "$COMPLETE" 'With task changes, HEAD may be unborn' 'require `git rev-parse HEAD` to succeed'
assert_contains "$COMPLETE" 'do not create an empty commit'
assert_contains "$COMPLETE" 'skip staging and committing and continue to §5'
assert_contains "$COMPLETE" 'either a successful new commit or an explicitly confirmed existing verified commit'
assert_contains "$COMPLETE" '**No changes to commit**: use the existing-commit path in §3'
assert_not_contains "$COMPLETE" 'Only after the commit succeeds'
assert_not_contains "$COMPLETE" '**Trunk / direct-commit mode** — `current_branch` equals `default_branch`, **or** there is no remote, **or** HEAD is detached.'

assert_contains "$REVIEW" 'Bash(~/.agents/skills/next/scripts/next-select:*)'
assert_contains "$REVIEW" 'next/scripts/next-select resolve <bead-id>'
assert_contains "$REVIEW" 'next/scripts/next-select start <bead-id>'
assert_contains "$REVIEW" 'Reopen the bead after a committed fix'
assert_not_contains "$REVIEW" 'bd -C <directory> close'
assert_order "$REVIEW" '### 7. Implement, Verify, and Commit Locally' 'Reopen the bead after a committed fix'

printf '%s\n' 'Git/PR lifecycle contract tests passed'
