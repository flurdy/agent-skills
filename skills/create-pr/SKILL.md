---
name: create-pr
description: Create a pull request from the current branch following project conventions. Uses the branch name to find the Jira ticket, generates a PR with the standard template, pushes to origin, and closes the associated bead.
allowed-tools: "Read,Bash(git:*),Bash(~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh:*),Bash(~/.agents/skills/next/scripts/next-select:*),Bash(bd close:*),Bash(bd list:*),Bash(bd show:*),Bash(bd update:*),Bash(~/.agents/skills/create-pr/scripts/gh-pr-create.sh:*),Bash(gh pr create:*),Skill,AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "2.1.0"
author: "flurdy"
---

# Create Pull Request

Create a pull request from the current branch using project conventions.

## Usage

```
/create-pr                              # Resolve recorded/default base
/create-pr {base-branch}                # Explicit base, including a stacked parent
/create-pr --draft {base-branch}        # Create a draft PR against that base
```

## Instructions

Parse optional `--draft` plus at most one `{base-branch}`. Reject unknown or duplicate arguments.
Expand `{draft-flag}` to `--draft` when requested and to nothing otherwise.

### 1. Gather context

Get the current branch and working-copy state:

```bash
git branch --show-current
git status -sb
```

If the branch is empty, stop: HEAD is detached. Preserve the commit on a branch before attempting
to push or create a PR.

### 2. Resolve the PR base

Use the first available source:

1. explicit `{base-branch}` argument;
2. `git config --get branch.{branch-name}.gh-merge-base` (recorded by `/stack-branch`);
3. the default branch from `origin/HEAD`, falling back to local `main`, then `master`.

If the result is empty, equals the head branch, or does not resolve to a commit, ask rather than
guessing. Fetch the selected base, then use it consistently for context and PR creation:

```bash
git fetch origin {base-branch}
git log origin/{base-branch}..HEAD --oneline
git diff origin/{base-branch}...HEAD --stat
```

### 3. Extract Jira Ticket from Branch Name

Parse the branch name to find the ticket number:

- Pattern: `{type}/{TICKET-NUMBER}-{description}`
- Example: `feat/AB-123-sanitize-input` → `AB-123`
- Ticket format: 2-4 uppercase letters, dash, numbers (e.g., `AB-123`, `SSP-456`)

If no ticket found, ask the user.

### 4. Look Up Jira Ticket

Use [jira-ticket](../jira-ticket/SKILL.md) for the key, summary and description. It owns tool
availability, deferred discovery and unavailable-context handoffs. If skill invocation is absent,
read that installed skill and follow it; do not reconstruct the lookup. Missing context remains
unavailable in the draft unless supplied by the user; never fabricate fetched requirements.

### 5. Generate PR Title

Use conventional commit format based on branch prefix:

| Branch Prefix | PR Title Format |
|---------------|-----------------|
| `feat/` | `feat(<scope>): <description>` |
| `fix/` | `fix(<scope>): <description>` |
| `refactor/` | `refactor(<scope>): <description>` |
| `chore/` | `chore(<scope>): <description>` |
| `docs/` | `docs(<scope>): <description>` |
| `perf/` | `perf(<scope>): <description>` |

Infer the scope from changed files (e.g., `offers-cms`, `web`, `api`).

### 6. Generate PR Body

Analyze the actual code changes (use `git diff origin/{base-branch}...HEAD`) to write a meaningful description.

House style: say what changed in general terms, easy to digest. Keep the why brief or absent
(Jira/Trello owns it) and details minimal (the commits and diff own them). No test narrative, no
future-task lists, no names, no bead IDs.

Check for a repo-specific PR template at `.github/pull-request-template.md` or `.github/pull_request_template.md`. If found, use that format. If not, ask user for confirmation on generating the body ourselves.


### 7. Confirm push

Run the shared preflight immediately before deciding whether publication is needed:

```bash
~/.agents/skills/start-ticket/scripts/git-branch-preflight.sh {branch-name}
```

Skip this phase only when `target_published=true`: HEAD matches the exact `origin/{branch-name}` destination.
Never infer publication from a parent upstream or stale remote-tracking ref. On `unknown` or a
preflight error, stop. Otherwise show the exact branch and remote. Use `AskUserQuestion`
**immediately before** the push. If approved, the push must be the next tool call, standalone and unchained:

```bash
git push -u origin {branch-name}
```

Approval applies only to this push. A retry requires fresh confirmation. If declined, stop before
PR creation.

### 8. Confirm PR creation

First show the user the target, title, and complete body draft. Then use `AskUserQuestion`
**immediately before** creating the PR. Push approval does not authorize this second remote action.
If approved, invoke the wrapper as the next tool call, standalone and unchained:

```bash
~/.agents/skills/create-pr/scripts/gh-pr-create.sh {draft-flag} --base {base-branch} --title "{title}" --body "$(cat <<'EOF'
{body}
EOF
)"
```

If the script is unavailable, show and separately confirm the fallback before running it:

```bash
gh pr create {draft-flag} --base {base-branch} --title "{title}" --body "$(cat <<'EOF'
{body}
EOF
)"
```

### 9. Close the Associated Bead

Once the PR is created, close the bead for this work — this is the preferred close point in a PR workflow (the commit was done in `/complete-task`, which deliberately left the bead open for this step). Reopen later if review demands major changes.

Skip this whole step silently if `bd` is unavailable or the repo has no beads database.

1. Find the in-progress bead for this work:

   ```bash
   bd list --status=in_progress
   ```

   Match by the Jira key from §3 appearing in the bead title/description, or an obvious 1:1 correspondence to the branch.

2. If multiple beads plausibly match, ask the user which (if any) to close with `AskUserQuestion`. If none match, skip silently — don't invent one.

3. Resolve the chosen bead to its owning store before closing. Never infer the store from the ID or the cwd; at a workspace root the cwd store is the workspace store, not the repository the PR belongs to.

   ```bash
   ~/.agents/skills/next/scripts/next-select resolve <bead-id>
   ```

   | status | action |
   |---|---|
   | `resolved` | take `directory`; close and reopen with `bd -C <directory>` |
   | `ambiguous` | show `matches[].selector`, ask which `<repo>:<id>` is meant; close nothing |
   | `unavailable` | report `failures`; the PR stands, the bead stays `in_progress`, say why |
   | `not-found` | skip the close and say so; never guess another store |

4. Close it in that store, referencing the PR:

   ```bash
   bd -C <directory> close <bead-id> --reason="PR #<number> created: <pr-title>"
   ```

5. Tell the user the bead was closed and how to reopen it if review requires major changes:

   ```bash
   bd -C <directory> update <bead-id> --status=in_progress
   ```

Note: `/ready-to-merge` closes a bead only if it is `in_progress`. It therefore no-ops when this
close remains current, but closes it post-merge if `/review-comments` reopened it for substantial
review work.

### 10. Return Result

Output the PR URL so the user can view it, and note the bead that was closed (or left open, if none matched).
