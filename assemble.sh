#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SHARED_REPO="${SHARED_REPO:-$SCRIPT_DIR}"
PRIVATE_REPO="${PRIVATE_REPO:-$SCRIPT_DIR/../agent-skills-private}"

SHARED_REPO="$(cd "$SHARED_REPO" 2>/dev/null && pwd || printf '%s' "$SHARED_REPO")"
[[ -d "$PRIVATE_REPO" ]] && PRIVATE_REPO="$(cd "$PRIVATE_REPO" && pwd)"

SHARED_SKILLS_DIR="${SHARED_SKILLS_DIR:-$SHARED_REPO/skills}"
PRIVATE_SKILLS_DIR="${PRIVATE_SKILLS_DIR:-$PRIVATE_REPO/skills}"
SHARED_AGENTS_DIR="${SHARED_AGENTS_DIR:-$SHARED_REPO/agents}"
PRIVATE_AGENTS_DIR="${PRIVATE_AGENTS_DIR:-$PRIVATE_REPO/agents}"
PRIVATE_MACHINES_DIR="${PRIVATE_MACHINES_DIR:-$PRIVATE_REPO/machines}"
PRIVATE_CLIENTS_DIR="${PRIVATE_CLIENTS_DIR:-$PRIVATE_REPO/clients}"
PROFILES_DIR="${PROFILES_DIR:-$PRIVATE_REPO/profiles}"

SKILLS_DIR="${SKILLS_DIR:-$HOME/.agents/skills}"
CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
LEGACY_CODEX_SKILLS_DIR="${LEGACY_CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
AGENTS_DIR="${AGENTS_DIR:-$HOME/.claude/agents}"
SKIP_AGENTS="${SKIP_AGENTS:-0}"
LAYERS_ORDER="${LAYERS_ORDER:-shared private machine clients}"
PI_SETTINGS_FILE="${PI_SETTINGS_FILE:-$HOME/.pi/agent/settings.json}"

log() { printf '%s\n' "$*"; }
err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  assemble.sh apply [--profile NAME] [--machine NAME] [--clients "a b c"] [--dry-run]
  assemble.sh clean [--dry-run]
  assemble.sh doctor
  assemble.sh list

Notes:
- Installs managed skill links in SKILLS_DIR (default: ~/.agents/skills).
- Creates per-skill Claude compatibility aliases in CLAUDE_SKILLS_DIR.
- Removes old managed links from LEGACY_CODEX_SKILLS_DIR during apply/clean.
- Installs Claude-style agents in AGENTS_DIR unless SKIP_AGENTS=1.
- Preserves unmanaged files, directories, and third-party symlinks.
- Refuses symlinked destination roots and collisions before making changes.

Env:
  SHARED_REPO, PRIVATE_REPO, SKILLS_DIR, CLAUDE_SKILLS_DIR,
  LEGACY_CODEX_SKILLS_DIR, AGENTS_DIR, SKIP_AGENTS, LAYERS_ORDER,
  PI_SETTINGS_FILE
EOF
}

load_profile() {
  local profile="$1"
  local file="$PROFILES_DIR/$profile.env"
  [[ -f "$file" ]] || err "Profile not found: $file"
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
}

lexical_path() {
  realpath -ms -- "$1"
}

physical_path() {
  realpath -m -- "$1"
}

same_path() {
  [[ "$(physical_path "$1")" == "$(physical_path "$2")" ]]
}

