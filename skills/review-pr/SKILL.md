---
name: review-pr
description: Review a pull request by checking the code changes, PR description, and CI status against the linked Jira ticket requirements. Produces an AC checklist and flags concerns.
allowed-tools: "Read,Grep,Glob,Bash(~/.agents/skills/review-pr/scripts/gh-pr-view.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-diff.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-checks.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-current-number.sh:*),Bash(~/.agents/skills/review-pr/scripts/gh-pr-comments.sh:*),Bash(gh pr view:*),Bash(gh pr diff:*),Bash(gh pr checks:*),Bash(gh api:*),Bash(git:*),mcp__jira__*,AskUserQuestion"
model-tier: premium
effort: xhigh
version: "1.0.0"
author: "flurdy"
---

# Review Pull Request

Comprehensively review a PR by comparing code changes against Jira ticket requirements.

## Requirements

- GitHub CLI (`gh`) configured
- Jira MCP server configured (for ticket lookup)

## Usage

```
/review-pr <PR-NUMBER>
/review-pr 5753
```

If no PR number provided, use the current branch's PR.

## Instructions

### Tier guard

This skill is `model-tier: premium`. Before starting, check which model you are
running as. If it is below the premium tier for this runtime (e.g. Sonnet or Haiku in
Claude Code), say so and ask via `AskUserQuestion` whether to:

- **Continue here** — accept reduced depth on this run
- **Stop** — switch model (`/model` in Claude Code) or rerun in a premium session

Skip the prompt when the user explicitly chose the current model. On a premium model,
stay silent and proceed.

Fetch context in this fixed order. Do not skip ahead to analysis or verdict
until every step that applies has been completed — unresolved reviewer
feedback must be surfaced **before** you form an opinion.

1. PR description
2. Review threads (reviews + issue comments + GraphQL thread state)
3. Inline comments per-file
4. CI status
5. Linked Jira ticket context (if a ticket is referenced)

### 1. PR Description

If no PR number provided, resolve it first:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-current-number.sh
```

If the script is unavailable, fall back to:

```bash
gh pr view --json number --jq '.number'
```

Fetch the PR description and metadata (title, body, author, branches, file
counts). Read the body in full — that is where the author explains intent,
scope, and any caveats reviewers should already know about.

```bash
~/.agents/skills/review-pr/scripts/gh-pr-view.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr view {PR_NUMBER} --json title,body,additions,deletions,changedFiles,files,state,author,baseRefName,headRefName
```

Defer fetching the diff itself until step 6 (Analyze) — the description
sets expectations the diff must then meet.

### 2. Review Threads (`gh api`)

Before forming your own opinion, check what other reviewers (human and bot)
have already said. Duplicating their work wastes context; missing their
objections produces wrong verdicts.

The comments script runs three queries in order: reviews + issue comments,
then GraphQL review threads (with `isResolved` / `isOutdated`), then inline
comments grouped per-file. Run it once and read the first two sections now;
the per-file section is step 3.

```bash
~/.agents/skills/review-pr/scripts/gh-pr-comments.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr view {PR_NUMBER} --json reviews,comments
gh api graphql -F owner={OWNER} -F repo={REPO} -F num={PR_NUMBER} -f query='
query($owner:String!,$repo:String!,$num:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$num){reviewThreads(first:100){nodes{isResolved isOutdated path line comments(first:20){nodes{author{login} body createdAt}}}}}}}'
```

What to extract:

- **Review states**: `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, `DISMISSED`. A `COMMENTED` review doesn't block merge but may still contain substantive objections — read the body.
- **Unresolved inline threads**: `isResolved: false` on the GraphQL output. Each is a thread on a specific file/line. Read every comment in the thread to understand the conversation.
- **Issue-level comments**: include any human feedback that wasn't attached to a review.

Treat as noise (mention only if directly relevant):

- Swarmia / Jira / Linear ticket-linker bots
- CI sticky comments (e.g. `terraform-plan-summary`, coverage reports) — useful as data points, not as feedback
- Auto-generated changelog / preview-deploy bots

Treat as signal (must address in the review):

