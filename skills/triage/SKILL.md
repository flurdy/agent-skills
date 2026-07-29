---
name: triage
description: "Create bead(s) from a raw user prompt or Jira ticket, or refine an existing bead in place when given its ID. Investigates relevance, checks for duplicates, may split complex requests, and delegates approved structured plans to plan-to-backlog."
allowed-tools: "Read,Bash(bd:*),Bash(~/.agents/skills/next/scripts/next-select:*),Grep,Glob,Task,AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "1.3.0"
author: "flurdy"
---

# Triage - Smart Bead Creation from Prompts

Analyze user requests and create appropriate beads with intelligent investigation.

## When to Use

- User describes a feature, bug, or task to track
- User provides a Jira ticket to convert into bead(s)
- Raw idea needs analysis before becoming actionable work
- Need to check if work is already tracked or duplicated
- Complex request might need to be split into multiple beads
- An **existing** bead needs real investigation before it is worth working on — to deepen or
  correct its description, fix its priority, or split off the further beads that investigation
  reveals (see *Refine mode*)

## Relationship to approved plans

This skill owns raw prompt and Jira intake. When input clearly cites an approved
architecture or implementation plan and asks for durable materialization, stop with a
paste-ready `/plan-to-backlog <plan-source>` handoff. Do not invoke the separate
materialization workflow from inside triage.
Do not classify plan children or create beads first. `/plan-to-backlog` owns source
citation, no-item versus single-item versus epic disposition, proposal preview,
confirmation, apply, and recovery.

If the plan is not approved or the user is asking to improve it, route to `/architect`
instead of creating tracking from an unstable plan.

## Usage

```
/triage <description of feature, bug, or task>
/triage ABC-123                          # Create bead(s) from a Jira ticket
/triage ABC-123 break into subtasks      # Jira ticket with additional instructions
/triage skills-1fw                       # Refine an existing bead (see Refine mode)
/triage skills-1fw split it              # Refine with additional instructions
/triage shared:skills-1fw                # Repo-qualified, when the ID exists in several stores
```

## What This Skill Does

1. **Investigate Relevance**
   - Search codebase to understand if request is feasible
   - Check if the feature/fix location is obvious
   - Identify any related existing code

2. **Check for Duplicates**
   - Run `bd list --status=open` to see existing work
   - Search bead titles and descriptions for similar items
   - Flag potential duplicates or related beads

3. **Analyze Complexity**
   - Determine if single bead or multiple beads needed
   - Identify natural task boundaries
   - Consider dependencies between potential beads

4. **Create Beads**
   - Create focused, actionable beads
   - Set appropriate type (task/bug/feature)
   - Set reasonable priority (P2 default, adjust based on context)
   - Add dependencies if creating multiple related beads

5. **Report Summary**
   - List newly created beads
   - Show current open beads count
   - Highlight any duplicates or related work found

## Examples

```bash
# Simple feature request
/triage Add dark mode toggle to settings page

# Bug report
/triage Users seeing 500 error when saving profile with emoji in name

# Complex request (may split)
/triage Implement user authentication with OAuth, session management, and password reset

# From a Jira ticket
/triage SP-123

# Jira ticket broken into subtasks
/triage SP-123 break into subtasks

# Refine an existing bead: investigate, then deepen, correct, or split it
/triage skills-1fw

# Refine with a steer
/triage skills-1fw is this actually two jobs?
```

## Output Format

After triage, provide:

1. **Investigation Summary**: What was checked, relevance assessment
2. **Duplicate Check**: Any similar existing beads found
3. **Created Beads**: List of new beads with IDs
4. **Open Beads Summary**: Quick stats on current workload

## Implementation

When invoked:

1. Parse the input to determine the source:
   - **Approved structured plan**: A cited architecture/implementation plan plus a request
     to create or reconcile durable tracking. Return a paste-ready
     `/plan-to-backlog <plan-source>` handoff and stop; do not run triage's duplicate,
     split, or create procedure first.
   - **Jira ticket**: Input matches pattern `[A-Z]{2,4}-\d+` (e.g., `SP-123`, `ABC-45`)
   - **Existing bead**: The first token looks like a bead ID — `^[a-z][a-z0-9]*(-[a-z0-9]+)+$`
     (e.g. `skills-1fw`, `ai-tools-fiz`) or a repo-qualified `<repo>:<id>` — **and** resolves
     (**R1** below). Anything after the ID is extra instructions. Go to *Refine mode*.
   - **Free text**: Everything else — a description of a feature, bug, or task

   The bead-ID shape is deliberately narrower than free text: it must be a single lowercase
   hyphenated token, so an ordinary sentence never triggers resolution. Jira keys are uppercase
   and so cannot collide. Shape only *gates* the check — resolution decides.

