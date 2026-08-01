#!/usr/bin/env bash
# Emit today's activity for the wrap-up skill: commits across worktrees,
# PRs (created/merged/closed today), and Beads state/activity.
# Sections are delimited by `---<NAME>---` markers for easy parsing.
# --workspace preserves the default contract while adding validated workspace
# scope, repository-qualified commits, and repository-qualified Beads JSON.
set -uo pipefail

TODAY=$(date -I)
SINCE="${TODAY}T00:00:00"

section_value() {
    local section=$1
    awk -v marker="---${section}---" '$0 == marker { getline; print; exit }'
}

compact_json() {
    python3 -c '
import json
import sys

fields = ("id", "title", "status", "priority", "issue_type")
items = json.load(sys.stdin)
summary = [{field: item.get(field) for field in fields if field in item} for item in items]
json.dump(summary, sys.stdout, separators=(",", ":"))
' 2>/dev/null
}

emit_github_activity() {
    local status created merged closed
    local -a diagnostics=()

    created="[]"
    merged="[]"
    closed="[]"
    if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
        status="UNAVAILABLE"
    else
        status="OK"
        if ! created=$(gh search prs --author=@me --created="$TODAY" \
            --json number,title,url,repository,state,isDraft --limit 30 2>/dev/null); then
            created="[]"
            status="ERROR"
            diagnostics+=("Created-PR query failed.")
        fi
        if ! merged=$(gh search prs --author=@me --merged --merged-at="$TODAY" \
            --json number,title,url,repository --limit 30 2>/dev/null); then
            merged="[]"
            status="ERROR"
            diagnostics+=("Merged-PR query failed.")
        fi
        if ! closed=$(gh search prs --author=@me --closed="$TODAY" --state=closed \
            --json number,title,url,repository --limit 30 2>/dev/null); then
            closed="[]"
            status="ERROR"
            diagnostics+=("Closed-PR query failed.")
        fi
    fi

    echo "---GH-STATUS---"
    echo "$status"
    echo "---GH-DIAGNOSTICS---"
    printf '%s\n' "${diagnostics[@]}"
    echo "---PRS-CREATED---"
    echo "${created:-[]}"
    echo "---PRS-MERGED---"
    echo "${merged:-[]}"
    echo "---PRS-CLOSED-UNMERGED---"
    echo "${closed:-[]}"
}

