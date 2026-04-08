---
name: trello-beads
description: "Integrate Trello boards with Beads — pull triage cards into beads, sync closed beads back to Trello. Use for project management bridging between Trello and Beads."
allowed-tools: "Read,Write,Bash(bd:*),Bash(./scripts/trello-api:*),Bash(./scripts/trello-pull:*),Bash(./scripts/trello-sync:*),Bash(ln:*),Bash(mkdir:*),Bash(direnv:*),AskUserQuestion"
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
ln -sf ~/.claude/skills/trello-beads/resources/trello-api.sh scripts/trello-api
ln -sf ~/.claude/skills/trello-beads/resources/trello-pull.sh scripts/trello-pull
ln -sf ~/.claude/skills/trello-beads/resources/trello-sync.sh scripts/trello-sync
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
/trello-beads pull                     # Pull all triage cards into beads
/trello-beads pull <card-id>           # Pull a specific card into a bead
/trello-beads cards <list-name>        # List cards in any column
/trello-beads sync                     # Update Trello cards from closed beads
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

Use the pull script directly:

```bash
# Pull all triage cards into beads
./scripts/trello-pull pull

# Pull a specific card
./scripts/trello-pull pull <card-id>

# Pull all and move processed cards to Backlog
./scripts/trello-pull pull-all Backlog
```

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

Use the sync script:

```bash
./scripts/trello-sync sync              # Move cards for closed beads to Done
./scripts/trello-sync sync --dry-run    # Preview what would be moved
```

The script:
1. Batch-fetches all card IDs in Done (including archived) in a single API call
2. Finds closed beads with `bd list --status=closed --label=trello`
3. For each bead with a `trello-<card-id>` external ref:
   - **Already in Done** (active or archived): skipped silently (no API call)
   - **Archived in another list**: skipped with a warning (won't unarchive)
   - **Active in another list**: moved to Done (or previewed with `--dry-run`)

This avoids per-card API calls for cards already in Done and prevents accidentally unarchiving cards that were archived in other columns.

## Notes

- Always confirm before moving/modifying Trello cards
- Scripts require `curl` and `jq`
- Rate limits: 300 requests per 10 seconds per API key
