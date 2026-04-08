---
name: setup-multirepo-git
description: Multi-repo git workflow rules and setup. Provides mgit wrapper for safe permission patterns across independent service repositories. Use when setting up a new multi-repo workspace or when working with multi-repo git operations.
allowed-tools: "Read,Write,Bash(git:*),Bash(ln:*),Bash(mkdir:*),Bash(cat:*),Bash(./scripts/mgit:*),Bash(readlink:*),AskUserQuestion"
version: "1.0.0"
author: "flurdy"
---

# Multi-Repo Git Workflow

This skill provides rules for working with multi-repo workspaces (multiple independent git repositories in one project directory) and a setup command for new projects.

## Multi-Repo Git Rules

These rules apply whenever working in a project that has a `.mgit.conf` file in its root.

### Always use mgit for service git operations

**Rule: Use `./scripts/mgit <subcommand> <service>` for all git operations on service repositories.** This wrapper runs `git -C` under the hood but puts the subcommand first and service last, enabling permission patterns to distinguish safe vs dangerous operations.

Use `root` or `.` as the service name for the root repo.

Never use `cd <service> && git ...` (breaks auto-approval). Never run bare `git add/status/commit` expecting it to pick up service files — that targets the root repo.

```bash
# CORRECT — works from project root, auto-approvable for safe operations
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

# WRONG — requires manual approval (permission wildcards don't match mid-string)
git -C my-service status --short

# WRONG — changes directory, breaks auto-approval
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

Ensure a `scripts/` directory exists, then create the symlink:

```bash
mkdir -p scripts
ln -sf ~/.claude/skills/setup-multirepo-git/resources/mgit scripts/mgit
```

Verify the symlink works:
```bash
./scripts/mgit status <first-service> --short
./scripts/mgit status root --short
```

### Step 4: Output permission patterns

Read the permission template from the skill resources and output it for the user:

```bash
cat ~/.claude/skills/setup-multirepo-git/resources/permissions.json
```

Tell the user to merge these patterns into their `.claude/settings.local.json` file. The `allow` patterns enable auto-approval for safe read-only operations. The `ask` patterns require confirmation for dangerous operations.

### Step 5: Output AGENTS.md block

Read the AGENTS template from the skill resources and output it:

```bash
cat ~/.claude/skills/setup-multirepo-git/resources/AGENTS-MGIT.md
```

Tell the user to include this block in their project's `AGENTS.md` file, customizing the service names and any project-specific details.

### Step 6: Confirm setup

Verify everything works:
1. `readlink scripts/mgit` — should show the symlink target
2. `./scripts/mgit status <service>` — should show git status for a service
3. `./scripts/mgit status root` — should show git status for the root repo
4. `./scripts/mgit status invalid-name` — should error with valid service list