- Human reviewer comments, especially `COMMENTED` reviews — these are often "I'm not blocking but you should know" notes that get missed
- AI code-reviewer bot comments (e.g. `claude-reviewer`, `copilot`, `amazon-q-developer`) — weight them like a human reviewer's first-pass feedback
- Any inline thread where `isResolved: false`

### 3. Inline Comments Per-File

The third section of `gh-pr-comments.sh` groups review comments by file path
(via REST `/pulls/{num}/comments`). Reading per-file makes it easier to
notice when multiple reviewers piled on the same file or when a file
accumulated drive-by suggestions that never became formal threads.

If the script is unavailable, fall back to:

```bash
gh api --paginate "/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments" \
  --jq 'group_by(.path) | map({path: .[0].path, comments: (sort_by(.created_at) | map({author: .user.login, line: (.line // .original_line), body: .body}))})'
```

For each file with comments, note:

- Which reviewers commented and on which lines
- Whether each comment was addressed in a later commit (cross-check against
  the diff in step 6) or replied to
- Repeated themes across files (e.g. "missing tests" raised on three files)

Build a running list of **unresolved comments** (any thread with
`isResolved: false`, plus any per-file comment without an addressing commit
or reply). You will surface this list explicitly in step 8 before giving a
verdict.

### 4. CI Status

```bash
~/.agents/skills/review-pr/scripts/gh-pr-checks.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr checks {PR_NUMBER} 2>/dev/null | awk -F'\t' '{print $2}' | sort | uniq -c
```

Note pass/fail counts and any specific failing or pending checks worth
calling out.

### 5. Linked Jira Ticket Context (Optional)

Find the Jira ticket from (in order of preference):

1. PR title (e.g., `feat: AB-841 pii warning`)
2. PR body (e.g., `Jira ticket number? AB-841`)
3. Branch name (e.g., `feat/AB-841-pii-warning`)

Ticket pattern: 2-4 uppercase letters, dash, numbers (e.g., `AB-23`, `SSP-456`, `MAMA-89`)

**If no ticket found:** Continue with the review without Jira comparison. Skip the AC checklist step, and note in the output that no Jira ticket was linked.

If a ticket is found, fetch its details with the Jira MCP tool:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, description: fields.description, status: fields.status.name, issuetype: fields.issuetype.name, acceptance: fields.customfield_10040}"
```

Parse the description to extract:

- Overview/context
- Acceptance criteria (look for "AC", "Acceptance Criteria", bullet points)
- Any technical requirements

### 6. Analyze the Code Changes

Now fetch the diff and read it against everything gathered above:

```bash
~/.agents/skills/review-pr/scripts/gh-pr-diff.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr diff {PR_NUMBER}
```

For each changed file, understand:

- What was added/modified/deleted
- Whether changes align with ticket requirements
- Whether commits in the diff address the inline comments from steps 2 & 3

For large diffs, save to a file and read in chunks if needed.

**Pay attention to:**

- Deleted code: Is it safe? Are there still imports/usages elsewhere?
- New dependencies: Are they appropriate?
- Test coverage: Are new features tested?
- Security: Any obvious vulnerabilities?

To check if deleted code is used elsewhere:

```bash
# Search for imports of deleted modules
grep -r "from.*{deleted-module}" --include="*.ts" --include="*.tsx"
grep -r "import.*{deleted-module}" --include="*.ts" --include="*.tsx"
```

### 7. Compare PR Against Jira ACs (If Ticket Found)

Create a checklist comparing each acceptance criterion against the implementation:

| AC | Status | Implementation |
|----|--------|----------------|
| {AC from ticket} | {pass/fail/partial} | {How it's implemented or why it fails} |

**If no ticket found:** Skip this step. The review will focus on code quality, CI status, and potential concerns without AC validation.

### 8. Surface Unresolved Comments — Before Any Verdict

**Do not write a verdict, an "overall assessment", or any opinion on the
PR's mergeability until this section has been emitted.** It exists so that
human and AI reviewer feedback is never silently overridden by your own
analysis.

Output an `### Unresolved Reviewer Comments` block listing every item from
the running list built in step 3:

