#!/usr/bin/env bash
set -euo pipefail

# ---- Config (override via env) ----
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SHARED_REPO="${SHARED_REPO:-$SCRIPT_DIR}"
PRIVATE_REPO="${PRIVATE_REPO:-$SCRIPT_DIR/../agent-skills-private}"

# Resolve to absolute paths for reliable symlink target matching
SHARED_REPO="$(cd "$SHARED_REPO" 2>/dev/null && pwd || echo "$SHARED_REPO")"
[[ -d "$PRIVATE_REPO" ]] && PRIVATE_REPO="$(cd "$PRIVATE_REPO" && pwd)"

SHARED_SKILLS_DIR="${SHARED_SKILLS_DIR:-$SHARED_REPO/skills}"
PRIVATE_SKILLS_DIR="${PRIVATE_SKILLS_DIR:-$PRIVATE_REPO/skills}"
SHARED_AGENTS_DIR="${SHARED_AGENTS_DIR:-$SHARED_REPO/agents}"
PRIVATE_AGENTS_DIR="${PRIVATE_AGENTS_DIR:-$PRIVATE_REPO/agents}"
PRIVATE_MACHINES_DIR="${PRIVATE_MACHINES_DIR:-$PRIVATE_REPO/machines}"
PRIVATE_CLIENTS_DIR="${PRIVATE_CLIENTS_DIR:-$PRIVATE_REPO/clients}"
PROFILES_DIR="${PROFILES_DIR:-$PRIVATE_REPO/profiles}"

SKILLS_DIR="${SKILLS_DIR:-$HOME/.claude/skills}"
AGENTS_DIR="${AGENTS_DIR:-$HOME/.claude/agents}"

# Set SKIP_AGENTS=1 for targets that don't support agents (e.g. Codex).
SKIP_AGENTS="${SKIP_AGENTS:-0}"

# shared private machine clients (later overrides earlier)
LAYERS_ORDER="${LAYERS_ORDER:-shared private machine clients}"

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
- Links "skill units" (directories with SKILL.md) into SKILLS_DIR
  Example: skills/create-pr/ -> $SKILLS_DIR/create-pr (symlink)
- Links "agent units" (*.md files) into AGENTS_DIR
  Example: agents/tracking-auditor.md -> $AGENTS_DIR/tracking-auditor.md (symlink)
- Symlinks coexist with user's own skills/agents.
- Pre-existing items not managed by us are never overwritten — apply will error.
- Clean only removes symlinks pointing to our repos.
- Set SKIP_AGENTS=1 for targets without agent support (e.g. Codex).

Env:
  SHARED_REPO, PRIVATE_REPO, SKILLS_DIR, AGENTS_DIR, SKIP_AGENTS, LAYERS_ORDER
EOF
}

# Basic KEY=VALUE loader (supports quoted values), ignores comments/blank lines.
load_profile() {
  local profile="$1"
  local f="$PROFILES_DIR/$profile.env"
  [[ -f "$f" ]] || err "Profile not found: $f"
  set -a
  # shellcheck disable=SC1090
  source "$f"
  set +a
}

