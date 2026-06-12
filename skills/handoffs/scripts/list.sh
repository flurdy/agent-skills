#!/usr/bin/env bash
# List Claude Code handoff files (~/.claude/handoffs/*.md) with metadata.
# Sections delimited by `---<NAME>---` markers. Companion to the wrap-up skill.
#
# Usage: list.sh [--recent-days N] [--summary-only] [--bead ID] [--ticket KEY]
#   --recent-days N   override the "recent" window (default: 3, with Mon=3, Tue=4
#                     weekend buffer to mirror gh-pr-list-closed.sh)
#   --summary-only    suppress per-file lines in the HANDOFFS section (landscape's
#                     footer only needs the SUMMARY counts)
#   --bead ID         emit a `---MATCHED-HANDOFFS---` section: current-repo, NON-stale
#   --ticket KEY      handoffs whose `**Beads:**` / `**Jira:**` header field contains
#                     an exact ID/KEY token. Lets /next and /start-ticket surface
#                     "you have a handoff for this" at bead/ticket resume — without
#                     re-implementing repo-matching or staleness. "Non-stale" =
#                     archive-class empty (live / open-PR / unknown); superseded and
#                     merged/closed rows are dropped so dead context isn't resurfaced.
#                     Pair with --check-branches for full staleness (merged-PR) filtering;
#                     without it only supersede filtering applies. Leaves every other
#                     section byte-identical, so existing callers are unaffected.
set -uo pipefail

HANDOFFS_DIR="${HOME}/.claude/handoffs"

RECENT_DAYS=""
SUMMARY_ONLY=0
CHECK_BRANCHES=0
MATCH_BEAD=""
MATCH_TICKET=""
while [ $# -gt 0 ]; do
    case "$1" in
        --recent-days) RECENT_DAYS="$2"; shift 2 ;;
        --summary-only) SUMMARY_ONLY=1; shift ;;
        --check-branches) CHECK_BRANCHES=1; shift ;;
        --bead) MATCH_BEAD="$2"; shift 2 ;;
        --ticket) MATCH_TICKET="$2"; shift 2 ;;
        *) shift ;;
    esac
done
# A filter is active when either ID was supplied — gates the (otherwise skipped)
# per-file Beads/Jira grep and the MATCHED-HANDOFFS section.
MATCH_FILTER=""
[ -n "$MATCH_BEAD" ] || [ -n "$MATCH_TICKET" ] && MATCH_FILTER=1

# True when handoff field $1 (e.g. "`bd-123`, `bd-124`") contains the exact
# token $2. Backticks and commas are flattened to spaces, then each token is
# compared case-insensitively for an EXACT match — so `bd-12` never matches
# `bd-123`, and `AB-649` matches regardless of case drift from a branch name.
field_has_token() {
    local field id tok
    field=$(printf '%s' "$1" | tr '`,' '  ' | tr '[:upper:]' '[:lower:]')
    id=$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')
    [ -n "$id" ] || return 1
    for tok in $field; do
        [ "$tok" = "$id" ] && return 0
    done
    return 1
}
if [ -z "$RECENT_DAYS" ]; then
    DOW=$(date +%u)  # 1=Mon..7=Sun
    case "$DOW" in
        1) RECENT_DAYS=3 ;;  # Mon → covers Fri+weekend
        2) RECENT_DAYS=4 ;;  # Tue → covers Fri+weekend+Mon
        *) RECENT_DAYS=3 ;;
    esac
fi