2. **If Jira ticket detected**, look up the ticket:
   ```
   mcp__jira__jira_get with:
     path: /rest/api/3/issue/{ticketNumber}
     jq: "{key: key, summary: fields.summary, type: fields.issuetype.name, description: fields.description}"
   ```

   Map the Jira issue type to bead type:

   | Jira Issue Type | Bead Type |
   |-----------------|-----------|
   | Story           | feature   |
   | Task            | task      |
   | Bug             | bug       |
   | Sub-task        | task      |
   | Improvement     | feature   |
   | Spike           | task      |
   | Technical Debt  | task      |
   | Default         | task      |

   Use the ticket summary and description to populate the bead title and description. Any additional text after the ticket ID in the prompt is treated as extra instructions (e.g., "break into subtasks").

3. Quick codebase investigation:
   ```bash
   # Search for related code/files
   # Check if area of code exists
   ```

4. Check for duplicates:
   ```bash
   bd list --status=open
   bd search "<keywords from description>"
   ```

5. Decide on bead structure:
   - Single focused task → one bead
   - Multi-part work → multiple beads with dependencies
   - Vague request → ask clarifying questions first

6. Create bead(s):
   ```bash
   # For Jira-sourced beads, include --external-ref and --labels
   bd create --title="..." --type=feature|bug|task --priority=2 \
     --description="..." \
     --external-ref "jira-SP-123" \
     --labels "jira"

   # For free-text beads (no Jira reference)
   bd create --title="..." --type=feature|bug|task --priority=2 --description="..."
   ```

7. If multiple beads, set dependencies:
   ```bash
   bd dep add <dependent> <dependency>
   ```

   When creating multiple beads from a single Jira ticket, all beads get the same `--external-ref` and `jira` label so they can be traced back to the source ticket.

8. Report results with summary of open beads

## Refine mode (existing bead)

Same investigation, dedup, and splitting procedure as intake — pointed at a bead that already
exists instead of a prompt. Use it when a bead is too thin, possibly wrong, or bigger than it
looks, and you want to find out *before* starting the work.

This is the depth counterpart to `/backlog-groom`, which sweeps the whole backlog and
deliberately does not investigate — "if a single bead needs real investigation, flag it and move
on". Refine mode is where that flagged bead goes.

**R1. Resolve the owning store — before any read or write.**

Bead IDs do **not** resolve across stores: `bd show skills-1fw` from a workspace root fails with
`no issue found`, and that is the usual working directory. Never infer ownership from the cwd.

```bash
~/.agents/skills/next/scripts/next-select resolve <selector>
```

Read-only; it never writes. Act on `status`:

| status | action |
|---|---|
| `resolved` | take `directory`; every later `bd` call uses `bd -C <directory>` |
| `not-found` | the token was just a word — fall through to **free-text** triage, do not error |
| `ambiguous` | show `matches[].selector`, ask which `<repo>:<id>`, mutate nothing |
| `unavailable` | report `failures`, mutate nothing — a probe failed, so ownership is unproven |

**R2. Read the current bead.** `bd -C <directory> show <id>` — note title, description, design,
notes, acceptance criteria, status, priority, labels. An `in_progress` bead may belong to another
session; say so before proposing changes.

**R3. Investigate.** Verify the bead's own claims against the code, don't just read around them.
A bead asserting "X is gated on Y" is a claim to check. Cite what you found — file and line.

**R4. Propose before writing.** Never silently rewrite a description. Show what investigation
changed: which claims held, which were wrong, what scope was missed. Then list the concrete
proposed edits and any new beads.

**R5. Apply on approval**, all in the resolved store:

```bash
bd -C <directory> update <id> --description/--design/--notes/--acceptance/--priority/--labels
```

New beads that investigation revealed go through the normal create path (steps 4–7) so they get
dedup-checked and linked with `bd dep add`.

### Rules

- **Never fabricate scope.** Every correction must be evidence-backed. Draft only from what the
  bead, its comments, and the code actually say — and mark drafted prose for review. Do not
  invent requirements that change what the bead means.
- **A confirmed bead needs no edit.** If investigation says it is already accurate and correctly
  sized, report that and change nothing. Restating a healthy bead is noise.
- **Correct the record when investigation contradicts the bead.** A bead built on a wrong premise
  is worse than a thin one — fix the description and note what was wrong, so it is not re-derived.
- **Closing is the riskiest verb.** Refine mode may *propose* a close with a one-line rationale,
  but requires explicit per-bead confirmation and closes with `bd close --reason="…"`. Never
  batch closes.
- **Splitting stays here.** Unlike `/backlog-groom`, refine mode does not delegate splitting — it
  already owns the create path.

## Priority Guidelines

- **P0-P1**: Critical/urgent (user explicitly says urgent, or blocking issue)
- **P2**: Default for most work (standard feature/task)
- **P3**: Lower priority (nice-to-have, minor improvements)
- **P4**: Backlog (future work, ideas to consider)