# Check if a symlink target is managed by us (points into SHARED_REPO or PRIVATE_REPO)
is_managed_symlink() {
  local link="$1"
  [[ -L "$link" ]] || return 1
  local target
  target="$(readlink -f "$link" 2>/dev/null || true)"
  [[ -z "$target" ]] && return 1
  [[ "$target" == "$SHARED_REPO"/* || "$target" == "$PRIVATE_REPO"/* ]]
}

# Remove managed symlinks (pointing to our repos) from a target directory.
clean_managed_symlinks_in() {
  local target_dir="$1"
  local dry_run="${2:-0}"
  local removed=0

  [[ -d "$target_dir" ]] || { echo 0; return 0; }

  shopt -s nullglob dotglob
  local item
  for item in "$target_dir"/*; do
    if is_managed_symlink "$item"; then
      if [[ "$dry_run" -eq 1 ]]; then
        log "DRY: rm '$item' -> $(readlink "$item")"
      else
        rm -f "$item"
      fi
      ((removed++)) || true
    fi
  done
  shopt -u nullglob dotglob

  echo "$removed"
}

cmd_clean() {
  local dry_run=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift;;
      -h|--help) usage; exit 0;;
      *) err "Unknown arg: $1";;
    esac
  done

  local removed_skills removed_agents
  removed_skills="$(clean_managed_symlinks_in "$SKILLS_DIR" "$dry_run")"
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    removed_agents="$(clean_managed_symlinks_in "$AGENTS_DIR" "$dry_run")"
  else
    removed_agents=0
  fi

  if [[ "$dry_run" -eq 0 ]]; then
    log "Cleaned $removed_skills managed skill symlink(s) from $SKILLS_DIR"
    if [[ "$SKIP_AGENTS" -eq 0 ]]; then
      log "Cleaned $removed_agents managed agent symlink(s) from $AGENTS_DIR"
    fi
    log "User content (non-symlinks or symlinks to other locations) was preserved."
  fi
}

# Ensure a target dir exists as a real directory (convert stale symlinks).
ensure_target_dir() {
  local target_dir="$1"
  local dry_run="$2"

  if [[ -L "$target_dir" ]]; then
    log "NOTE: $target_dir is a symlink (old setup). Converting to directory."
    if [[ "$dry_run" -eq 0 ]]; then
      rm -f "$target_dir"
      mkdir -p "$target_dir"
    else
      log "DRY: rm -f '$target_dir' && mkdir -p '$target_dir'"
    fi
  elif [[ -d "$target_dir" ]]; then
    :
  else
    if [[ "$dry_run" -eq 0 ]]; then
      mkdir -p "$target_dir"
    else
      log "DRY: mkdir -p '$target_dir'"
    fi
  fi
}

# Link each immediate child under src_skills_dir into SKILLS_DIR.
# Only directories containing SKILL.md are considered valid skills.
# - If skill already exists and is managed by us: update the symlink (layer override)
# - If skill already exists and is NOT managed by us: error (pre-existing wins)
link_skill_units() {
  local src_skills_dir="$1"  # .../skills
  local label="$2"           # shared | machine:xxx | client:yyy
  local dry_run="$3"

  [[ -d "$src_skills_dir" ]] || return 0

  shopt -s nullglob dotglob
  local child
  for child in "$src_skills_dir"/*; do
    [[ -d "$child" && -f "$child/SKILL.md" ]] || continue

    local name
    name="$(basename "$child")"
    local dst="$SKILLS_DIR/$name"

    if [[ -e "$dst" || -L "$dst" ]]; then
      if is_managed_symlink "$dst"; then
        log "  Override: $name (layer '$label' replaces earlier layer)"
        [[ "$dry_run" -eq 1 ]] || rm -f "$dst"
      else
        err "Collision: skill '$name' already exists and is not managed by us.
  Existing: $dst
  Attempted: $child (from $label)
Pre-existing skill wins. Remove it manually if you want to use the managed version."
      fi
    fi

    if [[ "$dry_run" -eq 1 ]]; then
      log "  DRY: ln -s '$child' -> '$dst'"
    else
      ln -s "$child" "$dst"
    fi
  done
  shopt -u nullglob dotglob
}

# Link each *.md file under src_agents_dir into AGENTS_DIR.
# README.md is skipped. Collision behavior mirrors link_skill_units.
link_agent_units() {
  local src_agents_dir="$1"  # .../agents
  local label="$2"
  local dry_run="$3"

  [[ -d "$src_agents_dir" ]] || return 0

  shopt -s nullglob dotglob
  local child
  for child in "$src_agents_dir"/*.md; do
    [[ -f "$child" ]] || continue

    local name
    name="$(basename "$child")"
    [[ "$name" == "README.md" ]] && continue

    local dst="$AGENTS_DIR/$name"

    if [[ -e "$dst" || -L "$dst" ]]; then
      if is_managed_symlink "$dst"; then
        log "  Override: $name (layer '$label' replaces earlier layer)"
        [[ "$dry_run" -eq 1 ]] || rm -f "$dst"
      else
        err "Collision: agent '$name' already exists and is not managed by us.
  Existing: $dst
  Attempted: $child (from $label)
Pre-existing agent wins. Remove it manually if you want to use the managed version."
      fi
    fi

    if [[ "$dry_run" -eq 1 ]]; then
      log "  DRY: ln -s '$child' -> '$dst'"
    else
      ln -s "$child" "$dst"
    fi
  done
  shopt -u nullglob dotglob
}

cmd_list() {
  log "Machines (private):"
  [[ -d "$PRIVATE_MACHINES_DIR" ]] && find "$PRIVATE_MACHINES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '  %f\n' | sort || true
  log ""
  log "Clients (private):"
  [[ -d "$PRIVATE_CLIENTS_DIR" ]] && find "$PRIVATE_CLIENTS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '  %f\n' | sort || true
  log ""
  log "Profiles (private):"
  [[ -d "$PROFILES_DIR" ]] && find "$PROFILES_DIR" -mindepth 1 -maxdepth 1 -type f -name '*.env' -printf '  %f\n' | sed 's/\.env$//' | sort || true
}

cmd_doctor() {
  log "Shared repo:   $SHARED_REPO"
  log "Private repo:  $PRIVATE_REPO"
  log "Shared skills: $SHARED_SKILLS_DIR"
  log "Shared agents: $SHARED_AGENTS_DIR"
  log "Skills dir:    $SKILLS_DIR"
  log "Agents dir:    $AGENTS_DIR (skip=$SKIP_AGENTS)"
  log "Layer order:   $LAYERS_ORDER"
  log ""

  [[ -d "$SHARED_SKILLS_DIR" ]] || log "WARN: shared skills dir missing: $SHARED_SKILLS_DIR"
  [[ "$SKIP_AGENTS" -eq 0 && ! -d "$SHARED_AGENTS_DIR" ]] && log "NOTE: shared agents dir missing: $SHARED_AGENTS_DIR"

  report_target_dir() {
    local label="$1"
    local dir="$2"
    if [[ -L "$dir" ]]; then
      log "$label: symlink (old setup): $(readlink "$dir")"
      log "      Run 'apply' to convert to new direct-symlink setup."
    elif [[ -d "$dir" ]]; then
      local managed=0 unmanaged=0
      shopt -s nullglob dotglob
      for item in "$dir"/*; do
        if is_managed_symlink "$item"; then
          ((managed++)) || true
        else
          ((unmanaged++)) || true
        fi
      done
      shopt -u nullglob dotglob
      log "$label: exists (good)"
      log "  Managed:   $managed"
      log "  Unmanaged: $unmanaged"
    else
      log "$label: not present yet."
    fi
  }

  report_target_dir "Skills dir" "$SKILLS_DIR"
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    report_target_dir "Agents dir" "$AGENTS_DIR"
  fi
}

apply_layer_skills() {
  local src="$1"
  local label="$2"
  local dry_run="$3"
  if [[ -d "$src" ]]; then
    log "Applying skills: $label ($src)"
    link_skill_units "$src" "$label" "$dry_run"
  fi
}

apply_layer_agents() {
  local src="$1"
  local label="$2"
  local dry_run="$3"
  [[ "$SKIP_AGENTS" -eq 1 ]] && return 0
  if [[ -d "$src" ]]; then
    log "Applying agents: $label ($src)"
    link_agent_units "$src" "$label" "$dry_run"
  fi
}

cmd_apply() {
  local profile=""
  local machine=""
  local clients=""
  local dry_run=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile) profile="${2:-}"; shift 2;;
      --machine) machine="${2:-}"; shift 2;;
      --clients) clients="${2:-}"; shift 2;;
      --dry-run) dry_run=1; shift;;
      -h|--help) usage; exit 0;;
      *) err "Unknown arg: $1";;
    esac
  done

  if [[ -n "$profile" ]]; then
    load_profile "$profile"
  fi

  machine="${machine:-${MACHINE:-}}"
  clients="${clients:-${CLIENTS:-}}"

  if [[ -z "$machine" ]]; then
    machine="$(hostname -s 2>/dev/null || hostname)"
  fi

  # First, clean any existing managed symlinks (from previous apply)
  # This ensures layer ordering is correct on re-apply
  log "Cleaning existing managed symlinks..."
  clean_managed_symlinks_in "$SKILLS_DIR" "$dry_run" > /dev/null
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    clean_managed_symlinks_in "$AGENTS_DIR" "$dry_run" > /dev/null
  fi

  ensure_target_dir "$SKILLS_DIR" "$dry_run"
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    ensure_target_dir "$AGENTS_DIR" "$dry_run"
  fi

  local layer
  for layer in $LAYERS_ORDER; do
    case "$layer" in
      shared)
        apply_layer_skills "$SHARED_SKILLS_DIR" "shared" "$dry_run"
        apply_layer_agents "$SHARED_AGENTS_DIR" "shared" "$dry_run"
        ;;
      private)
        apply_layer_skills "$PRIVATE_SKILLS_DIR" "private" "$dry_run"
        apply_layer_agents "$PRIVATE_AGENTS_DIR" "private" "$dry_run"
        ;;
      machine)
        apply_layer_skills "$PRIVATE_MACHINES_DIR/$machine/skills" "machine:$machine" "$dry_run"
        apply_layer_agents "$PRIVATE_MACHINES_DIR/$machine/agents" "machine:$machine" "$dry_run"
        ;;
      clients)
        if [[ -n "$clients" ]]; then
          local c
          for c in $clients; do
            apply_layer_skills "$PRIVATE_CLIENTS_DIR/$c/skills" "client:$c" "$dry_run"
            apply_layer_agents "$PRIVATE_CLIENTS_DIR/$c/agents" "client:$c" "$dry_run"
          done
        else
          log "No clients specified."
        fi
        ;;
      *) err "Unknown layer in LAYERS_ORDER: '$layer'";;
    esac
  done

  log ""
  log "Done."
  log "Machine: $machine"
  log "Clients: ${clients:-<none>}"
  log "Skills:  $SKILLS_DIR"
  if [[ "$SKIP_AGENTS" -eq 0 ]]; then
    log "Agents:  $AGENTS_DIR"
  fi
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    apply)  cmd_apply "$@";;
    clean)  cmd_clean "$@";;
    doctor) cmd_doctor;;
    list)   cmd_list;;
    ""|-h|--help) usage;;
    *) err "Unknown command: $cmd";;
  esac
}

main "$@"