emit_workspace_activity() {
    local script_dir multirepo marker root scope current name dir author wt wt_branch wt_base out
    local worktrees log_output
    local -a member_paths=() multirepo_diagnostics=() repo_names=() repo_dirs=() diagnostics=()
    local -a commit_status=() commit_lines=()
    local -a beads_status=() beads_in_progress=() beads_created=() beads_closed=()

    script_dir=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    if multirepo=$("$script_dir/multirepo.sh" --members-only 2>/dev/null); then
        marker=$(printf '%s\n' "$multirepo" | section_value MARKER)
        root=$(printf '%s\n' "$multirepo" | section_value ROOT)
        mapfile -t member_paths < <(
            printf '%s\n' "$multirepo" |
                awk '$0 == "---REPOS---" { emit=1; next } /^---.*---$/ { emit=0 } emit && NF'
        )
        mapfile -t multirepo_diagnostics < <(
            printf '%s\n' "$multirepo" |
                awk '$0 == "---DIAGNOSTICS---" { emit=1; next } /^---.*---$/ { emit=0 } emit && NF'
        )
        diagnostics+=("${multirepo_diagnostics[@]}")
    else
        marker=""
        root=""
        diagnostics+=("Workspace discovery failed; using the current repository only.")
    fi

    if [[ -n "$marker" && "$marker" != "none" && -n "$root" && ${#member_paths[@]} -gt 0 ]]; then
        scope="WORKSPACE"
        for name in "${member_paths[@]}"; do
            dir=$(readlink -f "$root/$name" 2>/dev/null || true)
            if [[ -z "$dir" ]] || ! git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
                diagnostics+=("Skipped unavailable workspace member: $name")
                continue
            fi
            if [[ "$name" == "." ]]; then
                name=$(basename "$root")
            fi
            repo_names+=("$name")
            repo_dirs+=("$dir")
        done
    else
        scope="CURRENT_REPO"
        current=$(git rev-parse --show-toplevel 2>/dev/null || true)
        if [[ -n "$current" ]]; then
            current=$(readlink -f "$current")
            repo_names+=("$(basename "$current")")
            repo_dirs+=("$current")
        fi
        if [[ -n "$marker" && "$marker" != "none" ]]; then
            diagnostics+=("Workspace membership was incomplete; using the current repository only.")
        fi
        root="$current"
    fi

    echo "---STATUS---"
    if [[ ${#repo_dirs[@]} -gt 0 ]]; then echo "OK"; else echo "NO_GIT"; fi
    echo "---DATE---"
    echo "$TODAY"
    echo "---AUTHOR---"
    git config user.email 2>/dev/null
    echo "---SCOPE---"
    echo "$scope"
    echo "---ROOT---"
    echo "$root"
    echo "---REPOSITORIES---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        echo "${repo_names[$i]}|${repo_dirs[$i]}"
    done
    echo "---DIAGNOSTICS---"
    printf '%s\n' "${diagnostics[@]}"

    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        name=${repo_names[$i]}
        dir=${repo_dirs[$i]}
        author=$(git -C "$dir" config user.email 2>/dev/null || true)
        if [[ -z "$author" ]]; then
            commit_status[$i]="NO_AUTHOR"
            continue
        fi
        if ! worktrees=$(git -C "$dir" worktree list --porcelain 2>/dev/null); then
            commit_status[$i]="ERROR"
            continue
        fi
        commit_status[$i]="OK"
        while IFS= read -r wt; do
            [[ -n "$wt" ]] || continue
            wt_branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
            wt_base=$(basename "$wt")
            if log_output=$(git -C "$wt" log --since="$SINCE" --author="$author" \
                --format="${name}|${wt_base}|${wt_branch}|%h|%s|%ar" --no-merges 2>/dev/null); then
                if [[ -n "$log_output" ]]; then
                    commit_lines[$i]="${commit_lines[$i]:-}${log_output}"$'\n'
                fi
            else
                commit_status[$i]="ERROR"
            fi
        done < <(printf '%s\n' "$worktrees" | awk '/^worktree /{print $2}')
    done

    echo "---COMMIT-STATUS---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        echo "${repo_names[$i]}|${commit_status[$i]}"
    done
    echo "---COMMITS---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        printf '%s' "${commit_lines[$i]:-}"
    done

    emit_github_activity

    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        name=${repo_names[$i]}
        dir=${repo_dirs[$i]}
        if ! command -v bd >/dev/null 2>&1; then
            beads_status[$i]="NO_BD"
        elif [[ ! -d "$dir/.beads" ]]; then
            beads_status[$i]="NO_BEADS_IN_REPO"
        elif out=$(bd -C "$dir" list --status=in_progress --limit=50 --json --readonly 2>/dev/null) &&
             beads_in_progress[$i]=$(printf '%s\n' "$out" | compact_json) &&
             out=$(bd -C "$dir" list --created-after="$TODAY" --limit=50 --json --readonly 2>/dev/null) &&
             beads_created[$i]=$(printf '%s\n' "$out" | compact_json) &&
             out=$(bd -C "$dir" list --status=closed --closed-after="$TODAY" --limit=50 --json --readonly 2>/dev/null) &&
             beads_closed[$i]=$(printf '%s\n' "$out" | compact_json); then
            beads_status[$i]="OK"
        else
            beads_status[$i]="ERROR"
        fi
    done

    echo "---BEADS-STATUS---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        echo "${repo_names[$i]}|${beads_status[$i]}"
    done
    echo "---BEADS-IN-PROGRESS---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_status[$i]} == "OK" ]] && echo "${repo_names[$i]}|${beads_in_progress[$i]}"
    done
    echo "---BEADS-CREATED-TODAY---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_status[$i]} == "OK" ]] && echo "${repo_names[$i]}|${beads_created[$i]}"
    done
    echo "---BEADS-CLOSED---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_status[$i]} == "OK" ]] && echo "${repo_names[$i]}|${beads_closed[$i]}"
    done
}

if [[ "${1:-}" == "--workspace" ]]; then
    emit_workspace_activity
    exit 0
fi

# Grace period (days) before an in-progress bead counts as "stale". A bead
# touched within this window is still considered live WIP, so running wrap-up
# many times a day — or working a bead over several days without committing —
# no longer flags it. Override with WRAP_UP_STALE_DAYS; default 7.
STALE_DAYS="${WRAP_UP_STALE_DAYS:-7}"
case "$STALE_DAYS" in
    ''|*[!0-9]*) STALE_DAYS=7 ;;  # non-numeric override → fall back to default
esac
STALE_BEFORE=$(date -I -d "${TODAY} -${STALE_DAYS} days" 2>/dev/null || echo "$TODAY")

echo "---STATUS---"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "OK"
else
    echo "NO_GIT"
fi

echo "---DATE---"
echo "$TODAY"

echo "---AUTHOR---"
git config user.email 2>/dev/null

# --- Commits across all worktrees of this repo ---
echo "---COMMITS---"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    AUTHOR=$(git config user.email 2>/dev/null)
    if [ -n "$AUTHOR" ]; then
        git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}' | while IFS= read -r WT; do
            WT_BRANCH=$(git -C "$WT" rev-parse --abbrev-ref HEAD 2>/dev/null)
            WT_BASE=$(basename "$WT")
            git -C "$WT" log --since="$SINCE" --author="$AUTHOR" \
                --format="${WT_BASE}|${WT_BRANCH}|%h|%s|%ar" --no-merges 2>/dev/null
        done
    fi
fi

# --- PRs created / merged / closed today ---
emit_github_activity

# --- Beads closed today ---
echo "---BEADS-STATUS---"
if ! command -v bd >/dev/null 2>&1; then
    echo "NO_BD"
elif [ ! -d .beads ]; then
    echo "NO_BEADS_IN_REPO"
else
    echo "OK"
fi

echo "---BEADS-IN-PROGRESS---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=in_progress --limit=50 --no-pager 2>/dev/null
fi

# Window the §3a stale check exposes, so the prose can name it ("idle 7+ days").
echo "---BEADS-STALE-DAYS---"
echo "$STALE_DAYS"

# In-progress beads idle for the whole grace period — the candidate set for
# §3a's stale check. Anything updated within STALE_DAYS (a bead a parallel
# session is actively working, or one you've been at over several days, or one
# you touched earlier in a day full of repeated wrap-ups) is still live WIP and
# excluded here. This kills the false positives where a bead read as "stale"
# the moment the clock rolled past midnight without a commit/branch trace.
echo "---BEADS-STALE-CANDIDATES---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=in_progress --updated-before="$STALE_BEFORE" --limit=50 --no-pager 2>/dev/null
fi

echo "---BEADS-CREATED-TODAY---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    # Default filter excludes closed — beads created and closed the same day
    # already appear in CLOSED, so this lists only ones left open.
    bd list --created-after="$TODAY" --limit=50 --no-pager 2>/dev/null
fi

echo "---BEADS-CLOSED---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=closed --closed-after="$TODAY" --limit=50 --no-pager 2>/dev/null
fi
