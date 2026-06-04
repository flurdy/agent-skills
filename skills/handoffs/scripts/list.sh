#!/usr/bin/env bash
# List Claude Code handoff files (~/.claude/handoffs/*.md) with metadata.
# Sections delimited by `---<NAME>---` markers. Companion to the wrap-up skill.
#
# Usage: list.sh [--recent-days N] [--summary-only]
#   --recent-days N   override the "recent" window (default: 3, with Mon=3, Tue=4
#                     weekend buffer to mirror gh-pr-list-closed.sh)
#   --summary-only    suppress per-file lines in the HANDOFFS section (landscape's
#                     footer only needs the SUMMARY counts)
set -uo pipefail

HANDOFFS_DIR="${HOME}/.claude/handoffs"

RECENT_DAYS=""
SUMMARY_ONLY=0
CHECK_BRANCHES=0
while [ $# -gt 0 ]; do
    case "$1" in
        --recent-days) RECENT_DAYS="$2"; shift 2 ;;
        --summary-only) SUMMARY_ONLY=1; shift ;;
        --check-branches) CHECK_BRANCHES=1; shift ;;
        *) shift ;;
    esac
done
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

# Look up the PR state for a branch from the cached `gh` listing. Echoes
# `{state}|{number}|{url}` where state ∈ merged|open|closed (a real PR exists),
# `none||` when gh ran but found no PR for the branch, or `unknown||` when gh
# wasn't consulted (no --check-branches, no gh, offline, or branch `?`).
# Precedence when a branch has several PRs: merged > open > closed.
pr_state() {
    local b="$1"
    { [ "$PR_OK" -eq 1 ] && [ "$b" != "?" ]; } || { echo "unknown||"; return; }
    local best_rank=0 best="none||"
    local hb st num url rank
    while IFS=$'\t' read -r hb st num url; do
        [ "$hb" = "$b" ] || continue
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
# Precedence: supersede > open PR > merged PR > closed PR > local merged > gone.
# A merged PR is ground truth that beats local ancestry — the fix for
# squash-merges, where the branch is never an ancestor of the default tip.
# CUR_STALE counts the §3b "stale" group: archivable for a NON-supersede reason
# (superseded rows are counted by CUR_SUPERSEDED and grouped separately).
R_STATE=()
R_PRSTATE=()
R_PRNUM=()
R_PRURL=()
R_ARCHCLASS=()
CUR_STALE=0
i=0
while [ "$i" -lt "$N" ]; do
    state="unknown"
    ps="unknown"; pnum=""; purl=""
    archclass=""
    is_current=0
    if [ "$CURRENT_REPO_KEY" != "NONE" ] && [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ]; then
        is_current=1
    fi

    if [ "$CHECK_BRANCHES" -eq 1 ] && [ "$is_current" -eq 1 ]; then
        state=$(branch_state "${R_BRANCH[$i]}")
        IFS='|' read -r ps pnum purl <<< "$(pr_state "${R_BRANCH[$i]}")"
    fi

    if [ "$is_current" -eq 1 ]; then
        if [ -n "${R_SUPBY[$i]}" ]; then
            archclass="safe"
        elif [ "$ps" = "open" ]; then
            archclass=""
        elif [ "$ps" = "merged" ]; then
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
    fi

    R_STATE+=("$state")
    R_PRSTATE+=("$ps")
    R_PRNUM+=("$pnum")
    R_PRURL+=("$purl")
    R_ARCHCLASS+=("$archclass")
    i=$((i+1))
done

# --- Current-repo "last session" + live-recent count (offline; for landscape) -
# LATEST_* is the newest current-repo handoff (records are newest-first, and the
# newest is always live — nothing newer can supersede it). recent_live counts
# recent current-repo handoffs that aren't superseded, so the morning nudge
# reflects distinct resumable threads rather than re-wraps of the same one.
CUR_RECENT_LIVE=0
LATEST_SLUG=""
LATEST_BRANCH=""
LATEST_DATE=""
if [ "$CURRENT_REPO_KEY" != "NONE" ]; then
    i=0
    while [ "$i" -lt "$N" ]; do
        if [ "${R_REPO[$i]}" = "$CURRENT_REPO_KEY" ]; then
            if [ -z "$LATEST_DATE" ]; then
                LATEST_SLUG="${R_SLUG[$i]}"
                LATEST_BRANCH="${R_BRANCH[$i]}"
                LATEST_DATE="${R_DATE[$i]}"
            fi
            if [ -z "${R_SUPBY[$i]}" ] \
                && { [[ "${R_DATE[$i]}" > "$CUTOFF" ]] || [ "${R_DATE[$i]}" = "$CUTOFF" ]; }; then
                CUR_RECENT_LIVE=$((CUR_RECENT_LIVE+1))
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
        echo "${R_FILE[$i]}|${R_DATE[$i]}|${R_SLUG[$i]}|${R_CWD[$i]}|${R_BRANCH[$i]}|${R_REPO[$i]}|${R_EXISTS[$i]}|${R_SUPBY[$i]}|${R_SUPREASON[$i]}|${R_STATE[$i]}|${R_PRSTATE[$i]}|${R_PRNUM[$i]}|${R_PRURL[$i]}|${R_ARCHCLASS[$i]}|${R_TIME[$i]}"
        i=$((i+1))
    done
fi

# Newest current-repo handoff (the "last session"), or empty line if none.
echo "---CURRENT-REPO-LATEST---"
if [ -n "$LATEST_DATE" ]; then
    echo "${LATEST_SLUG}|${LATEST_BRANCH}|${LATEST_DATE}"
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