# Check whether any sibling of $1 has a *bare* `.claude` symlink pointing at
# $1 (i.e. target == $1, not target == $1/.claude/...). Print the sibling's
# path if so. Used so the "scratch" side of a bare-link pair defers to the
# "real" side (the one with the symlink).
check_bare_symlink_alias() {
    local target_repo_root="$1"
    local parent_dir
    parent_dir=$(dirname "$target_repo_root")
    [ -d "$parent_dir" ] || return 1

    local sibling claude_path link_target
    for sibling in "$parent_dir"/*; do
        [ -d "$sibling" ] || continue
        [ "$sibling" = "$target_repo_root" ] && continue
        claude_path="$sibling/.claude"
        [ -L "$claude_path" ] || continue
        link_target=$(readlink -f "$claude_path" 2>/dev/null)
        [ "$link_target" = "$target_repo_root" ] || continue
        echo "$sibling"
        return 0
    done
    return 1
}

# Resolve a directory (or one of its ancestors) to a repo identity + display.
# Output format: `{repo-id}|{repo-display}` on one line, or non-zero exit if
# we can't resolve to a git repo.
#
# - Walks up from $1 if the path itself doesn't exist (pruned worktrees still
#   point at a real parent repo).
# - Identity prefers `remote.origin.url` so independent clones of the same
#   upstream collapse to one row. Falls back to realpath of git-common-dir.
# - `.claude`-symlink unification has two flavours:
#     • **non-bare** (target is a subdir like `B/.claude` of another repo) —
#       the current side defers to the linked repo's identity.
#     • **bare** (target IS another repo's root) — the current side is the
#       "real" repo; the target is a scratch state-holder. Source keeps its
#       identity. When the scratch side resolves on its own, a sibling scan
#       finds the bare link pointing at it and defers up to the source.
# - Display is the basename of the repo root on disk, stripped of `.git`.
#
# Second argument `follow_claude_link` defaults to 1; recursive calls use 0
# so we follow at most one hop and don't cycle.
resolve_repo_info() {
    local dir="${1:-.}"
    local follow_claude_link="${2:-1}"

    # Refuse relative paths — they would falsely match the script's pwd after
    # enough `dirname`s and report a wrong repo.
    [ "$dir" = "." ] || [[ "$dir" == /* ]] || return 1

    local probe="$dir"
    while [ -n "$probe" ] && [ "$probe" != "/" ] && [ ! -d "$probe" ]; do
        probe=$(dirname "$probe")
    done
    [ -d "$probe" ] || return 1

    local raw abs_git_dir origin repo_id repo_root repo_display
    raw=$(cd "$probe" 2>/dev/null && git rev-parse --git-common-dir 2>/dev/null) || return 1
    [ -n "$raw" ] || return 1
    abs_git_dir=$(cd "$probe" && realpath "$raw" 2>/dev/null) || return 1
    [ -n "$abs_git_dir" ] || return 1

    repo_root=$(dirname "$abs_git_dir")

    if [ "$follow_claude_link" -eq 1 ]; then
        # Non-bare symlink: this repo's .claude → another repo's subdir →
        # defer to that repo's identity.
        if [ -L "$repo_root/.claude" ]; then
            local link_target linked_root
            link_target=$(readlink -f "$repo_root/.claude" 2>/dev/null)
            if [ -n "$link_target" ] && [ -d "$link_target" ]; then
                linked_root=$(cd "$link_target" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)
                if [ -n "$linked_root" ]; then
                    linked_root=$(realpath "$linked_root" 2>/dev/null)
                    if [ -n "$linked_root" ] \
                        && [ "$linked_root" != "$repo_root" ] \
                        && [ "$link_target" != "$linked_root" ]; then
                        # Non-bare: defer
                        resolve_repo_info "$linked_root" 0
                        return $?
                    fi
                    # Otherwise it's bare — fall through to normal resolution
                    # so the source side keeps its own identity.
                fi
            fi
        fi

        # Inverse: if a sibling has a bare `.claude` symlink pointing at this
        # repo, this is the scratch side — defer to the sibling's identity.
        local alias_root
        alias_root=$(check_bare_symlink_alias "$repo_root" 2>/dev/null || true)
        if [ -n "$alias_root" ]; then
            resolve_repo_info "$alias_root" 0
            return $?
        fi
    fi

    origin=$(cd "$probe" 2>/dev/null && git config --get remote.origin.url 2>/dev/null || true)
    if [ -n "$origin" ]; then
        repo_id="$origin"
    else
        repo_id="$abs_git_dir"
    fi

    repo_display=$(basename "$repo_root")
    repo_display="${repo_display%.git}"

    echo "${repo_id}|${repo_display}"
}

# Current repo info — `NONE|NONE` when invoked outside a git repo.
CURRENT_INFO=$(resolve_repo_info . 2>/dev/null || true)
if [ -n "$CURRENT_INFO" ]; then
    CURRENT_REPO_KEY="${CURRENT_INFO%%|*}"
    CURRENT_REPO_DISPLAY="${CURRENT_INFO##*|}"
else
    CURRENT_REPO_KEY="NONE"
    CURRENT_REPO_DISPLAY="NONE"
fi

CUTOFF=$(date -I -d "${RECENT_DAYS} days ago" 2>/dev/null || date -j -v-${RECENT_DAYS}d +%Y-%m-%d 2>/dev/null)

# --- Branch-liveness setup (only with --check-branches, only in a repo) -----
# Staleness is current-repo-only: the git queries run in the invocation pwd, so
# we can't speak to branches in other repos. One `git ls-remote` (network,
# timeout-guarded) covers remote existence; merged/ancestor checks are local
# against the default branch tip. Degrades gracefully when offline.
TIMEOUT=""
if command -v timeout >/dev/null 2>&1; then TIMEOUT="timeout 8"
elif command -v gtimeout >/dev/null 2>&1; then TIMEOUT="gtimeout 8"; fi

# Short name of the default branch. Computed whenever we're in a repo (not just
# under --check-branches) because the supersede pass — which runs for every
# caller, including wrap-up's no-flag invocation — needs it too: two handoffs
# co-resident on the trunk are NOT the same thread (see is_trunk_branch).
DEFAULT_BRANCH_NAME=""
if [ "$CURRENT_REPO_KEY" != "NONE" ]; then
    dref=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null || true)
    if [ -n "$dref" ]; then
        DEFAULT_BRANCH_NAME="${dref##*/}"
    else
        for cand in main master; do
            if git rev-parse --verify --quiet "$cand" >/dev/null 2>&1 \
                || git rev-parse --verify --quiet "origin/$cand" >/dev/null 2>&1; then
                DEFAULT_BRANCH_NAME="$cand"; break
            fi
        done
    fi
fi

DEFAULT_TIP=""
REMOTE_HEADS=""
REMOTE_OK=0
if [ "$CHECK_BRANCHES" -eq 1 ] && [ "$CURRENT_REPO_KEY" != "NONE" ]; then
    dref=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null || true)
    if [ -n "$dref" ]; then
        DEFAULT_TIP="${dref#refs/remotes/}"
    else
        for cand in origin/main origin/master main master; do
            if git rev-parse --verify --quiet "$cand" >/dev/null 2>&1; then
                DEFAULT_TIP="$cand"; break
            fi
        done
    fi
    if REMOTE_HEADS=$($TIMEOUT git ls-remote --heads origin 2>/dev/null); then
        REMOTE_OK=1
    fi
fi

# True when $1 is a trunk branch — the repo's default branch, or the universal
# main/master. The trunk is never a meaningful "same thread" or "merged feature"
# signal: a worktree sitting on main while the real work lives on a feature
# branch is the trunk-parking case. Used to suppress the `branch` supersede
# reason and the `merged` branch-state. Same-slug / same-day-collision
# supersedes still apply on the trunk — only branch co-residence is discounted.
is_trunk_branch() {
    local b="$1"
    [ -z "$b" ] && return 1
    [ "$b" = "?" ] && return 1
    case "$b" in main|master) return 0 ;; esac
    [ -n "$DEFAULT_BRANCH_NAME" ] && [ "$b" = "$DEFAULT_BRANCH_NAME" ] && return 0
    return 1
}

