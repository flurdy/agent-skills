---
name: trello-beads
description: "Integrate Trello boards with Beads — pull triage cards into beads, sync closed beads back to Trello. Use for project management bridging between Trello and Beads."
allowed-tools: "Read,Write,Bash(bd:*),Bash(./scripts/trello-api:*),Bash(./scripts/trello-pull:*),Bash(./scripts/trello-sync:*),Bash(ln:*),Bash(mkdir:*),Bash(direnv:*),AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "1.0.0"
author: "flurdy"
---

# Trello-Beads — Board Integration for Beads Workflow

Interact with Trello boards and integrate with Beads project management.

## Prerequisites

- Environment variables set (via direnv `.env.local`):
  - `TRELLO_API_KEY` — from https://trello.com/power-ups/admin
  - `TRELLO_TOKEN` — generated from the same page
  - `TRELLO_BOARD_ID` — your board ID
  - `TRELLO_LIST_TRIAGE` — column name for cards to pull into beads (default: "Triage")
  - `TRELLO_LIST_BUGS` — bug column name (default: "Bugs")
  - `TRELLO_LIST_DONE` — done column name (default: "Done")
- Scripts symlinked into project `scripts/` directory (see Setup below)

## Setup

When invoked as `/trello-beads setup`, or when setting up a new project:

### Step 1: Symlink scripts

```bash
mkdir -p scripts
SKILLS_DIR="${SKILLS_DIR:-${CODEX_HOME:-$HOME/.codex}/skills}"
if [[ ! -d "$SKILLS_DIR" ]]; then
  SKILLS_DIR="${CLAUDE_HOME:-$HOME/.claude}/skills"
fi
ln -sf "$SKILLS_DIR/trello-beads/scripts/trello-api.sh" scripts/trello-api
ln -sf "$SKILLS_DIR/trello-beads/scripts/trello-pull.sh" scripts/trello-pull
ln -sf "$SKILLS_DIR/trello-beads/scripts/trello-sync.sh" scripts/trello-sync
```

Verify:
```bash
./scripts/trello-api help
./scripts/trello-pull help
```

### Step 2: Create .env.local from template

Copy `.env.local.dist` if it exists, or create `.env.local` with:

```
TRELLO_API_KEY=<your-api-key>
TRELLO_TOKEN=<your-token>
TRELLO_BOARD_ID=<your-board-id>
TRELLO_LIST_TRIAGE=Triage
TRELLO_LIST_BUGS=Bugs
TRELLO_LIST_DONE=Done
```

Find your board ID with:
```bash
./scripts/trello-api boards
```

### Step 3: Ensure .env.local is gitignored

Check `.gitignore` contains `.env.local` to avoid committing secrets.

### Step 4: Verify

```bash
direnv allow
./scripts/trello-api lists
./scripts/trello-pull list
```

## Usage

```
/trello-beads                          # Show board overview
/trello-beads setup                    # Set up symlinks and config for a project
/trello-beads triage                   # List cards in the triage column
/trello-beads pull                     # Preview all triage cards → Beads/Trello changes
/trello-beads pull <card-id>           # Preview a specific card
/trello-beads apply [card-id]          # Apply a reviewed pull plan after confirmation
/trello-beads cards <list-name>        # List cards in any column
/trello-beads sync                     # Preview closed-Bead card moves
/trello-beads sync --apply             # Apply a reviewed sync plan after confirmation
```

## Commands

### Board Overview (default)

Show all lists and card counts:

```bash
./scripts/trello-api lists
```

Then for each list with cards, show a summary:

```bash
./scripts/trello-api cards-summary "<list-name>"
```

Present as a formatted board overview to the user.

### Triage — List Cards Ready to Pull

```bash
./scripts/trello-pull list
```

Show the cards with their titles, labels, and Trello URLs.

### Pull — Create Beads from Trello Cards

First generate a complete read-only plan, present it to the user, and obtain explicit confirmation. Only then run the matching apply command:

```bash
# Preview all triage cards
./scripts/trello-pull pull

# Preview a specific card
./scripts/trello-pull pull <card-id>

# After explicit confirmation, apply that same plan
./scripts/trello-pull apply <card-id>

# Preview/apply all cards with a custom destination
./scripts/trello-pull plan-all Backlog
./scripts/trello-pull apply-all Backlog
```

`pull`, `plan`, `pull-all`, and `plan-all` never create Beads or mutate Trello. `apply` and `apply-all` are the only pull commands that do.

The script handles:
- Mapping Trello labels to bead type/priority
- Duplicate detection (won't create if bead with same title + trello label exists)
- Adding `trello-<card-id>` as external-ref and `trello` label to beads
- Optional card movement after pull

**Label-to-bead mapping:**

| Trello Label/Color | Bead Type | Bead Priority |
|---------------------|-----------|---------------|
| bug, red            | bug       | P2            |
| feature, green      | feature   | P2            |
| minor, yellow       | task      | P3            |
| (no label)          | task      | P2            |

Cards from the Bugs column are always type=bug regardless of labels.

### Cards — View Any Column

```bash
./scripts/trello-api cards-summary "<list-name>"
./scripts/trello-api cards "<list-name>"     # Full JSON
```

### Sync — Update Trello from Closed Beads

Generate and present a sync plan, then require explicit confirmation before applying it:

```bash
./scripts/trello-sync sync              # Preview what would move
./scripts/trello-sync sync --dry-run    # Explicit preview alias
./scripts/trello-sync sync --apply      # Apply after confirmation
```

`sync` and `sync --dry-run` never mutate Trello. Unknown options fail without making requests or moves.

The script:
1. Batch-fetches all card IDs in Done (including archived) in a single API call
2. Finds closed beads with `bd list --status=closed --label=trello`
3. For each bead with a `trello-<card-id>` external ref:
   - **Already in Done** (active or archived): skipped silently (no API call)
   - **Archived in another list**: skipped with a warning (won't unarchive)
   - **Active in another list**: included in the plan, then moved to Done only with `--apply`

This avoids per-card API calls for cards already in Done and prevents accidentally unarchiving cards that were archived in other columns.

## Security

The scripts send the API key and token in Trello's documented OAuth `Authorization` header. The shared request helper feeds that header to curl through standard input so credentials do not appear in request URLs, process arguments, or command output.

When the client supports it, the official Trello MCP server (`https://mcp.trello.com/v1`) provides a stronger credential boundary through OAuth 2.0, revocable permissions, and workspace-scoped access. The shell scripts remain the portable integration for deterministic Beads creation and synchronization.

## Notes

- Always present the complete plan and obtain explicit confirmation before any `--apply`, `apply`, or `apply-all` command.
- Direct `trello-api` mutations (`move`, `create`, `add-label`, `comment`) are plan-only by default and require trailing `--apply`.
- Scripts require `curl` and `jq`
- Rate limits: 300 requests per 10 seconds per API key
