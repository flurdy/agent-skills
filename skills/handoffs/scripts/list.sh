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
while [ $# -gt 0 ]; do
    case "$1" in
        --recent-days) RECENT_DAYS="$2"; shift 2 ;;
        --summary-only) SUMMARY_ONLY=1; shift ;;
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

echo "---HANDOFFS---"
TOTAL=0
CUR_TOTAL=0
CUR_RECENT=0
CUR_PRUNED=0
PRUNED_TOTAL=0
UNRESOLVED_COUNT=0
# Parallel arrays for per-repo aggregation (bash 3.2 compatible — macOS).
OTHER_KEYS=()
OTHER_DISPLAYS=()
OTHER_COUNTS=()

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

        if [ "$SUMMARY_ONLY" -eq 0 ]; then
            echo "${BASE}|${DATE}|${SLUG}|${CWD}|${BRANCH}|${REPO_KEY}|${EXISTS}"
        fi

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

echo "---SUMMARY---"
echo "total=${TOTAL}"
echo "current_repo_total=${CUR_TOTAL}"
echo "current_repo_recent=${CUR_RECENT}"
echo "current_repo_pruned=${CUR_PRUNED}"
echo "other_repos=${#OTHER_KEYS[@]}"
echo "pruned_total=${PRUNED_TOTAL}"
echo "unresolved=${UNRESOLVED_COUNT}"

echo "---OTHER-REPOS---"
# Sort other-repos by count desc, then by display name asc.
for i in "${!OTHER_KEYS[@]}"; do
    echo "${OTHER_COUNTS[$i]}|${OTHER_DISPLAYS[$i]}|${OTHER_KEYS[$i]}"
done | sort -t'|' -k1,1nr -k2,2 | awk -F'|' '{print $3"|"$1"|"$2}'
