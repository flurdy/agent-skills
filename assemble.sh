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
PRIVATE_MACHINES_DIR="${PRIVATE_MACHINES_DIR:-$PRIVATE_REPO/machines}"
PRIVATE_CLIENTS_DIR="${PRIVATE_CLIENTS_DIR:-$PRIVATE_REPO/clients}"
PROFILES_DIR="${PROFILES_DIR:-$PRIVATE_REPO/profiles}"

SKILLS_DIR="${SKILLS_DIR:-$HOME/.claude/skills}"

# shared machine clients (later overrides earlier)
LAYERS_ORDER="${LAYERS_ORDER:-shared machine clients}"

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
- This assembler links "skill units" directly into ~/.claude/skills/
  Example: skills/create-pr/ -> ~/.claude/skills/create-pr (symlink)
- Symlinks are created directly in SKILLS_DIR, coexisting with user's own skills.
- Pre-existing skills (not managed by us) are never overwritten - apply will error.
- Clean only removes symlinks pointing to our repos, preserving user skills.

Env:
  SHARED_REPO, PRIVATE_REPO, SKILLS_DIR, LAYERS_ORDER
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

# Remove only symlinks managed by us (pointing to our repos)
clean_managed_symlinks() {
  local dry_run="${1:-0}"
  local removed=0

  [[ -d "$SKILLS_DIR" ]] || return 0

  shopt -s nullglob dotglob
  local item
  for item in "$SKILLS_DIR"/*; do
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

  local removed
  removed="$(clean_managed_symlinks "$dry_run")"

  if [[ "$dry_run" -eq 0 ]]; then
    log "Cleaned $removed managed skill symlink(s) from $SKILLS_DIR"
    log "User skills (non-symlinks or symlinks to other locations) were preserved."
  fi
}

ensure_skills_dir() {
  local dry_run="$1"

  if [[ -L "$SKILLS_DIR" ]]; then
    # SKILLS_DIR is a symlink - this is the old setup, convert it
    log "NOTE: $SKILLS_DIR is a symlink (old setup). Converting to directory."
    if [[ "$dry_run" -eq 0 ]]; then
      rm -f "$SKILLS_DIR"
      mkdir -p "$SKILLS_DIR"
    else
      log "DRY: rm -f '$SKILLS_DIR' && mkdir -p '$SKILLS_DIR'"
    fi
  elif [[ -d "$SKILLS_DIR" ]]; then
    : # Already a directory, good
  else
    if [[ "$dry_run" -eq 0 ]]; then
      mkdir -p "$SKILLS_DIR"
    else
      log "DRY: mkdir -p '$SKILLS_DIR'"
    fi
  fi
}

# Link each immediate child under src_skills_dir into SKILLS_DIR
# Children can be directories (preferred) or files.
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
    local name
    name="$(basename "$child")"
    local dst="$SKILLS_DIR/$name"

    if [[ -e "$dst" || -L "$dst" ]]; then
      if is_managed_symlink "$dst"; then
        # It's our symlink from an earlier layer - override it
        log "  Override: $name (layer '$label' replaces earlier layer)"
        [[ "$dry_run" -eq 1 ]] || rm -f "$dst"
      else
        # Pre-existing skill not managed by us - error out, let it win
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
  log "Skills dir:    $SKILLS_DIR"
  log "Layer order:   $LAYERS_ORDER"
  log ""

  [[ -d "$SHARED_SKILLS_DIR" ]] || log "WARN: shared skills dir missing: $SHARED_SKILLS_DIR"

  if [[ -L "$SKILLS_DIR" ]]; then
    log "WARN: Skills dir is a symlink (old setup): $(readlink "$SKILLS_DIR")"
    log "      Run 'apply' to convert to new direct-symlink setup."
  elif [[ -d "$SKILLS_DIR" ]]; then
    log "Skills dir exists (good)"
    # Count managed vs unmanaged skills
    local managed=0 unmanaged=0
    shopt -s nullglob dotglob
    for item in "$SKILLS_DIR"/*; do
      if is_managed_symlink "$item"; then
        ((managed++)) || true
      else
        ((unmanaged++)) || true
      fi
    done
    shopt -u nullglob dotglob
    log "  Managed skills:   $managed"
    log "  Unmanaged skills: $unmanaged"
  else
    log "Skills dir not present yet."
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
  clean_managed_symlinks "$dry_run" > /dev/null

  # Ensure SKILLS_DIR exists as a directory (not a symlink)
  ensure_skills_dir "$dry_run"

  local layer
  for layer in $LAYERS_ORDER; do
    case "$layer" in
      shared)
        if [[ -d "$SHARED_SKILLS_DIR" ]]; then
          log "Applying: shared ($SHARED_SKILLS_DIR)"
          link_skill_units "$SHARED_SKILLS_DIR" "shared" "$dry_run"
        else
          log "Skipping shared: missing $SHARED_SKILLS_DIR"
        fi
        ;;
      machine)
        local mskills="$PRIVATE_MACHINES_DIR/$machine/skills"
        if [[ -d "$mskills" ]]; then
          log "Applying: machine:$machine ($mskills)"
          link_skill_units "$mskills" "machine:$machine" "$dry_run"
        else
          log "Skipping machine '$machine': missing $mskills"
        fi
        ;;
      clients)
        if [[ -n "$clients" ]]; then
          local c
          for c in $clients; do
            local cskills="$PRIVATE_CLIENTS_DIR/$c/skills"
            if [[ -d "$cskills" ]]; then
              log "Applying: client:$c ($cskills)"
              link_skill_units "$cskills" "client:$c" "$dry_run"
            else
              log "Skipping client '$c': missing $cskills"
            fi
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