# --- PR-liveness setup (auto-enabled when `gh` exists; no separate flag) ------
# Tied to --check-branches (the only "network detail wanted" caller) so that
# landscape's --summary-only and wrap-up's plain calls stay network-free. One
# batched `gh pr list` (timeout-guarded) covers every branch; we map by
# headRefName locally. `gh`'s embedded --jq means no external jq dependency.
# Degrades exactly like ls-remote: missing/unauthenticated/timed-out gh → every
# row reports pr-state `unknown` and the local heuristic stands.
PR_LINES=""
PR_OK=0
if [ "$CHECK_BRANCHES" -eq 1 ] && [ "$CURRENT_REPO_KEY" != "NONE" ] \
    && command -v gh >/dev/null 2>&1; then
    if PR_LINES=$($TIMEOUT gh pr list --state all --limit 200 \
        --json number,state,headRefName,url \
        --jq '.[] | [.headRefName, (.state|ascii_downcase), (.number|tostring), .url] | @tsv' \
        2>/dev/null); then
        PR_OK=1
    fi
fi

# Look up the PR state for a handoff from the cached `gh` listing. A PR matches
# either by branch (headRefName) OR by a number recorded in the handoff's
# `**PRs:**` field ($2) — the latter is what catches the trunk-parking case,
# where wrap-up recorded `main` as the branch (the feature branch was already
# gone) but stored the real PR number in the body. Without the number fallback
# such handoffs look up `main`, match nothing, and wrongly render 🟢 live.
# Echoes `{state}|{number}|{url}` where state ∈ merged|open|closed (a real PR
# exists), `none||` when gh ran but found no PR, or `unknown||` when gh wasn't
# consulted (no --check-branches, no gh, offline). Precedence across all
# matching PRs (branch- or number-matched): merged > open > closed.
pr_state() {
    local b="$1" prfield="${2:-}"
    [ "$PR_OK" -eq 1 ] || { echo "unknown||"; return; }
    local nums n
    nums=$(printf '%s' "$prfield" | grep -oE '#[0-9]+' | tr -d '#')
    # Nothing to match on at all (branch `?` and no recorded numbers) → unknown.
    { [ "$b" != "?" ] || [ -n "$nums" ]; } || { echo "unknown||"; return; }
    local best_rank=0 best="none||"
    local hb st num url rank match
    while IFS=$'\t' read -r hb st num url; do
        [ -n "$hb" ] || continue
        match=0
        [ "$b" != "?" ] && [ "$hb" = "$b" ] && match=1
        if [ "$match" -eq 0 ] && [ -n "$nums" ]; then
            for n in $nums; do [ "$n" = "$num" ] && { match=1; break; }; done
        fi
        [ "$match" -eq 1 ] || continue
        case "$st" in
            merged) rank=3 ;;
            open)   rank=2 ;;
            closed) rank=1 ;;
            *)      rank=0 ;;
        esac
        if [ "$rank" -gt "$best_rank" ]; then
            best_rank=$rank
            best="${st}|${num}|${url}"
        fi
    done <<< "$PR_LINES"
    echo "$best"
}

# --- Bead-closure setup (local; no network, no --check-branches needed) -------
# A finished task often leaves no live branch/PR — on a trunk-based repo there's
# no PR at all, and even on a PR repo the handoff may have recorded `main`. The
# bead it referenced is the ground-truth "done" signal in those cases. This is a
# local `bd` query, so it runs whenever beads exist (independent of the network
# --check-branches gate) — that lets landscape's offline call also stop counting
# bead-closed handoffs as live threads.
BEADS_AVAILABLE=""
BEADS_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if command -v bd >/dev/null 2>&1 && [ -n "$BEADS_ROOT" ] && [ -d "$BEADS_ROOT/.beads" ]; then
    BEADS_AVAILABLE=1
fi

# Echo "{closed} {total}" for the beads named in field $1 (backtick/comma
# flattened, filtered to `{prefix}-{suffix}` shapes — bd-123, ge-1505,
# letterbox-lf9d). "0 0" when beads are unavailable, the field is empty, the
# field is truncated with "(+N more)" (can't verify all — conservative), or no
# token resolves in the db. One batched, local `bd list --id` per call (no
# network). The caller decides done-ness: all-closed = (total>0 && closed==total).
beads_counts() {
    local field="$1"
    [ -n "$BEADS_AVAILABLE" ] || { echo "0 0"; return; }
    [ -n "$field" ] || { echo "0 0"; return; }
    case "$field" in *"more)"*) echo "0 0"; return ;; esac
    local ids="" tok
    for tok in $(printf '%s' "$field" | tr '`,' '  '); do
        case "$tok" in
            [A-Za-z]*-[A-Za-z0-9]*) ids="${ids:+$ids,}$tok" ;;
        esac
    done
    [ -n "$ids" ] || { echo "0 0"; return; }
    local json total closed
    json=$(bd list --id "$ids" --all --json --limit 0 --no-pager 2>/dev/null) || { echo "0 0"; return; }
    [ -n "$json" ] || { echo "0 0"; return; }
    # Count occurrences (grep -o → one match per line → wc -l) rather than
    # matching lines, so a future compact-JSON `bd` doesn't collapse to 1.
    total=$(printf '%s' "$json" | grep -oE '"status":[[:space:]]*"[a-z_]+"' | wc -l | tr -d ' ')
    closed=$(printf '%s' "$json" | grep -oE '"status":[[:space:]]*"closed"' | wc -l | tr -d ' ')
    echo "$closed $total"
}

