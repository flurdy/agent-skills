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

if command -v bd >/dev/null 2>&1; then
    run_probe "BEADS-IN-PROGRESS" bd list --status=in_progress --json --readonly
    run_probe "BEAD-CURRENT" bd show --current --json --readonly
else
    section "BEADS-IN-PROGRESS"
    echo "status=UNAVAILABLE"
    section "BEAD-CURRENT"
    echo "status=UNAVAILABLE"
fi

if [ -z "$TARGET" ]; then
    section "BEAD-EXPLICIT"
    echo "status=NOT_REQUESTED"
elif [[ "$TARGET" =~ ^[A-Z][A-Z0-9]+-[0-9]+$ ]]; then
    section "BEAD-EXPLICIT"
    echo "status=NOT_A_BEAD_TARGET"

    if command -v bd >/dev/null 2>&1; then
        run_probe "BEADS-JIRA-EXTERNAL" bd search --external-contains "$TARGET" --status all --json --readonly
        run_probe "BEADS-JIRA-TITLE" bd list --title-contains "$TARGET" --all --json --readonly
        run_probe "BEADS-JIRA-DESCRIPTION" bd search --desc-contains "$TARGET" --status all --json --readonly
    else
        section "BEADS-JIRA-EXTERNAL"
        echo "status=UNAVAILABLE"
        section "BEADS-JIRA-TITLE"
        echo "status=UNAVAILABLE"
        section "BEADS-JIRA-DESCRIPTION"
        echo "status=UNAVAILABLE"
    fi
else
    if command -v bd >/dev/null 2>&1; then
        run_probe "BEAD-EXPLICIT" bd show --id="$TARGET" --json --readonly
    else
        section "BEAD-EXPLICIT"
        echo "status=UNAVAILABLE"
    fi
fi
