#!/usr/bin/env bash
# Collect fresh, read-only mechanical evidence for /outstanding-work.
# Requirement assessment and rendering remain the calling agent's responsibility.
set -u

usage() {
    echo "usage: collect.sh [<bead-id|JIRA-key>]" >&2
}

if [ "$#" -gt 1 ]; then
    usage
    exit 2
fi

TARGET=${1:-}
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SKILLS_ROOT=$(dirname -- "$(dirname -- "$SCRIPT_DIR")")
WORKING_COPY_HELPER="$SKILLS_ROOT/landscape/scripts/working-copy.sh"

section() {
    printf '%s\n' "---$1---"
}

# Prefix every external payload line so tool-controlled text cannot forge a section or status.
emit_payload() {
    local payload=${1:-}
    local line

    while IFS= read -r line || [ -n "$line" ]; do
        printf 'data=%s\n' "$line"
    done <<<"$payload"
}

run_probe() {
    local name=$1
    shift
    local output

    section "$name"
    if output=$("$@" 2>&1); then
        echo "status=OK"
        [ -n "$output" ] && emit_payload "$output"
    else
        echo "status=ERROR"
        [ -n "$output" ] && emit_payload "$output"
    fi
}

section "TIMESTAMP"
emit_payload "$(date '+%Y-%m-%d %H:%M:%S %Z')"

section "TARGET"
if [ -n "$TARGET" ]; then
    emit_payload "$TARGET"
else
    echo "data=CURRENT"
fi

section "GIT-META"
if command -v git >/dev/null 2>&1 && GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "status=OK"
    printf 'data=root=%q\n' "$GIT_ROOT"
    printf 'data=branch=%q\n' "$(git branch --show-current 2>/dev/null || true)"
    printf 'data=head=%q\n' "$(git rev-parse HEAD 2>/dev/null || true)"
else
    echo "status=UNAVAILABLE"
fi

if [ -x "$WORKING_COPY_HELPER" ]; then
    run_probe "WORKING-COPY" "$WORKING_COPY_HELPER"
else
    section "WORKING-COPY"
    echo "status=UNAVAILABLE"
    echo "reason=landscape working-copy helper not found"
fi

section "CURRENT-PR"
if command -v gh >/dev/null 2>&1; then
    if PR_OUTPUT=$(gh pr view --json number,title,body,state,url,headRefName,headRefOid,baseRefName 2>&1); then
        echo "status=OK"
        emit_payload "$PR_OUTPUT"
    else
        echo "status=NOT_LINKED_OR_UNAVAILABLE"
        [ -n "$PR_OUTPUT" ] && emit_payload "$PR_OUTPUT"
    fi
else
    echo "status=UNAVAILABLE"
fi

# The resolver owns topology and identity; never fall back to unqualified bd.
run_probe "TRACKING-INVENTORY" python3 "$SCRIPT_DIR/tracking.py" "$TARGET"