# Classify one branch as live / merged / gone / unknown. `unknown` means we
# couldn't determine it (no --check-branches, branch is `?`, or offline with no
# local ref). Only `merged` and `gone` count as stale.
branch_state() {
    local b="$1"
    [ "$b" = "?" ] && { echo "unknown"; return; }

    # The trunk is never "merged" in the feature sense — its tip is trivially an
    # ancestor of DEFAULT_TIP, so the merge-base check below would always fire. A
    # handoff recorded on the trunk (wrap-up captured a worktree sitting on main
    # while the real work lived on a feature branch elsewhere) tells us nothing
    # about liveness — report `unknown` so it renders 🟢 live and never becomes a
    # stale/archive candidate. PR detection still applies separately.
    if is_trunk_branch "$b"; then
        echo "unknown"; return
    fi

    local local_exists=0 remote_sha="" test_commit=""
    if git show-ref --verify --quiet "refs/heads/$b" 2>/dev/null; then
        local_exists=1
        test_commit="refs/heads/$b"
    fi
    if [ "$REMOTE_OK" -eq 1 ]; then
        remote_sha=$(printf '%s\n' "$REMOTE_HEADS" | awk -v r="refs/heads/$b" '$2==r {print $1}')
        [ -z "$test_commit" ] && [ -n "$remote_sha" ] && test_commit="$remote_sha"
    fi

    if [ -n "$test_commit" ] && [ -n "$DEFAULT_TIP" ] \
        && git merge-base --is-ancestor "$test_commit" "$DEFAULT_TIP" 2>/dev/null; then
        echo "merged"; return
    fi
    if [ "$local_exists" -eq 0 ] && [ "$REMOTE_OK" -eq 1 ] && [ -z "$remote_sha" ]; then
        echo "gone"; return
    fi
    if [ "$local_exists" -eq 0 ] && [ "$REMOTE_OK" -eq 0 ]; then
        echo "unknown"; return
    fi
    echo "live"
}

echo "---CURRENT-REPO---"
echo "$CURRENT_REPO_KEY"

echo "---CURRENT-REPO-DISPLAY---"
echo "$CURRENT_REPO_DISPLAY"

echo "---RECENT-WINDOW-DAYS---"
echo "$RECENT_DAYS"

echo "---HANDOFFS-DIR---"
echo "$HANDOFFS_DIR"

echo "---CUTOFF---"
echo "$CUTOFF"

TOTAL=0
CUR_TOTAL=0
CUR_RECENT=0
CUR_PRUNED=0
CUR_SUPERSEDED=0
PRUNED_TOTAL=0
SUPERSEDED_TOTAL=0
UNRESOLVED_COUNT=0
# Parallel arrays for per-repo aggregation (bash 3.2 compatible — macOS).
OTHER_KEYS=()
OTHER_DISPLAYS=()
OTHER_COUNTS=()
# Parallel arrays buffering every handoff record. Supersede classification
# needs all records before any line is emitted, so we collect first, compute
# supersede in a second pass, then print.
R_FILE=()
R_DATE=()
R_TIME=()       # HH:MM from the handoff's "# Resume:" header, falling back to file mtime
R_SLUG=()
R_BASESLUG=()   # slug with a trailing collision suffix (-2, -3, …) removed
R_SUFFIX=()     # the stripped collision suffix, or empty
R_RANK=()       # sortable recency key: "{date}#{suffix3}" (no-suffix → 000)
R_CWD=()
R_BRANCH=()
R_REPO=()
R_EXISTS=()
R_BEADS=()      # raw `**Beads:**` field content (parsed under --bead/--ticket or when beads exist)
R_DELIV=()      # raw `**Deliverable:**` field content — own-work beads (wrap-up v0.10.0+); keys beads-done when present
R_JIRA=()       # raw `**Jira:**` field content (parsed under --bead/--ticket or --check-branches)
R_PRS=()        # raw `**PRs:**` field content (parsed under --check-branches; PR-number fallback)

bump_other() {
    local key="$1" display="$2"
    local i
    for i in "${!OTHER_KEYS[@]}"; do
        if [ "${OTHER_KEYS[$i]}" = "$key" ]; then
            OTHER_COUNTS[$i]=$((OTHER_COUNTS[$i]+1))
            return
        fi
    done
    OTHER_KEYS+=("$key")
    OTHER_DISPLAYS+=("$display")
    OTHER_COUNTS+=(1)
}