paths_overlap() {
  local first
  local second
  first="$(physical_path "$1")"
  second="$(physical_path "$2")"
  [[ "$first" == "$second" || "$first" == "$second"/* || "$second" == "$first"/* ]]
}

symlink_target_path() {
  local link="$1"
  local target
  target="$(readlink -- "$link")"
  if [[ "$target" == /* ]]; then
    lexical_path "$target"
  else
    lexical_path "$(dirname -- "$link")/$target"
  fi
}

path_is_lexically_within() {
  local path="$1"
  local root="$2"
  [[ "$(lexical_path "$path")" == "$(lexical_path "$root")"/* ]]
}

is_repo_managed_symlink() {
  local link="$1"
  local target
  [[ -L "$link" ]] || return 1
  target="$(symlink_target_path "$link")"
  path_is_lexically_within "$target" "$SHARED_REPO" \
    || path_is_lexically_within "$target" "$PRIVATE_REPO"
}

is_claude_compat_symlink() {
  local link="$1"
  [[ -L "$link" ]] || return 1
  path_is_lexically_within "$(symlink_target_path "$link")" "$SKILLS_DIR"
}

is_managed_symlink() {
  local ownership="$1"
  local link="$2"
  if [[ "$ownership" == "claude" ]]; then
    is_repo_managed_symlink "$link" || is_claude_compat_symlink "$link"
  else
    is_repo_managed_symlink "$link"
  fi
}

assert_safe_root() {
  local label="$1"
  local target_dir="$2"
  if [[ -L "$target_dir" ]]; then
    err "$label is a symlink; refusing to replace or traverse it: $target_dir"
  fi
  if [[ -e "$target_dir" && ! -d "$target_dir" ]]; then
    err "$label exists but is not a directory: $target_dir"
  fi
}

assert_distinct_roots() {
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    if same_path "$AGENTS_DIR" "$SKILLS_DIR"; then
      err "AGENTS_DIR must differ from SKILLS_DIR"
    fi
    if same_path "$AGENTS_DIR" "$CLAUDE_SKILLS_DIR"; then
      err "AGENTS_DIR must differ from CLAUDE_SKILLS_DIR"
    fi
  fi

  local root
  for root in "$SKILLS_DIR" "$CLAUDE_SKILLS_DIR" "$LEGACY_CODEX_SKILLS_DIR"; do
    if paths_overlap "$root" "$SHARED_REPO" || paths_overlap "$root" "$PRIVATE_REPO"; then
      err "Managed destination overlaps a source repository: $root"
    fi
  done
  if [[ "$SKIP_AGENTS" -eq 0 ]] \
    && { paths_overlap "$AGENTS_DIR" "$SHARED_REPO" || paths_overlap "$AGENTS_DIR" "$PRIVATE_REPO"; }; then
    err "Managed destination overlaps a source repository: $AGENTS_DIR"
  fi
}

preflight_roots() {
  assert_distinct_roots
  assert_safe_root "Skills root" "$SKILLS_DIR"
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    assert_safe_root "Claude skills root" "$CLAUDE_SKILLS_DIR"
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    assert_safe_root "Agents root" "$AGENTS_DIR"
  fi
  if ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$SKILLS_DIR" \
    && ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$CLAUDE_SKILLS_DIR"; then
    assert_safe_root "Legacy Codex skills root" "$LEGACY_CODEX_SKILLS_DIR"
  fi
}

ensure_target_dir() {
  local target_dir="$1"
  local dry_run="$2"
  if [[ -d "$target_dir" ]]; then
    return 0
  fi
  if [[ "$dry_run" -eq 1 ]]; then
    log "DRY: mkdir -p '$target_dir'"
  else
    mkdir -p "$target_dir"
  fi
}

clean_managed_symlinks_in() {
  local target_dir="$1"
  local dry_run="$2"
  local ownership="$3"
  local removed=0
  local item

  [[ -d "$target_dir" ]] || { printf '0\n'; return 0; }

  shopt -s nullglob dotglob
  for item in "$target_dir"/*; do
    if is_managed_symlink "$ownership" "$item"; then
      if [[ "$dry_run" -eq 1 ]]; then
        log "DRY: rm '$item' -> $(readlink -- "$item")" >&2
      else
        rm -f -- "$item"
      fi
      ((removed++)) || true
    fi
  done
  shopt -u nullglob dotglob
  printf '%s\n' "$removed"
}

declare -A DESIRED_SKILLS=()
declare -A DESIRED_SKILL_LABELS=()
declare -A DESIRED_AGENTS=()
declare -A DESIRED_AGENT_LABELS=()

collect_skill_units() {
  local source_dir="$1"
  local label="$2"
  local child
  local name

  [[ -d "$source_dir" ]] || return 0
  log "Selecting skills: $label ($source_dir)"
  shopt -s nullglob dotglob
  for child in "$source_dir"/*; do
    [[ -d "$child" && -f "$child/SKILL.md" ]] || continue
    name="$(basename -- "$child")"
    # shellcheck disable=SC2034  # Read later through a nameref.
    DESIRED_SKILLS["$name"]="$child"
    # shellcheck disable=SC2034  # Read later through a nameref.
    DESIRED_SKILL_LABELS["$name"]="$label"
  done
  shopt -u nullglob dotglob
}

collect_agent_units() {
  local source_dir="$1"
  local label="$2"
  local child
  local name

  [[ "$SKIP_AGENTS" -eq 1 || ! -d "$source_dir" ]] && return 0
  log "Selecting agents: $label ($source_dir)"
  shopt -s nullglob dotglob
  for child in "$source_dir"/*.md; do
    [[ -f "$child" ]] || continue
    name="$(basename -- "$child")"
    [[ "$name" == "README.md" ]] && continue
    # shellcheck disable=SC2034  # Read later through a nameref.
    DESIRED_AGENTS["$name"]="$child"
    # shellcheck disable=SC2034  # Read later through a nameref.
    DESIRED_AGENT_LABELS["$name"]="$label"
  done
  shopt -u nullglob dotglob
}

collect_layer() {
  local skills_dir="$1"
  local agents_dir="$2"
  local label="$3"
  collect_skill_units "$skills_dir" "$label"
  collect_agent_units "$agents_dir" "$label"
}

collect_desired_units() {
  local machine="$1"
  local clients="$2"
  local layer
  local client

  for layer in $LAYERS_ORDER; do
    case "$layer" in
      shared)
        collect_layer "$SHARED_SKILLS_DIR" "$SHARED_AGENTS_DIR" "shared"
        ;;
      private)
        collect_layer "$PRIVATE_SKILLS_DIR" "$PRIVATE_AGENTS_DIR" "private"
        ;;
      machine)
        collect_layer "$PRIVATE_MACHINES_DIR/$machine/skills" \
          "$PRIVATE_MACHINES_DIR/$machine/agents" "machine:$machine"
        ;;
      clients)
        if [[ -n "$clients" ]]; then
          for client in $clients; do
            collect_layer "$PRIVATE_CLIENTS_DIR/$client/skills" \
              "$PRIVATE_CLIENTS_DIR/$client/agents" "client:$client"
          done
        else
          log "No clients specified."
        fi
        ;;
      *) err "Unknown layer in LAYERS_ORDER: '$layer'" ;;
    esac
  done
}

preflight_collisions() {
  local destination="$1"
  local ownership="$2"
  local unit_label="$3"
  local desired_name="$4"
  local name
  local path
  local -n desired="$desired_name"

  for name in "${!desired[@]}"; do
    path="$destination/$name"
    if [[ -e "$path" || -L "$path" ]]; then
      if ! is_managed_symlink "$ownership" "$path"; then
        err "Collision: $unit_label '$name' already exists and is not managed by this assembler.
  Existing: $path
  Attempted: ${desired[$name]}
No changes were made. Move or remove the existing entry before retrying."
      fi
    fi
  done
}

preflight_apply() {
  preflight_roots
  preflight_collisions "$SKILLS_DIR" repo "skill" DESIRED_SKILLS
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    preflight_collisions "$CLAUDE_SKILLS_DIR" claude "Claude skill alias" DESIRED_SKILLS
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    preflight_collisions "$AGENTS_DIR" repo "agent" DESIRED_AGENTS
  fi
}

sorted_keys() {
  local array_name="$1"
  local -n values="$array_name"
  printf '%s\n' "${!values[@]}" | LC_ALL=C sort
}

declare -a STAGE_DIRS=()
LAST_STAGE_DIR=""

cleanup_stages() {
  local stage
  for stage in "${STAGE_DIRS[@]}"; do
    [[ -d "$stage" ]] && rm -rf -- "$stage"
  done
  STAGE_DIRS=()
}

stage_desired_units() {
  local destination="$1"
  local desired_name="$2"
  local target_mode="$3"
  local stage
  local name
  local target
  local -n desired="$desired_name"

  stage="$(mktemp -d "$destination/.agent-skills-stage.XXXXXX")"
  STAGE_DIRS+=("$stage")
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if [[ "$target_mode" == "claude" ]]; then
      target="$SKILLS_DIR/$name"
    else
      target="${desired[$name]}"
    fi
    ln -s "$target" "$stage/$name"
  done < <(sorted_keys "$desired_name")
  LAST_STAGE_DIR="$stage"
}

commit_staged_units() {
  local destination="$1"
  local ownership="$2"
  local stage="$3"
  local item
  local name
  local target

  shopt -s nullglob
  for item in "$stage"/*; do
    name="$(basename -- "$item")"
    target="$destination/$name"
    if [[ -e "$target" || -L "$target" ]]; then
      if ! is_managed_symlink "$ownership" "$target"; then
        err "Destination changed after preflight; refusing to replace: $target"
      fi
    fi
    mv -Tf -- "$item" "$target"
  done
  shopt -u nullglob
}

log_desired_units() {
  local destination="$1"
  local desired_name="$2"
  local labels_name="$3"
  local target_mode="$4"
  local name
  local target
  local -n desired="$desired_name"
  local -n labels="$labels_name"

  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if [[ "$target_mode" == "claude" ]]; then
      target="$SKILLS_DIR/$name"
    else
      target="${desired[$name]}"
    fi
    log "DRY: ln -s '$target' '$destination/$name' (${labels[$name]})"
  done < <(sorted_keys "$desired_name")
}

remove_stale_managed_links() {
  local destination="$1"
  local ownership="$2"
  local desired_name="$3"
  local dry_run="$4"
  local item
  local name
  local removed=0
  local -n desired="$desired_name"

  [[ -d "$destination" ]] || { printf '0\n'; return 0; }
  shopt -s nullglob dotglob
  for item in "$destination"/*; do
    name="$(basename -- "$item")"
    if is_managed_symlink "$ownership" "$item" && [[ -z "${desired[$name]+present}" ]]; then
      if [[ "$dry_run" -eq 1 ]]; then
        log "DRY: rm '$item' -> $(readlink -- "$item")" >&2
      else
        rm -f -- "$item"
      fi
      ((removed++)) || true
    fi
  done
  shopt -u nullglob dotglob
  printf '%s\n' "$removed"
}

install_desired_units() {
  local dry_run="$1"
  local canonical_stage
  local claude_stage=""
  local agents_stage=""
  local removed

  if [[ "$dry_run" -eq 1 ]]; then
    log_desired_units "$SKILLS_DIR" DESIRED_SKILLS DESIRED_SKILL_LABELS repo
    if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
      log_desired_units "$CLAUDE_SKILLS_DIR" DESIRED_SKILLS DESIRED_SKILL_LABELS claude
    fi
    if [[ "$SKIP_AGENTS" -eq 0 ]]; then
      log_desired_units "$AGENTS_DIR" DESIRED_AGENTS DESIRED_AGENT_LABELS repo
    fi
  else
    trap cleanup_stages EXIT
    stage_desired_units "$SKILLS_DIR" DESIRED_SKILLS repo
    canonical_stage="$LAST_STAGE_DIR"
    if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
      stage_desired_units "$CLAUDE_SKILLS_DIR" DESIRED_SKILLS claude
      claude_stage="$LAST_STAGE_DIR"
    fi
    if [[ "$SKIP_AGENTS" -eq 0 ]]; then
      stage_desired_units "$AGENTS_DIR" DESIRED_AGENTS repo
      agents_stage="$LAST_STAGE_DIR"
    fi

    commit_staged_units "$SKILLS_DIR" repo "$canonical_stage"
    [[ -n "$claude_stage" ]] && commit_staged_units "$CLAUDE_SKILLS_DIR" claude "$claude_stage"
    [[ -n "$agents_stage" ]] && commit_staged_units "$AGENTS_DIR" repo "$agents_stage"
  fi

  removed="$(remove_stale_managed_links "$SKILLS_DIR" repo DESIRED_SKILLS "$dry_run")"
  log "Removed $removed stale managed skill link(s) from $SKILLS_DIR"
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    removed="$(remove_stale_managed_links "$CLAUDE_SKILLS_DIR" claude DESIRED_SKILLS "$dry_run")"
    log "Removed $removed stale managed Claude alias(es) from $CLAUDE_SKILLS_DIR"
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    removed="$(remove_stale_managed_links "$AGENTS_DIR" repo DESIRED_AGENTS "$dry_run")"
    log "Removed $removed stale managed agent link(s) from $AGENTS_DIR"
  fi
  if ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$SKILLS_DIR" \
    && ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$CLAUDE_SKILLS_DIR"; then
    removed="$(clean_managed_symlinks_in "$LEGACY_CODEX_SKILLS_DIR" "$dry_run" repo)"
    log "Cleaned $removed legacy managed Codex skill link(s) from $LEGACY_CODEX_SKILLS_DIR"
  fi

  if [[ "$dry_run" -eq 0 ]]; then
    cleanup_stages
    trap - EXIT
  fi
}

clean_installation() {
  local dry_run="$1"
  local removed

  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    removed="$(clean_managed_symlinks_in "$CLAUDE_SKILLS_DIR" "$dry_run" claude)"
    log "Cleaned $removed managed Claude skill alias(es) from $CLAUDE_SKILLS_DIR"
  fi

  if ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$SKILLS_DIR" \
    && ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$CLAUDE_SKILLS_DIR"; then
    removed="$(clean_managed_symlinks_in "$LEGACY_CODEX_SKILLS_DIR" "$dry_run" repo)"
    log "Cleaned $removed legacy managed Codex skill link(s) from $LEGACY_CODEX_SKILLS_DIR"
  fi

  removed="$(clean_managed_symlinks_in "$SKILLS_DIR" "$dry_run" repo)"
  log "Cleaned $removed managed skill link(s) from $SKILLS_DIR"

  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    removed="$(clean_managed_symlinks_in "$AGENTS_DIR" "$dry_run" repo)"
    log "Cleaned $removed managed agent link(s) from $AGENTS_DIR"
  fi
}

managed_count() {
  local target_dir="$1"
  local ownership="$2"
  local count=0
  local item
  [[ -d "$target_dir" ]] || { printf '0\n'; return 0; }
  shopt -s nullglob dotglob
  for item in "$target_dir"/*; do
    is_managed_symlink "$ownership" "$item" && ((count++)) || true
  done
  shopt -u nullglob dotglob
  printf '%s\n' "$count"
}

report_target_dir() {
  local label="$1"
  local target_dir="$2"
  local ownership="$3"
  local managed=0
  local unmanaged=0
  local item

  if [[ -L "$target_dir" ]]; then
    log "$label: unsafe root symlink -> $(readlink -- "$target_dir")"
    return 1
  fi
  if [[ ! -d "$target_dir" ]]; then
    log "$label: not present yet ($target_dir)"
    return 1
  fi

  shopt -s nullglob dotglob
  for item in "$target_dir"/*; do
    if is_managed_symlink "$ownership" "$item"; then
      ((managed++)) || true
    else
      ((unmanaged++)) || true
    fi
  done
  shopt -u nullglob dotglob
  log "$label: $target_dir"
  log "  Managed:   $managed"
  log "  Unmanaged: $unmanaged"
}

pi_uses_claude_skills() {
  [[ -f "$PI_SETTINGS_FILE" ]] || return 1
  python3 - "$PI_SETTINGS_FILE" "$CLAUDE_SKILLS_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

try:
    settings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
expected = Path(os.path.expanduser(sys.argv[2])).resolve(strict=False)
for entry in settings.get("skills", []):
    if isinstance(entry, str) and Path(os.path.expanduser(entry)).resolve(strict=False) == expected:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

warn_pi_legacy_setting() {
  if pi_uses_claude_skills; then
    log "WARN: Pi settings still load $CLAUDE_SKILLS_DIR; remove that entry after verifying $SKILLS_DIR discovery to avoid duplicate skills."
  fi
}

cmd_list() {
  log "Machines (private):"
  [[ -d "$PRIVATE_MACHINES_DIR" ]] \
    && find "$PRIVATE_MACHINES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '  %f\n' | sort \
    || true
  log ""
  log "Clients (private):"
  [[ -d "$PRIVATE_CLIENTS_DIR" ]] \
    && find "$PRIVATE_CLIENTS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '  %f\n' | sort \
    || true
  log ""
  log "Profiles (private):"
  [[ -d "$PROFILES_DIR" ]] \
    && find "$PROFILES_DIR" -mindepth 1 -maxdepth 1 -type f -name '*.env' -printf '  %f\n' \
      | sed 's/\.env$//' | sort \
    || true
}

DOCTOR_ERRORS=0

doctor_error() {
  log "ERROR: $*"
  ((DOCTOR_ERRORS++)) || true
}

verify_desired_links() {
  local destination="$1"
  local ownership="$2"
  local desired_name="$3"
  local target_mode="$4"
  local name
  local path
  local expected
  local item
  local -n desired="$desired_name"

  for name in "${!desired[@]}"; do
    path="$destination/$name"
    if [[ ! -L "$path" ]] || ! is_managed_symlink "$ownership" "$path"; then
      doctor_error "Missing managed link: $path"
      continue
    fi
    if [[ "$target_mode" == "claude" ]]; then
      expected="$SKILLS_DIR/$name"
    else
      expected="${desired[$name]}"
    fi
    if [[ "$(symlink_target_path "$path")" != "$(lexical_path "$expected")" ]]; then
      doctor_error "Incorrect link target: $path"
    fi
  done

  [[ -d "$destination" ]] || return 0
  shopt -s nullglob dotglob
  for item in "$destination"/*; do
    name="$(basename -- "$item")"
    if is_managed_symlink "$ownership" "$item" && [[ -z "${desired[$name]+present}" ]]; then
      doctor_error "Stale managed link: $item"
    fi
  done
  shopt -u nullglob dotglob
}

cmd_doctor() {
  local legacy_count=0
  local machine="${MACHINE:-}"
  local clients="${CLIENTS:-}"
  [[ -n "$machine" ]] || machine="$(hostname -s 2>/dev/null || hostname)"
  DOCTOR_ERRORS=0
  collect_desired_units "$machine" "$clients"

  log "Shared repo:   $SHARED_REPO"
  log "Private repo:  $PRIVATE_REPO"
  log "Shared skills: $SHARED_SKILLS_DIR"
  log "Shared agents: $SHARED_AGENTS_DIR"
  log "Layer order:   $LAYERS_ORDER"
  log ""

  if ! report_target_dir "Canonical skills" "$SKILLS_DIR" repo; then
    doctor_error "Canonical skills root is missing or unsafe: $SKILLS_DIR"
  else
    verify_desired_links "$SKILLS_DIR" repo DESIRED_SKILLS repo
  fi
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    if ! report_target_dir "Claude aliases" "$CLAUDE_SKILLS_DIR" claude; then
      doctor_error "Claude skills root is missing or unsafe: $CLAUDE_SKILLS_DIR"
    else
      verify_desired_links "$CLAUDE_SKILLS_DIR" claude DESIRED_SKILLS claude
    fi
  fi
  if ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$SKILLS_DIR" \
    && ! same_path "$LEGACY_CODEX_SKILLS_DIR" "$CLAUDE_SKILLS_DIR"; then
    report_target_dir "Legacy Codex skills" "$LEGACY_CODEX_SKILLS_DIR" repo || true
    legacy_count="$(managed_count "$LEGACY_CODEX_SKILLS_DIR" repo)"
    if [[ "$legacy_count" -gt 0 ]]; then
      doctor_error "$legacy_count legacy managed Codex link(s) remain; run apply to migrate them."
    fi
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    if ! report_target_dir "Claude agents" "$AGENTS_DIR" repo; then
      doctor_error "Claude agents root is missing or unsafe: $AGENTS_DIR"
    else
      verify_desired_links "$AGENTS_DIR" repo DESIRED_AGENTS repo
    fi
  fi
  if pi_uses_claude_skills; then
    doctor_error "Pi settings still load $CLAUDE_SKILLS_DIR; remove that entry to avoid duplicate skills."
  fi
  if [[ "$DOCTOR_ERRORS" -gt 0 ]]; then
    log "Doctor: FAIL ($DOCTOR_ERRORS error(s))"
    return 1
  fi
  log "Doctor: PASS"
}

cmd_clean() {
  local dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) err "Unknown arg: $1" ;;
    esac
  done

  preflight_roots
  clean_installation "$dry_run"
  log "User content was preserved."
}

cmd_apply() {
  local profile=""
  local machine=""
  local clients=""
  local dry_run=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile) profile="${2:-}"; shift 2 ;;
      --machine) machine="${2:-}"; shift 2 ;;
      --clients) clients="${2:-}"; shift 2 ;;
      --dry-run) dry_run=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) err "Unknown arg: $1" ;;
    esac
  done

  [[ -n "$profile" ]] && load_profile "$profile"
  machine="${machine:-${MACHINE:-}}"
  clients="${clients:-${CLIENTS:-}}"
  [[ -n "$machine" ]] || machine="$(hostname -s 2>/dev/null || hostname)"

  collect_desired_units "$machine" "$clients"
  preflight_apply

  ensure_target_dir "$SKILLS_DIR" "$dry_run"
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    ensure_target_dir "$CLAUDE_SKILLS_DIR" "$dry_run"
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    ensure_target_dir "$AGENTS_DIR" "$dry_run"
  fi

  log "Installing managed links..."
  install_desired_units "$dry_run"

  log ""
  log "Done."
  log "Machine: $machine"
  log "Clients: ${clients:-<none>}"
  log "Skills:  $SKILLS_DIR"
  if ! same_path "$CLAUDE_SKILLS_DIR" "$SKILLS_DIR"; then
    log "Claude:  $CLAUDE_SKILLS_DIR (per-skill aliases)"
  fi
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    log "Agents:  $AGENTS_DIR"
  fi
  warn_pi_legacy_setting
}

main() {
  local command="${1:-}"
  shift || true
  case "$command" in
    apply) cmd_apply "$@" ;;
    clean) cmd_clean "$@" ;;
    doctor) cmd_doctor ;;
    list) cmd_list ;;
    ""|-h|--help) usage ;;
    *) err "Unknown command: $command" ;;
  esac
}

main "$@"