- Each unresolved inline thread (`isResolved: false`) — author, file:line,
  short summary, and your read of whether it is still valid given the
  current diff.
- Each per-file inline comment that lacks a reply or an addressing commit.
- Each `CHANGES_REQUESTED` review or substantive `COMMENTED` review whose
  ask has not been met.

If, after careful reading, the list is genuinely empty, state
`### Unresolved Reviewer Comments\n\n- None.` explicitly. Silence is not an
acceptable substitute — the section must always be present so it is
obvious you actually checked.

### 9. Identify Concerns

Flag any issues beyond the unresolved-comments list:

- **Scope creep**: Changes not related to the ticket
- **Missing ACs**: Requirements not implemented
- **Deleted code**: Large deletions that might break things
- **Missing tests**: New features without test coverage
- **Security**: Potential vulnerabilities
- **Breaking changes**: API changes, removed exports

### 10. Produce Review Summary

Output a structured review. **Order matters:** `Unresolved Reviewer
Comments` must appear before `Verdict` — never the other way round.

```markdown
## PR #{number} Review

**Title:** {title}
**Jira:** {ticket} - {summary}  (or "No Jira ticket linked" if none found)
**Status:** {CI status}
**Reviews:** {e.g. "1 approved, 1 commented (unresolved)" — derived from step 2}

### Changes Overview
- {additions} additions, {deletions} deletions across {changedFiles} files
- {Brief summary of what changed}

### Unresolved Reviewer Comments
- {Each item from step 8 — author, file:line, summary, your assessment of whether it's still valid}
- {Or "None." if there genuinely are no unresolved items}

### AC Checklist (if Jira ticket found)
| AC | Status | Implementation |
|----|--------|----------------|
| ... | ... | ... |

### Concerns
- {List any concerns or none}
- {If no Jira ticket: flag "No Jira ticket linked - cannot verify requirements"}

### Verdict
{Safe to merge / Needs changes / Needs discussion}
```

Verdict rules:

- **Needs changes** if any reviewer has `CHANGES_REQUESTED`, or if any unresolved inline thread raises a valid architectural / correctness objection (even from a `COMMENTED` review or AI bot).
- **Needs discussion** if reviewers disagree or a substantive comment lacks a clear resolution.
- **Safe to merge** only when ACs are met, CI is green, and the `Unresolved Reviewer Comments` section is `None.`.

## Example Output

```
## PR #5753 Review

**Title:** feat: ab-841 pii warning
**Jira:** AB-841 - FE | PII redaction warnings
**Status:** All checks passing
**Reviews:** 1 approved, 0 commented

### Changes Overview
- 136 additions, 1528 deletions across 37 files
- Adds PII redaction instructions to file upload screens
- Removes unused IdVerification component

### Unresolved Reviewer Comments
- None.

### AC Checklist
| AC | Status | Implementation |
|----|--------|----------------|
| Prompt users to redact PII | Pass | New `getUploadInstructionText` utility |
| Different messages per user role | Pass | Three distinct messages |
| Include data-testid | Pass | `data-testid="upload-instruction-text"` |
| Region A only (ok for others) | Pass | Region check in utility |
| Update primary user flow | Pass | Both screens updated |
| Cleanup is fine if nothing breaks | Pass | Deleted unused code, CI green |

### Concerns
- None. Deleted code was not exported or used externally.

### Verdict
Safe to merge. PR fully implements all acceptance criteria.
```

## Example Output (No Jira Ticket)

```markdown
## PR #5801 Review

**Title:** chore: update dependencies
**Jira:** No Jira ticket linked
**Status:** All checks passing
**Reviews:** 0 approved, 0 commented

### Changes Overview
- 45 additions, 32 deletions across 3 files
- Updates npm dependencies to latest versions
- Updates lock file

### Unresolved Reviewer Comments
- None.

### Code Review
- package.json: Minor version bumps for react, typescript
- No breaking changes detected
- No new dependencies added

### Concerns
- No Jira ticket linked - cannot verify against requirements
- Consider adding a ticket reference for traceability

### Verdict
Looks safe to merge. Routine dependency update with passing CI. Recommend linking a Jira ticket for audit trail.
```
