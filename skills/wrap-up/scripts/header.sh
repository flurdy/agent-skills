#!/usr/bin/env bash
# Emit header info for the wrap-up skill: date, cwd, branch, worktree detection,
# and the canonical repo root (parent of realpath of --git-common-dir).
# Sections are delimited by `---<NAME>---` markers for easy parsing.
set -uo pipefail

echo "---DATE---"
date '+%A %Y-%m-%d %H:%M'

echo "---CWD---"
pwd

echo "---BRANCH---"
git rev-parse --abbrev-ref HEAD 2>/dev/null

echo "---GIT-COMMON-DIR---"
git rev-parse --git-common-dir 2>/dev/null

echo "---GIT-DIR---"
git rev-parse --git-dir 2>/dev/null

echo "---REPO-ROOT---"
git rev-parse --git-common-dir 2>/dev/null | xargs -I {} realpath {} 2>/dev/null | xargs -r dirname

# Short name of the repo's default branch (main/master). Lets §4 detect when the
# cwd is parked on the trunk — a branch that almost never holds the session's
# work, so recording it would send /handoffs hunting for a PR that isn't there.
echo "---DEFAULT-BRANCH---"
def_ref=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
if [ -n "$def_ref" ]; then
    echo "${def_ref##*/}"
else
    for cand in main master; do
        if git rev-parse --verify --quiet "$cand" >/dev/null 2>&1 \
            || git rev-parse --verify --quiet "origin/$cand" >/dev/null 2>&1; then
            echo "$cand"; break
        fi
    done
fi

# Every worktree of this repo as `{path}|{branch}` (branch `(detached)` if so).
# §4 maps a feature branch found in today's activity back to the worktree that
# holds it, so the resume block can point at where the work actually lives.
echo "---WORKTREES---"
git worktree list --porcelain 2>/dev/null | awk '
    /^worktree /{ path=$2 }
    /^branch /{ b=$2; sub(/^refs\/heads\//,"",b); print path "|" b }
    /^detached$/{ print path "|(detached)" }
'

# Permission entries living only in a linked worktree's settings file — gone if
# that worktree is pruned. One `{path}|{basename}|{count}` line per drifting file
# (`parse-error` instead of a count when the file isn't valid JSON). §3c flags
# these and offers /tidy-settings, which owns the promotion flow.
echo "---SETTINGS-DRIFT---"
python3 - <<'PY' 2>/dev/null || true
import json, os, subprocess, sys

def entries(path):
    try:
        with open(path) as f:
            perms = json.load(f).get("permissions") or {}
    except OSError:
        return set()  # missing canonical file: every worktree entry is drift
    except Exception:
        return None
    return {(s, e) for s in ("allow", "deny", "ask") for e in (perms.get(s) or [])}

out = subprocess.run(["git", "worktree", "list", "--porcelain"],
                     capture_output=True, text=True).stdout
wts = [l[len("worktree "):] for l in out.splitlines() if l.startswith("worktree ")]
if len(wts) < 2:
    sys.exit(0)
canon = os.path.realpath(os.path.join(wts[0], ".claude"))
for wt in wts[1:]:
    cdir = os.path.join(wt, ".claude")
    if not os.path.isdir(cdir) or os.path.realpath(cdir) == canon:
        continue
    for base in ("settings.json", "settings.local.json"):
        wfile = os.path.join(cdir, base)
        if not os.path.isfile(wfile):
            continue
        wset = entries(wfile)
        if wset is None:
            print(f"{wt}|{base}|parse-error")
            continue
        cset = entries(os.path.join(canon, base)) or set()
        drift = len(wset - cset)
        if drift:
            print(f"{wt}|{base}|{drift}")
PY
