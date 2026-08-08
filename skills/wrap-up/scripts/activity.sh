#!/usr/bin/env bash
# Emit activity for the wrap-up and catch-up skills: commits across worktrees,
# PRs, and Beads state/activity. Sections use `---<NAME>---` delimiters.
# --workspace adds validated workspace scope and repository-qualified output.
# --previous-workday selects Friday on Monday and the prior calendar day otherwise.
set -uo pipefail

WORKSPACE_MODE=0
PREVIOUS_WORKDAY=0
for arg in "$@"; do
    case "$arg" in
        --workspace) WORKSPACE_MODE=1 ;;
        --previous-workday) PREVIOUS_WORKDAY=1 ;;
        *)
            echo "ERROR: unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done
if [[ $PREVIOUS_WORKDAY -eq 1 && $WORKSPACE_MODE -ne 1 ]]; then
    echo "ERROR: --previous-workday requires --workspace" >&2
    exit 2
fi

BASE_DATE=${ACTIVITY_TODAY:-$(date +%F)}
if ! WINDOW=$(python3 - "$BASE_DATE" "$PREVIOUS_WORKDAY" <<'PY'
from datetime import date, datetime, time, timedelta, timezone
import sys

try:
    base = date.fromisoformat(sys.argv[1])
except ValueError as error:
    raise SystemExit(f"ERROR: invalid activity date: {error}")

activity = base - timedelta(days=3 if sys.argv[2] == "1" and base.weekday() == 0 else int(sys.argv[2]))
window_end_date = activity + timedelta(days=1)
window_start = datetime.combine(activity, time.min).astimezone()
window_end = datetime.combine(window_end_date, time.min).astimezone()
window_start_utc = window_start.astimezone(timezone.utc)
window_end_utc = window_end.astimezone(timezone.utc)
beads_after_utc = window_start_utc - timedelta(seconds=1)
github_end = window_end_utc - timedelta(seconds=1)

def utc(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")

print(
    activity.isoformat(),
    window_start.isoformat(timespec="seconds"),
    window_end.isoformat(timespec="seconds"),
    utc(window_start_utc),
    utc(window_end_utc),
    utc(beads_after_utc),
    f"{window_start_utc.date().isoformat()}..{github_end.date().isoformat()}",
)
PY
); then
    exit 2
fi
read -r TODAY SINCE UNTIL WINDOW_START_UTC WINDOW_END_UTC BEADS_AFTER_UTC GH_DATE_RANGE <<<"$WINDOW"
GIT_UNTIL=$(python3 - "$UNTIL" <<'PY'
from datetime import datetime, timedelta
import sys
print((datetime.fromisoformat(sys.argv[1]) - timedelta(seconds=1)).isoformat(timespec="seconds"))
PY
)

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

filter_json_window() {
    local field=$1
    python3 -c '
from datetime import datetime
import json
import sys

field, start_text, end_text = sys.argv[1:]
parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
start = parse(start_text)
end = parse(end_text)
matched = []
for item in json.load(sys.stdin):
    value = item.get(field)
    if value and start <= parse(value) < end:
        matched.append(item)
json.dump(matched, sys.stdout, separators=(",", ":"))
' "$field" "$WINDOW_START_UTC" "$WINDOW_END_UTC" 2>/dev/null
}

without_closed_json() {
    python3 -c '
import json
import sys
json.dump(
    [item for item in json.load(sys.stdin) if item.get("status") != "closed"],
    sys.stdout,
    separators=(",", ":"),
)
' 2>/dev/null
}

strip_json_field() {
    local field=$1
    python3 -c '
import json
import sys
field = sys.argv[1]
items = json.load(sys.stdin)
for item in items:
    item.pop(field, None)
json.dump(items, sys.stdout, separators=(",", ":"))
' "$field" 2>/dev/null
}

emit_github_activity() {
    local status created merged closed raw
    local -a diagnostics=()

    created="[]"
    merged="[]"
    closed="[]"
    if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
        status="UNAVAILABLE"
    else
        status="OK"
        if raw=$(gh search prs --author=@me --created="$GH_DATE_RANGE" \
            --json number,title,url,repository,state,isDraft,createdAt --limit 100 2>/dev/null) &&
           created=$(printf '%s\n' "$raw" | filter_json_window createdAt | strip_json_field createdAt); then
            :
        else
            created="[]"
            status="ERROR"
            diagnostics+=("Created-PR query failed.")
        fi
        if raw=$(gh search prs --author=@me --merged --merged-at="$GH_DATE_RANGE" \
            --json number,title,url,repository,closedAt --limit 100 2>/dev/null) &&
           merged=$(printf '%s\n' "$raw" | filter_json_window closedAt | strip_json_field closedAt); then
            :
        else
            merged="[]"
            status="ERROR"
            diagnostics+=("Merged-PR query failed.")
        fi
        if raw=$(gh search prs --author=@me --closed="$GH_DATE_RANGE" --state=closed \
            --json number,title,url,repository,closedAt --limit 100 2>/dev/null) &&
           closed=$(printf '%s\n' "$raw" | filter_json_window closedAt | strip_json_field closedAt); then
            :
        else
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
    local script_dir multirepo marker root scope current name dir author wt wt_branch wt_base out filtered
    local worktrees log_output failures
    local -a member_paths=() multirepo_diagnostics=() repo_names=() repo_dirs=() diagnostics=()
    local -a commit_status=() commit_lines=()
    local -a beads_status=() beads_in_progress=() beads_created=() beads_created_legacy=() beads_closed=()
    local -a beads_in_progress_ok=() beads_created_ok=() beads_closed_ok=()

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
    echo "---WINDOW-START---"
    echo "$SINCE"
    echo "---WINDOW-END---"
    echo "$UNTIL"
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
            # The git format stays constant. Branch and directory names may contain
            # % placeholders, which git would expand into the parsed stream.
            if log_output=$(git -C "$wt" log --since="$SINCE" --until="$GIT_UNTIL" --author="$author" \
                --format="%h|%s|%ar" --no-merges 2>/dev/null); then
                if [[ -n "$log_output" ]]; then
                    while IFS= read -r commit_line || [[ -n "$commit_line" ]]; do
                        commit_lines[$i]="${commit_lines[$i]:-}${name}|${wt_base}|${wt_branch}|${commit_line}"$'\n'
                    done <<<"$log_output"
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
            continue
        elif [[ ! -d "$dir/.beads" ]]; then
            beads_status[$i]="NO_BEADS_IN_REPO"
            continue
        fi

        failures=0
        if out=$(bd -C "$dir" list --status=in_progress --limit=50 --json --readonly 2>/dev/null) &&
           beads_in_progress[$i]=$(printf '%s\n' "$out" | compact_json); then
            beads_in_progress_ok[$i]=1
        else
            failures=1
        fi
        if out=$(bd -C "$dir" list --all --created-after="$BEADS_AFTER_UTC" \
                --created-before="$WINDOW_END_UTC" --limit=0 --json --readonly 2>/dev/null) &&
           filtered=$(printf '%s\n' "$out" | filter_json_window created_at) &&
           beads_created[$i]=$(printf '%s\n' "$filtered" | compact_json) &&
           beads_created_legacy[$i]=$(printf '%s\n' "$filtered" | without_closed_json | compact_json); then
            beads_created_ok[$i]=1
        else
            failures=1
        fi
        if out=$(bd -C "$dir" list --status=closed --closed-after="$BEADS_AFTER_UTC" \
                --closed-before="$WINDOW_END_UTC" --limit=0 --json --readonly 2>/dev/null) &&
           filtered=$(printf '%s\n' "$out" | filter_json_window closed_at) &&
           beads_closed[$i]=$(printf '%s\n' "$filtered" | compact_json); then
            beads_closed_ok[$i]=1
        else
            failures=1
        fi
        if [[ $failures -eq 0 ]]; then
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
        [[ ${beads_in_progress_ok[$i]:-0} -eq 1 ]] && echo "${repo_names[$i]}|${beads_in_progress[$i]}"
    done
    echo "---BEADS-CREATED---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_created_ok[$i]:-0} -eq 1 ]] && echo "${repo_names[$i]}|${beads_created[$i]}"
    done
    # Compatibility alias excludes currently closed rows, matching the prior /today contract.
    echo "---BEADS-CREATED-TODAY---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_created_ok[$i]:-0} -eq 1 ]] && echo "${repo_names[$i]}|${beads_created_legacy[$i]}"
    done
    echo "---BEADS-CLOSED---"
    for ((i = 0; i < ${#repo_dirs[@]}; i++)); do
        [[ ${beads_closed_ok[$i]:-0} -eq 1 ]] && echo "${repo_names[$i]}|${beads_closed[$i]}"
    done
}

if [[ $WORKSPACE_MODE -eq 1 ]]; then
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
echo "---WINDOW-START---"
echo "$SINCE"
echo "---WINDOW-END---"
echo "$UNTIL"

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
            # The git format stays constant. Branch and directory names may contain
            # % placeholders, which git would expand into the parsed stream.
            git -C "$WT" log --since="$SINCE" --until="$GIT_UNTIL" --author="$AUTHOR" \
                --format="%h|%s|%ar" --no-merges 2>/dev/null \
                | while IFS= read -r COMMIT_LINE || [ -n "$COMMIT_LINE" ]; do
                    printf '%s|%s|%s\n' "$WT_BASE" "$WT_BRANCH" "$COMMIT_LINE"
                done
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
    bd list --status=in_progress --limit=50 --no-pager --readonly 2>/dev/null
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
    bd list --status=in_progress --updated-before="$STALE_BEFORE" --limit=50 --no-pager --readonly 2>/dev/null
fi

echo "---BEADS-CREATED-TODAY---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    # Default filter excludes closed — beads created and closed the same day
    # already appear in CLOSED, so this lists only ones left open.
    bd list --created-after="$BEADS_AFTER_UTC" --created-before="$WINDOW_END_UTC" --limit=50 --no-pager --readonly 2>/dev/null
fi

echo "---BEADS-CLOSED---"
if command -v bd >/dev/null 2>&1 && [ -d .beads ]; then
    bd list --status=closed --closed-after="$BEADS_AFTER_UTC" --closed-before="$WINDOW_END_UTC" --limit=50 --no-pager --readonly 2>/dev/null
fi
