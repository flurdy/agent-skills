#!/usr/bin/env bash
# Multi-repo working-copy roll-up for /wrap-up §3b.
#
# The default hygiene probe (landscape/working-copy.sh) only inspects the cwd repo.
# In a multi-repo workspace (mgit services, or git submodules) that silently misses
# unpushed/uncommitted state in sibling repos. This walks every member repo and emits
# its branch / ahead / behind / dirty counts so the wrap-up can roll them up.
#
# Workspace-root detection (first match wins):
#   - $MGIT_ROOT, when it points at a directory holding .mgit.conf
#   - nearest ancestor holding .mgit.conf  -> mgit workspace (parse `services=a,b,c`)
#   - nearest ancestor holding .gitmodules -> git submodules
#   - nearest ancestor with a *child* directory whose .mgit.conf lists this repo
#   - otherwise                            -> single repo (marker=none, nothing to roll up)
#
# The child-directory step exists because a member repo is usually not inside the
# workspace: mgit links siblings in via repos/<name> symlinks, so .mgit.conf sits at
# ~/w/workspace/.mgit.conf while the repo lives at ~/w/<name>. It is a sibling, never
# an ancestor, so an ancestor-only walk reports marker=none from every member repo.
# Candidates are accepted only when `services=` actually resolves to this repo — one
# parent can hold several unrelated workspaces, and proximity alone would mis-assign.
#
# Output (delimited; parse, don't eyeball):
#   ---MARKER---  mgit | submodules | none
#   ---ROOT---    <absolute repo root>
#   ---REPOS---
#   <name>|<branch>|<ahead>|<behind>|<upstream>|<modified>|<untracked>
#   ... (one line per member repo, including the root repo itself as ".")
#
# ahead/behind are "-" when there is no upstream. upstream is yes|no.
set -u

mgit_services() {   # $1 = dir holding .mgit.conf; prints one service path per line
  sed -n 's/^services=//p' "$1/.mgit.conf" | head -1 | tr ',' '\n' | tr -d '[:blank:]'
}

mgit_claims_repo() {   # $1 = candidate workspace dir, $2 = resolved repo root
  local s
  [ -n "$2" ] || return 1
  while IFS= read -r s; do
    [ -n "$s" ] || continue
    [ "$(readlink -f "$1/$s" 2>/dev/null)" = "$2" ] && return 0
  done < <(mgit_services "$1")
  return 1
}

self="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$self" ] && self="$(readlink -f "$self")"

root=""
marker="none"
if [ -n "${MGIT_ROOT:-}" ] && [ -f "${MGIT_ROOT}/.mgit.conf" ]; then
  root="$(readlink -f "$MGIT_ROOT")"
  marker="mgit"
else
  d="$(readlink -f "${PWD}")"
  while : ; do
    if [ -f "$d/.mgit.conf" ]; then
      root="$d"; marker="mgit"; break
    fi
    if [ -f "$d/.gitmodules" ] && [ -e "$d/.git" ]; then
      root="$d"; marker="submodules"; break
    fi
    for conf in "$d"/*/.mgit.conf; do
      [ -f "$conf" ] || continue
      ws="$(dirname "$conf")"
      if mgit_claims_repo "$ws" "$self"; then
        root="$ws"; marker="mgit"; break 2
      fi
    done
    [ "$d" = "/" ] && break
    d="$(dirname "$d")"
  done
fi

[ -z "$root" ] && root="$self"
if [ -z "$root" ]; then
  echo "---MARKER---"; echo "none"
  echo "---ROOT---"
  echo "---REPOS---"
  exit 0
fi

members=()   # relative paths from root; "." is the root repo itself
if [ "$marker" = "mgit" ]; then
  members+=(".")
  while IFS= read -r s; do
    [ -n "$s" ] && members+=("$s")
  done < <(mgit_services "$root")
elif [ "$marker" = "submodules" ]; then
  members+=(".")
  while IFS= read -r p; do
    [ -n "$p" ] && members+=("$p")
  done < <(git -C "$root" config --file .gitmodules --get-regexp '\.path$' 2>/dev/null | awk '{print $2}')
fi

echo "---MARKER---"; echo "$marker"
echo "---ROOT---"; echo "$root"
echo "---REPOS---"
[ "$marker" = "none" ] && exit 0

for m in "${members[@]}"; do
  dir="$root/$m"
  git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || continue
  name="$m"; [ "$m" = "." ] && name="$(basename "$root")"
  branch="$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  if git -C "$dir" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    upstream="yes"
    ahead="$(git -C "$dir" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
    behind="$(git -C "$dir" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
  else
    upstream="no"; ahead="-"; behind="-"
  fi
  modified="$(git -C "$dir" status --porcelain 2>/dev/null | grep -cv '^??')"
  untracked="$(git -C "$dir" status --porcelain 2>/dev/null | grep -c '^??')"
  echo "${name}|${branch}|${ahead}|${behind}|${upstream}|${modified}|${untracked}"
done
