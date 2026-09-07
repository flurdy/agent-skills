---
name: setup-multirepo-git
description: Multi-repo git workflow rules and setup. Provides mgit wrapper for safe permission patterns across independent service repositories. Use when setting up a new multi-repo workspace or when working with multi-repo git operations.
allowed-tools: "Read,Write,Bash(git:*),Bash(ln:*),Bash(mkdir:*),Bash(cat:*),Bash(./scripts/mgit:*),Bash(readlink:*),AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Multi-Repo Git Workflow

This skill provides rules for working with multi-repo workspaces (multiple independent git repositories in one project directory) and a setup command for new projects.

## Multi-Repo Git Rules

These rules apply whenever working in a project that has a `.mgit.conf` file in its root.

### Always use mgit for service git operations

**Rule: Use `./scripts/mgit <subcommand> <service>` for all git operations on service repositories.** This wrapper runs `git -C` under the hood but puts the subcommand before the service, giving harness-specific permission policies a stable command prefix. The wrapper itself does not enforce approvals.

Use `root` or `.` as the service name for the root repo.

Never use `cd <service> && git ...` (bypasses the documented wrapper prefix). Never run bare `git add/status/commit` expecting it to pick up service files — that targets the root repo.

```bash
# CORRECT — invoke from the project root using the configured wrapper prefix
./scripts/mgit status my-service --short
./scripts/mgit diff my-service
./scripts/mgit add my-service src/main/MyFile.scala
./scripts/mgit commit my-service -m "fix: something"
./scripts/mgit log my-service --oneline -5

# CORRECT — root repo operations
./scripts/mgit status root --short
./scripts/mgit diff .
./scripts/mgit add root AGENTS.md
./scripts/mgit commit . -m "docs: update agents"

# WRONG for this workflow — bypasses the configured mgit prefix
git -C my-service status --short

# WRONG for this workflow — changes directory and bypasses mgit
cd my-service && git status --short

# WRONG — targets root repo, service folders are gitignored
git add my-service/src/main/MyFile.scala
git status  # only shows root repo changes
```

### Which repo does a file belong to?

Check the first path component after the project root:
- If it matches a service name listed in `.mgit.conf` → use `./scripts/mgit <subcommand> <service>`
- If it's a root-level file (AGENTS.md, docs/, scripts/, etc.) → use `./scripts/mgit <subcommand> root` (or `.`)

### Multiple services in one session

When committing changes across multiple services, run separate mgit commands for each service. Each service gets its own commit.

### Git best practices

- **Staging**: Never use `git add -A`. Add specific files instead.
- **Commits**: Keep commits small and focused. Use Conventional Commits style.
- **Remote**: Never `git push` or `git pull` automatically — ask first. `git fetch` is allowed.
- **Resets**: Do not `git reset --hard` or checkout the whole project.

## Setup Instructions

When invoked as `/setup-multirepo-git`, set up a new multi-repo workspace:

### Step 1: Discover services

Scan the project root for subdirectories that contain their own `.git/` directory:

```bash
# Find subdirectories with their own git repos
for dir in */; do
  [ -d "$dir/.git" ] && echo "${dir%/}"
done
```

Present the discovered list to the user for confirmation. They may want to add or remove entries.

### Step 2: Create .mgit.conf

Create a `.mgit.conf` file in the project root with the confirmed service list:

```ini
# Multi-repo workspace configuration
# Presence of this file marks the project root for mgit
services=service-a,service-b,service-c
```

### Step 3: Symlink the mgit script

Resolve installed resources once in Bash before linking or reading templates. A nonempty
`SKILLS_DIR` is authoritative: use an absolute path and never silently replace an invalid override.
Without it, prefer the canonical root; fall back to the Claude alias root only if this skill unit
is absent. Legacy Codex-only installations can set `SKILLS_DIR` explicitly; they are not auto-selected.

```bash
set -eu
if [[ -z "${SKILLS_DIR:-}" ]]; then
  SKILLS_DIR="$HOME/.agents/skills"
  if [[ ! -d "$SKILLS_DIR/setup-multirepo-git" ]]; then
    SKILLS_DIR="${CLAUDE_SKILLS_DIR:-${CLAUDE_HOME:-$HOME/.claude}/skills}"
  fi
fi
[[ "$SKILLS_DIR" = /* ]] || { echo "SKILLS_DIR must be absolute" >&2; exit 1; }
for resource in SKILL.md scripts/mgit templates/permissions.json templates/AGENTS-MGIT.md; do
  [[ -f "$SKILLS_DIR/setup-multirepo-git/$resource" && -r "$SKILLS_DIR/setup-multirepo-git/$resource" ]] || {
    echo "Missing setup-multirepo-git resource: $resource" >&2; exit 1;
  }
done
[[ -x "$SKILLS_DIR/setup-multirepo-git/scripts/mgit" ]] || { echo "mgit is not executable" >&2; exit 1; }
```

Missing resources stop setup; do not create dangling links or repair the shared installation here.
After installation-root changes, re-run the approved project setup rather than retargeting silently.
Keep the resolved root for steps 4–5 (shell calls may not share variables). Preview the exact paths;
create links only after setup approval and never overwrite an existing destination implicitly:

```bash
[[ ! -e scripts/mgit && ! -L scripts/mgit ]] || { echo "Destination exists: scripts/mgit" >&2; exit 1; }
mkdir -p scripts
ln -s "$SKILLS_DIR/setup-multirepo-git/scripts/mgit" scripts/mgit
```

Verify the symlink works:
```bash
./scripts/mgit status <first-service> --short
./scripts/mgit status root --short
```

### Step 4: Output permission patterns

Read `$SKILLS_DIR/setup-multirepo-git/templates/permissions.json` using the root validated in step 3.
The existing filename is retained for compatibility, but these are **Claude Code** `Bash(...)`
patterns, not portable permission configuration. Show the fragment for the user to review and merge
under `permissions` in their Claude settings; do not edit settings automatically.

The `allow` list includes `add`, `commit`, `stash`, and `fetch`: it is **not read-only**. Review those
choices against repository rules before adopting them. Codex uses its own sandbox/approval controls;
Pi core does not enforce this JSON or skill `allowed-tools`. Installed Pi policy extensions may add
controls; inspect their actual configuration rather than translating Claude syntax or assuming
approvals are enforced. Frontmatter and a wrapper prefix never replace user/repository authorization.

### Step 5: Output AGENTS.md block

Read `$SKILLS_DIR/setup-multirepo-git/templates/AGENTS-MGIT.md` using the root validated in step 3
and output it. If this is a new shell/tool context, reuse the verified absolute path or repeat the
read-only resource resolution; never fall back to a different root for templates.

Tell the user to include this block in their project's `AGENTS.md` file, customizing the service names and any project-specific details.

### Step 6: Confirm setup

Verify everything works:
1. `readlink scripts/mgit` — should show the symlink target
2. `./scripts/mgit status <service>` — should show git status for a service
3. `./scripts/mgit status root` — should show git status for the root repo
4. `./scripts/mgit status invalid-name` — should error with valid service list
