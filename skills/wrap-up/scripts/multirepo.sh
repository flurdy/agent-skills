#!/usr/bin/env bash
# Multi-repo working-copy roll-up for /wrap-up §3b.
#
# The default hygiene probe (landscape/working-copy.sh) only inspects the cwd repo.
# In a multi-repo workspace (mgit services, or git submodules) that silently misses
# unpushed/uncommitted state in sibling repos. This walks every member repo and emits
# its branch / ahead / behind / dirty counts so the wrap-up can roll them up.
#
# Detection (first match wins):
#   - .mgit.conf at repo root  -> mgit workspace (parse `services=a,b,c`)
#   - .gitmodules at repo root -> git submodules
#   - otherwise                -> single repo (marker=none, nothing to roll up)
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

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$root" ]; then
  echo "---MARKER---"; echo "none"
  echo "---ROOT---"
  echo "---REPOS---"
  exit 0
fi

marker="none"
members=()   # relative paths from root; "." is the root repo itself
if [ -f "$root/.mgit.conf" ]; then
  marker="mgit"
  services="$(sed -n 's/^services=//p' "$root/.mgit.conf" | head -1)"
  members+=(".")
  IFS=',' read -r -a svc <<< "$services"
  for s in "${svc[@]}"; do
    s="$(echo "$s" | tr -d '[:space:]')"
    [ -n "$s" ] && members+=("$s")
  done
elif [ -f "$root/.gitmodules" ]; then
  marker="submodules"
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