if [ -d "$HANDOFFS_DIR" ]; then
    # newest first by filename (handoff filenames begin with YYYY-MM-DD)
    while IFS= read -r F; do
        [ -f "$F" ] || continue
        TOTAL=$((TOTAL+1))
        BASE=$(basename "$F")
        if [[ "$BASE" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2})-(.+)\.md$ ]]; then
            DATE="${BASH_REMATCH[1]}"
            SLUG="${BASH_REMATCH[2]}"
        else
            DATE=$(date -r "$F" +%Y-%m-%d 2>/dev/null)
            SLUG="${BASE%.md}"
        fi
        # Time of the handoff. Prefer the HH:MM trailing the date on the
        # "# Resume:" header (wrap-up v0.8.0+ embeds it — authoritative, and
        # survives the file being copied/synced across machines). Fall back to
        # the file's mtime so older handoffs and hand-edited ones still show a
        # time. `?` only if neither is available.
        TIME=$(grep -m1 '^# Resume:' "$F" 2>/dev/null \
            | sed -n 's/.*[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}[[:space:]]\{1,\}\([0-2][0-9]:[0-5][0-9]\).*/\1/p')
        [ -z "$TIME" ] && TIME=$(date -r "$F" +%H:%M 2>/dev/null)
        [ -z "$TIME" ] && TIME="?"

        LINE=$(grep -m1 '^\*\*Where to pick up:\*\*' "$F" 2>/dev/null || true)
        # Prefer "worktree at `PATH`" — that's reliably absolute. Otherwise use
        # the first backtick-quoted token, which may be relative.
        CWD=$(echo "$LINE" | sed -n 's/.*worktree at `\([^`]*\)`.*/\1/p')
        if [ -z "$CWD" ]; then
            CWD=$(echo "$LINE" | sed -n 's/.*\*\*Where to pick up:\*\* `\([^`]*\)`.*/\1/p')
        fi
        BRANCH=$(echo "$LINE" | sed -n 's/.*on branch `\([^`]*\)`.*/\1/p')
        if [ -z "$BRANCH" ]; then
            BRANCH=$(echo "$LINE" | sed -n 's/.*` on `\([^`]*\)`.*/\1/p')
        fi
        [ -z "$BRANCH" ] && BRANCH="?"

        # `Repo root:` is the canonical repo identity (wrap-up v0.2.0+).
        # Prefer it for resolution — it survives pruned worktrees and bogus
        # `Where to pick up:` paths. Falls back to walking up cwd for older
        # handoffs that don't have the field.
        REPO_ROOT=$(grep -m1 '^\*\*Repo root:\*\*' "$F" 2>/dev/null | sed -n 's/.*\*\*Repo root:\*\* `\([^`]*\)`.*/\1/p' || true)

        # Beads/Jira/PRs header fields. Parsed conditionally so the hot path
        # (wrap-up's no-flag call) pays only for what it uses:
        #   - Beads: when a --bead/--ticket filter is active, OR beads exist
        #     locally (the bead-closure "done" check needs it).
        #   - Jira: when filtering, OR under --check-branches (the skill resolves
        #     Jira-Done for live rows from this field).
        #   - PRs: under --check-branches only (PR-number fallback for pr_state).
        # Strip the `**Field:**` label; keep the raw token list.
        BEADS_FIELD=""; DELIV_FIELD=""; JIRA_FIELD=""; PRS_FIELD=""
        if [ -n "$MATCH_FILTER" ] || [ -n "$BEADS_AVAILABLE" ]; then
            BEADS_FIELD=$(grep -m1 '^\*\*Beads:\*\*' "$F" 2>/dev/null | sed 's/^\*\*Beads:\*\*[[:space:]]*//' || true)
            # `**Deliverable:**` (wrap-up v0.10.0+) names just the own-work beads —
            # the subset whose closure means this handoff is finished. Keys the
            # bead-closure check when present, so trunk-parked handoffs whose
            # **Beads:** list also carries context/epic beads still classify.
            DELIV_FIELD=$(grep -m1 '^\*\*Deliverable:\*\*' "$F" 2>/dev/null | sed 's/^\*\*Deliverable:\*\*[[:space:]]*//' || true)
        fi
        if [ -n "$MATCH_FILTER" ] || [ "$CHECK_BRANCHES" -eq 1 ]; then
            JIRA_FIELD=$(grep -m1 '^\*\*Jira:\*\*' "$F" 2>/dev/null | sed 's/^\*\*Jira:\*\*[[:space:]]*//' || true)
        fi
        if [ "$CHECK_BRANCHES" -eq 1 ]; then
            PRS_FIELD=$(grep -m1 '^\*\*PRs:\*\*' "$F" 2>/dev/null | sed 's/^\*\*PRs:\*\*[[:space:]]*//' || true)
        fi

        if [ -n "$CWD" ] && [ -d "$CWD" ]; then
            EXISTS="Y"
        else
            EXISTS="N"
        fi

        # Resolve repo identity. Order: Repo root field → walk-up from cwd.
        REPO_KEY="UNRESOLVED"
        REPO_DISPLAY=""
        if [ -n "$REPO_ROOT" ]; then
            INFO=$(resolve_repo_info "$REPO_ROOT" 2>/dev/null || true)
            if [ -n "$INFO" ]; then
                REPO_KEY="${INFO%%|*}"
                REPO_DISPLAY="${INFO##*|}"
            fi
        fi
        if [ "$REPO_KEY" = "UNRESOLVED" ] && [ -n "$CWD" ]; then
            INFO=$(resolve_repo_info "$CWD" 2>/dev/null || true)
            if [ -n "$INFO" ]; then
                REPO_KEY="${INFO%%|*}"
                REPO_DISPLAY="${INFO##*|}"
            fi
        fi

        # Recency key for supersede ordering. A trailing collision suffix
        # (-2, -3, … appended by wrap-up on same-day filename collision) makes
        # the suffixed file the newer of the pair, so fold it into the rank.
        SUFFIX=$(printf '%s' "$SLUG" | sed -n 's/.*-\([0-9]\{1,\}\)$/\1/p')
        if [ -n "$SUFFIX" ]; then
            BASESLUG="${SLUG%-$SUFFIX}"
            RANK_SUFFIX=$(printf '%03d' "$((10#$SUFFIX))" 2>/dev/null || echo "000")
        else
            BASESLUG="$SLUG"
            RANK_SUFFIX="000"
        fi

        R_FILE+=("$BASE")
        R_DATE+=("$DATE")
        R_TIME+=("$TIME")
        R_SLUG+=("$SLUG")
        R_BASESLUG+=("$BASESLUG")
        R_SUFFIX+=("$SUFFIX")
        R_RANK+=("${DATE}#${RANK_SUFFIX}")
        R_CWD+=("$CWD")
        R_BRANCH+=("$BRANCH")
        R_REPO+=("$REPO_KEY")
        R_EXISTS+=("$EXISTS")
        R_BEADS+=("$BEADS_FIELD")
        R_DELIV+=("$DELIV_FIELD")
        R_JIRA+=("$JIRA_FIELD")
        R_PRS+=("$PRS_FIELD")

        [ "$EXISTS" = "N" ] && PRUNED_TOTAL=$((PRUNED_TOTAL+1))
        [ "$REPO_KEY" = "UNRESOLVED" ] && UNRESOLVED_COUNT=$((UNRESOLVED_COUNT+1))

        if [ "$CURRENT_REPO_KEY" != "NONE" ] && [ "$REPO_KEY" = "$CURRENT_REPO_KEY" ]; then
            CUR_TOTAL=$((CUR_TOTAL+1))
            [ "$EXISTS" = "N" ] && CUR_PRUNED=$((CUR_PRUNED+1))
            if [[ "$DATE" > "$CUTOFF" ]] || [ "$DATE" = "$CUTOFF" ]; then
                CUR_RECENT=$((CUR_RECENT+1))
            fi
        elif [ "$REPO_KEY" != "UNRESOLVED" ]; then
            bump_other "$REPO_KEY" "$REPO_DISPLAY"
        fi
    done < <(ls -1 "$HANDOFFS_DIR"/*.md 2>/dev/null | sort -r)
fi

# --- Supersede pass -------------------------------------------------------
# A handoff is superseded by a *newer* handoff in the SAME repo that shares its
# branch, its exact slug, or its base slug via a same-day collision suffix.
# Ticket/cwd overlap is deliberately NOT a supersede signal — a ticket spans
# many handoffs legitimately. The `branch` reason also excludes the trunk: two
# distinct threads both recorded on main (the trunk-parking case) are NOT the
# same thread, so trunk co-residence must not collapse them — they only
# supersede on an exact slug or same-day collision. For each record we keep the
# newest superseding file and the reason. UNRESOLVED records never participate.
R_SUPBY=()
R_SUPREASON=()
N=${#R_FILE[@]}
i=0
while [ "$i" -lt "$N" ]; do
    best_rank=""
    best_idx=-1
    best_reason=""
    j=0
    while [ "$j" -lt "$N" ]; do
        if [ "$j" -ne "$i" ] \
            && [ "${R_REPO[$i]}" != "UNRESOLVED" ] \
            && [ "${R_REPO[$j]}" = "${R_REPO[$i]}" ] \
            && [[ "${R_RANK[$j]}" > "${R_RANK[$i]}" ]]; then
            reason=""
            if [ "${R_BRANCH[$i]}" != "?" ] && [ "${R_BRANCH[$j]}" = "${R_BRANCH[$i]}" ] \
                && ! is_trunk_branch "${R_BRANCH[$i]}"; then
                reason="branch"
            elif [ "${R_SLUG[$j]}" = "${R_SLUG[$i]}" ]; then
                reason="slug"
            elif [ -n "${R_SUFFIX[$j]}" ] \
                && [ "${R_BASESLUG[$j]}" = "${R_SLUG[$i]}" ] \
                && [ "${R_DATE[$j]}" = "${R_DATE[$i]}" ]; then
                reason="collision"
            fi
            if [ -n "$reason" ] && { [ -z "$best_rank" ] || [[ "${R_RANK[$j]}" > "$best_rank" ]]; }; then
                best_rank="${R_RANK[$j]}"
                best_idx="$j"
                best_reason="$reason"
            fi
        fi
        j=$((j+1))
    done
    if [ "$best_idx" -ge 0 ]; then
        R_SUPBY+=("${R_FILE[$best_idx]}")
        R_SUPREASON+=("$best_reason")
        SUPERSEDED_TOTAL=$((SUPERSEDED_TOTAL+1))
        if [ "$CURRENT_REPO_KEY" != "NONE" ] && [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ]; then
            CUR_SUPERSEDED=$((CUR_SUPERSEDED+1))
        fi
    else
        R_SUPBY+=("")
        R_SUPREASON+=("")
    fi
    i=$((i+1))
done

# --- Branch/PR-liveness pass (current-repo rows only; needs --check-branches) -
# Fills R_STATE (live/merged/gone/unknown) and, when gh is available, the PR
# fields R_PRSTATE/R_PRNUM/R_PRURL. Rows in other repos stay `unknown` — we can
# only query the repo we're standing in.
#
# R_ARCHCLASS is the per-row archive recommendation used by §3b:
#   safe — superseded, or PR merged, or branch-tip merged locally. Low regret;
#          the context lives on (newer handoff) or the work demonstrably landed.
#   keep — PR closed unmerged, or branch gone with no merged evidence. Higher
#          regret; may be the only record of an abandoned thread.
#   ""   — live work (incl. an OPEN PR — never a candidate) or unknown.
# Precedence: supersede > open PR > merged PR > beads-closed > closed PR >
# local merged > gone. A merged PR is ground truth that beats local ancestry —
# the fix for squash-merges, where the branch is never an ancestor of the
# default tip. Beads-closed ("done") is the fix for the trunk case, where there
# is no feature branch/PR to read — it ranks just under a merged PR but above a
# closed-unmerged PR (the work shipped some other way) and an open PR still wins
# (active review beats a sub-bead closing). R_BEADSDONE records the bead signal
# so the skill renders "✅ done (beads closed)". Jira-Done is resolved by the
# skill from the emitted Jira field (bash can't call the Jira MCP).
# CUR_STALE counts the §3b "stale" group: archivable for a NON-supersede reason
# (superseded rows are counted by CUR_SUPERSEDED and grouped separately).
#
# R_BEADSPROGRESS ("{closed}/{total}", or empty) and R_NEEDSREVIEW ("Y"/empty)
# support trunk-parked LEGACY handoffs — recorded on the trunk with no
# **Deliverable:** field, whose **Beads:** list mixes own work with
# context/epic beads. There the all-closed rule can't fire (a context bead
# never closes) yet branch/PR state is `unknown` (trunk guard), so the row
# renders 🟢 live forever. R_NEEDSREVIEW flags exactly those — partial bead
# closure on a trunk-parked, no-deliverable, otherwise-live current row — so
# the skill can surface a "this may be finished, check it" prompt rather than
# auto-archiving (which could clobber genuinely-live work). Handoffs WITH a
# **Deliverable:** field never need this — they classify cleanly via beadsdone.
R_STATE=()
R_PRSTATE=()
R_PRNUM=()
R_PRURL=()
R_ARCHCLASS=()
R_BEADSDONE=()
R_BEADSPROGRESS=()
R_NEEDSREVIEW=()
CUR_STALE=0
i=0
while [ "$i" -lt "$N" ]; do
    state="unknown"
    ps="unknown"; pnum=""; purl=""
    archclass=""
    beadsdone=""
    beadsprogress=""
    needsreview=""
    is_current=0
    if [ "$CURRENT_REPO_KEY" != "NONE" ] && [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ]; then
        is_current=1
    fi

    if [ "$CHECK_BRANCHES" -eq 1 ] && [ "$is_current" -eq 1 ]; then
        state=$(branch_state "${R_BRANCH[$i]}")
        IFS='|' read -r ps pnum purl <<< "$(pr_state "${R_BRANCH[$i]}" "${R_PRS[$i]}")"
    fi

    # Bead-closure is local — computed for current rows whenever beads exist,
    # even without --check-branches, so landscape's offline call benefits too.
    # The **Deliverable:** field (own-work beads) keys the check when present;
    # absent it, fall back to the full **Beads:** field (legacy handoffs).
    # Over-inclusion in Deliverable only ever UNDER-detects (a never-closing
    # bead keeps the row live) — safe; omitting an own-work bead is the only way
    # to false-positive, so wrap-up errs toward including.
    if [ "$is_current" -eq 1 ] && [ -n "$BEADS_AVAILABLE" ]; then
        bead_src="${R_DELIV[$i]}"
        [ -n "$bead_src" ] || bead_src="${R_BEADS[$i]}"
        read -r bclosed btotal <<< "$(beads_counts "$bead_src")"
        if [ "$btotal" -gt 0 ]; then
            beadsprogress="${bclosed}/${btotal}"
            [ "$bclosed" -eq "$btotal" ] && beadsdone="Y"
        fi
    fi

    if [ "$is_current" -eq 1 ]; then
        if [ -n "${R_SUPBY[$i]}" ]; then
            archclass="safe"
        elif [ "$ps" = "open" ]; then
            archclass=""
        elif [ "$ps" = "merged" ]; then
            archclass="safe"
        elif [ -n "$beadsdone" ]; then
            archclass="safe"
        elif [ "$ps" = "closed" ]; then
            archclass="keep"
        elif [ "$state" = "merged" ]; then
            archclass="safe"
        elif [ "$state" = "gone" ]; then
            archclass="keep"
        fi
        # "stale" group = archivable, but not via supersede.
        if [ -z "${R_SUPBY[$i]}" ] && [ -n "$archclass" ]; then
            CUR_STALE=$((CUR_STALE+1))
        fi
        # Trunk-parked legacy handoff that still renders live but has PARTIAL
        # bead closure (something shipped, something open) and no Deliverable
        # field to disambiguate → flag for the assisted prompt. All-closed rows
        # already became archclass=safe above; all-open rows are genuinely live.
        if [ -z "$archclass" ] && [ -z "${R_DELIV[$i]}" ] \
            && is_trunk_branch "${R_BRANCH[$i]}" && [ -n "$beadsprogress" ] \
            && [ "${beadsprogress%%/*}" -gt 0 ]; then
            needsreview="Y"
        fi
    fi

    R_STATE+=("$state")
    R_PRSTATE+=("$ps")
    R_PRNUM+=("$pnum")
    R_PRURL+=("$purl")
    R_ARCHCLASS+=("$archclass")
    R_BEADSDONE+=("$beadsdone")
    R_BEADSPROGRESS+=("$beadsprogress")
    R_NEEDSREVIEW+=("$needsreview")
    i=$((i+1))
done

# --- Current-repo "last session" + live-recent count (offline; for landscape) -
# LATEST_* is the newest current-repo handoff (records are newest-first, and the
# newest is always live — nothing newer can supersede it). recent_live counts
# recent current-repo handoffs that are still live work — archive-class empty,
# which excludes superseded AND finished (bead-closed; or, under --check-branches,
# merged/gone/closed) threads. So the morning nudge reflects distinct resumable
# threads, not re-wraps of the same one nor work that has already shipped.
CUR_RECENT_LIVE=0
LATEST_SLUG=""
LATEST_BRANCH=""
LATEST_DATE=""
# Per-handoff lines for the recent, non-superseded current-repo handoffs counted
# by CUR_RECENT_LIVE (newest first, same records). Lets landscape enumerate the
# few live threads inline instead of only naming the newest. Always emitted —
# survives --summary-only, since it's the summary-mode caller (landscape) that
# wants it.
CUR_LIVE_LINES=()
if [ "$CURRENT_REPO_KEY" != "NONE" ]; then
    i=0
    while [ "$i" -lt "$N" ]; do
        if [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ]; then
            if [ -z "$LATEST_DATE" ]; then
                LATEST_SLUG="${R_SLUG[$i]}"
                LATEST_BRANCH="${R_BRANCH[$i]}"
                LATEST_DATE="${R_DATE[$i]}"
            fi
            if [ -z "${R_ARCHCLASS[$i]}" ] \
                && { [[ "${R_DATE[$i]}" > "$CUTOFF" ]] || [ "${R_DATE[$i]}" = "$CUTOFF" ]; }; then
                CUR_RECENT_LIVE=$((CUR_RECENT_LIVE+1))
                CUR_LIVE_LINES+=("${R_SLUG[$i]}|${R_BRANCH[$i]}|${R_DATE[$i]}|${R_TIME[$i]}")
            fi
        fi
        i=$((i+1))
    done
fi

# --- Emit per-handoff lines (newest first; suppressed in --summary-only) ---
echo "---HANDOFFS---"
if [ "$SUMMARY_ONLY" -eq 0 ]; then
    i=0
    while [ "$i" -lt "$N" ]; do
        echo "${R_FILE[$i]}|${R_DATE[$i]}|${R_SLUG[$i]}|${R_CWD[$i]}|${R_BRANCH[$i]}|${R_REPO[$i]}|${R_EXISTS[$i]}|${R_SUPBY[$i]}|${R_SUPREASON[$i]}|${R_STATE[$i]}|${R_PRSTATE[$i]}|${R_PRNUM[$i]}|${R_PRURL[$i]}|${R_ARCHCLASS[$i]}|${R_TIME[$i]}|${R_BEADS[$i]}|${R_JIRA[$i]}|${R_BEADSDONE[$i]}|${R_DELIV[$i]}|${R_BEADSPROGRESS[$i]}|${R_NEEDSREVIEW[$i]}"
        i=$((i+1))
    done
fi

# Newest current-repo handoff (the "last session"), or empty line if none.
echo "---CURRENT-REPO-LATEST---"
if [ -n "$LATEST_DATE" ]; then
    echo "${LATEST_SLUG}|${LATEST_BRANCH}|${LATEST_DATE}"
fi

# Recent, non-superseded current-repo handoffs (newest first) — the live threads
# behind the current_repo_recent_live count. One `{slug}|{branch}|{date}|{time}`
# line each; first line is the same as ---CURRENT-REPO-LATEST--- when both exist.
# Empty when there are none.
echo "---CURRENT-REPO-LIVE---"
if [ "${#CUR_LIVE_LINES[@]}" -gt 0 ]; then
    for line in "${CUR_LIVE_LINES[@]}"; do
        echo "$line"
    done
fi

echo "---SUMMARY---"
echo "total=${TOTAL}"
echo "current_repo_total=${CUR_TOTAL}"
echo "current_repo_recent=${CUR_RECENT}"
echo "current_repo_recent_live=${CUR_RECENT_LIVE}"
echo "current_repo_pruned=${CUR_PRUNED}"
echo "current_repo_superseded=${CUR_SUPERSEDED}"
echo "current_repo_stale=${CUR_STALE}"
echo "other_repos=${#OTHER_KEYS[@]}"
echo "pruned_total=${PRUNED_TOTAL}"
echo "superseded_total=${SUPERSEDED_TOTAL}"
echo "unresolved=${UNRESOLVED_COUNT}"

echo "---OTHER-REPOS---"
# Sort other-repos by count desc, then by display name asc.
for i in "${!OTHER_KEYS[@]}"; do
    echo "${OTHER_COUNTS[$i]}|${OTHER_DISPLAYS[$i]}|${OTHER_KEYS[$i]}"
done | sort -t'|' -k1,1nr -k2,2 | awk -F'|' '{print $3"|"$1"|"$2}'

# --- Matched handoffs (only under --bead/--ticket) ------------------------
# Current-repo, NON-stale handoffs whose Beads/Jira field exactly contains the
# queried ID/KEY. "Non-stale" = R_ARCHCLASS empty: live, open-PR, or unknown.
# Superseded rows (archclass=safe) and merged/closed rows are dropped, so a
# resume nudge never points at dead context — the newer/live tip wins. Emitted
# only when a filter is active; absent otherwise, so existing parsers are
# untouched. Rows arrive newest-first (same order as ---HANDOFFS---).
# Line: {filename}|{date}|{time}|{slug}|{branch}|{exists}|{pr-state}|{pr-number}|{pr-url}
if [ -n "$MATCH_FILTER" ]; then
    echo "---MATCHED-HANDOFFS---"
    i=0
    while [ "$i" -lt "$N" ]; do
        if [ "$CURRENT_REPO_KEY" != "NONE" ] \
            && [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ] \
            && [ -z "${R_ARCHCLASS[$i]}" ]; then
            matched=0
            if [ -n "$MATCH_BEAD" ] && field_has_token "${R_BEADS[$i]}" "$MATCH_BEAD"; then matched=1; fi
            if [ -n "$MATCH_TICKET" ] && field_has_token "${R_JIRA[$i]}" "$MATCH_TICKET"; then matched=1; fi
            if [ "$matched" -eq 1 ]; then
                echo "${R_FILE[$i]}|${R_DATE[$i]}|${R_TIME[$i]}|${R_SLUG[$i]}|${R_BRANCH[$i]}|${R_EXISTS[$i]}|${R_PRSTATE[$i]}|${R_PRNUM[$i]}|${R_PRURL[$i]}"
            fi
        fi
        i=$((i+1))
    done
fi
