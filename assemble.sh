#!/usr/bin/env bash
set -euo pipefail

# ---- Config (override via env) ----
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SHARED_REPO="${SHARED_REPO:-$SCRIPT_DIR}"
PRIVATE_REPO="${PRIVATE_REPO:-$SCRIPT_DIR/../agent-skills-private}"

SHARED_SKILLS_DIR="${SHARED_SKILLS_DIR:-$SHARED_REPO/skills}"
PRIVATE_MACHINES_DIR="${PRIVATE_MACHINES_DIR:-$PRIVATE_REPO/machines}"
PRIVATE_CLIENTS_DIR="${PRIVATE_CLIENTS_DIR:-$PRIVATE_REPO/clients}"
PROFILES_DIR="${PROFILES_DIR:-$PRIVATE_REPO/profiles}"

ACTIVE_DIR="${ACTIVE_DIR:-$HOME/.claude/skills.active}"
SKILLS_DIR="${SKILLS_DIR:-$HOME/.claude/skills}"

# warn | fail | allow
COLLISION_MODE="${COLLISION_MODE:-warn}"

# shared machine clients (later overrides earlier)
LAYERS_ORDER="${LAYERS_ORDER:-shared machine clients}"

log() { printf '%s\n' "$*"; }
err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  assemble.sh apply [--profile NAME] [--machine NAME] [--clients "a b c"] [--dry-run]
  assemble.sh clean
  assemble.sh doctor
  assemble.sh list

Notes:
- This assembler links "skill units": immediate children under each skills/ directory.
  Example: skills/create-pr/ -> ~/.claude/skills.active/create-pr (symlink)

Env:
  SHARED_REPO, PRIVATE_REPO, ACTIVE_DIR, SKILLS_DIR, COLLISION_MODE, LAYERS_ORDER

Collision modes:
  warn  : warn; later layer wins (default)
  fail  : stop if a skill name already exists from earlier layer
  allow : silently override
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

clean_out_dir() {
  if [[ -d "$ACTIVE_DIR" ]]; then
    rm -rf "$ACTIVE_DIR"
  else
    rm -f "$ACTIVE_DIR"
  fi
}

ensure_live_link() {
  local dry_run="$1"
  mkdir -p "$(dirname "$SKILLS_DIR")"

  if [[ -L "$SKILLS_DIR" ]]; then
    local target
    target="$(readlink "$SKILLS_DIR")"
    if [[ "$target" != "$ACTIVE_DIR" ]]; then
      [[ "$dry_run" -eq 1 ]] && log "DRY: ln -snf '$ACTIVE_DIR' '$SKILLS_DIR'" || ln -snf "$ACTIVE_DIR" "$SKILLS_DIR"
    fi
  elif [[ -e "$SKILLS_DIR" ]]; then
    err "SKILLS_DIR exists and is not a symlink: $SKILLS_DIR (move it out of the way first)"
  else
    [[ "$dry_run" -eq 1 ]] && log "DRY: ln -s '$ACTIVE_DIR' '$SKILLS_DIR'" || ln -s "$ACTIVE_DIR" "$SKILLS_DIR"
  fi
}

# Link each immediate child under src_skills_dir into ACTIVE_DIR
# Children can be directories (preferred) or files.
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
    local dst="$ACTIVE_DIR/$name"

    if [[ -e "$dst" || -L "$dst" ]]; then
      case "$COLLISION_MODE" in
        fail) err "Collision on skill '$name' while applying '$label' (already exists)";;
        warn) log "WARN: collision on skill '$name' (layer '$label' overrides existing)";;
        allow) :;;
        *) err "Unknown COLLISION_MODE: $COLLISION_MODE";;
      esac
      [[ "$dry_run" -eq 1 ]] || rm -rf "$dst"
    fi

    if [[ "$dry_run" -eq 1 ]]; then
      log "DRY: ln -s '$child' -> '$dst'"
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
  log "Active dir:    $ACTIVE_DIR"
  log "Skills link:   $SKILLS_DIR"
  log "Collision:     $COLLISION_MODE"
  log "Order:         $LAYERS_ORDER"
  log ""

  [[ -d "$SHARED_SKILLS_DIR" ]] || log "WARN: shared skills dir missing: $SHARED_SKILLS_DIR"

  if [[ -L "$SKILLS_DIR" ]]; then
    log "Skills link -> $(readlink "$SKILLS_DIR")"
  elif [[ -e "$SKILLS_DIR" ]]; then
    log "WARN: Skills link path exists but is not a symlink."
  else
    log "Skills link not present yet."
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

  if [[ "$dry_run" -eq 1 ]]; then
    log "DRY: would rebuild ACTIVE_DIR '$ACTIVE_DIR'"
  else
    clean_out_dir
    mkdir -p "$ACTIVE_DIR"
  fi

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

  ensure_live_link "$dry_run"

  log ""
  log "Done."
  log "Machine: $machine"
  log "Clients: ${clients:-<none>}"
  log "Assembled: $ACTIVE_DIR"
  log "Live: $SKILLS_DIR -> $ACTIVE_DIR"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    apply)  cmd_apply "$@";;
    clean)  clean_out_dir; log "Cleaned: $ACTIVE_DIR";;
    doctor) cmd_doctor;;
    list)   cmd_list;;
    ""|-h|--help) usage;;
    *) err "Unknown command: $cmd";;
  esac
}

main "$@"
