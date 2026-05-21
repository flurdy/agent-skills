---
name: review-pr
description: Review a pull request by checking the code changes, PR description, and CI status against the linked Jira ticket requirements. Produces an AC checklist and flags concerns.
allowed-tools: "Read,Grep,Glob,Bash(~/.claude/skills/review-pr/scripts/gh-pr-view.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-diff.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-checks.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-current-number.sh:*),Bash(~/.claude/skills/review-pr/scripts/gh-pr-comments.sh:*),Bash(gh pr view:*),Bash(gh pr diff:*),Bash(gh pr checks:*),Bash(gh api:*),Bash(git:*),mcp__jira__*"
model: opus
effort: high
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

### 1. Get PR Details

If no PR number provided, resolve it first:

```bash
~/.claude/skills/review-pr/scripts/gh-pr-current-number.sh
```

If the script is unavailable, fall back to:

```bash
gh pr view --json number --jq '.number'
```

Fetch comprehensive PR information:

```bash
~/.claude/skills/review-pr/scripts/gh-pr-view.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr view {PR_NUMBER} --json title,body,additions,deletions,changedFiles,files,state,author,baseRefName,headRefName
```

Get the full diff:

```bash
~/.claude/skills/review-pr/scripts/gh-pr-diff.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr diff {PR_NUMBER}
```

Get CI status:

```bash
~/.claude/skills/review-pr/scripts/gh-pr-checks.sh {PR_NUMBER}
```

If the script is unavailable, fall back to:

```bash
gh pr checks {PR_NUMBER} 2>/dev/null | awk -F'\t' '{print $2}' | sort | uniq -c
```

### 2. Fetch Existing Reviews & Comments

Before forming your own opinion, check what other reviewers (human and bot) have already said. Duplicating their work wastes context; missing their objections produces wrong verdicts.

```bash
~/.claude/skills/review-pr/scripts/gh-pr-comments.sh {PR_NUMBER}
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

### 3. Extract Jira Ticket (Optional)

Find the Jira ticket from (in order of preference):

1. PR title (e.g., `feat: AB-841 pii warning`)
2. PR body (e.g., `Jira ticket number? AB-841`)
3. Branch name (e.g., `feat/AB-841-pii-warning`)

Ticket pattern: 2-4 uppercase letters, dash, numbers (e.g., `AB-23`, `SSP-456`, `MAMA-89`)

**If no ticket found:** Continue with the review without Jira comparison. Skip steps 4 and 6, and note in the output that no Jira ticket was linked.

### 4. Fetch Jira Ticket Details (If Ticket Found)

Use the Jira MCP tools to get ticket requirements:

```
mcp__jira__jira_get with:
  path: /rest/api/3/issue/{ticketNumber}
  jq: "{key: key, summary: fields.summary, description: fields.description, status: fields.status.name, issuetype: fields.issuetype.name, acceptance: fields.customfield_10040}"
```

Parse the description to extract:

- Overview/context
- Acceptance criteria (look for "AC", "Acceptance Criteria", bullet points)
- Any technical requirements

### 5. Analyze the Code Changes

For each changed file, understand:

- What was added/modified/deleted
- Whether changes align with ticket requirements

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

### 6. Compare PR Against Jira ACs (If Ticket Found)

Create a checklist comparing each acceptance criterion against the implementation:

| AC | Status | Implementation |
|----|--------|----------------|
| {AC from ticket} | {pass/fail/partial} | {How it's implemented or why it fails} |

**If no ticket found:** Skip this step. The review will focus on code quality, CI status, and potential concerns without AC validation.

### 7. Check CI Status

Summarize the CI status:

- All checks passing?
- Any failures or warnings?

### 8. Identify Concerns

Flag any issues:

- **Unaddressed reviewer feedback**: Substantive comments from step 2 that haven't been resolved or replied to
- **Scope creep**: Changes not related to the ticket
- **Missing ACs**: Requirements not implemented
- **Deleted code**: Large deletions that might break things
- **Missing tests**: New features without test coverage
- **Security**: Potential vulnerabilities
- **Breaking changes**: API changes, removed exports

### 9. Produce Review Summary

Output a structured review:

```markdown
## PR #{number} Review

**Title:** {title}
**Jira:** {ticket} - {summary}  (or "No Jira ticket linked" if none found)
**Status:** {CI status}
**Reviews:** {e.g. "1 approved, 1 commented (unresolved)" — derived from step 2}

### Changes Overview
- {additions} additions, {deletions} deletions across {changedFiles} files
- {Brief summary of what changed}

### Reviewer Feedback
- {Each substantive unresolved comment/review from step 2 — author, file:line, summary, your assessment of whether it's valid}
- {Omit this section only if there is no human or AI reviewer feedback at all}

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
- **Safe to merge** only when ACs are met, CI is green, and no unaddressed substantive feedback remains.

## Example Output

```
## PR #5753 Review

**Title:** feat: ge-841 pii warning
**Jira:** GE-841 - FE | Unitary AI PII Instructions
**Status:** All checks passing

### Changes Overview
- 136 additions, 1528 deletions across 37 files
- Adds PII redaction instructions to file upload screens
- Removes unused IdVerification component

### AC Checklist
| AC | Status | Implementation |
|----|--------|----------------|
| Prompt users to redact PII | Pass | New `getUploadInstructionText` utility |
| Different messages for Employed/Retired/Volunteer | Pass | Three distinct messages |
| Include data-testid | Pass | `data-testid="upload-instruction-text"` |
| BLC UK only (ok for others) | Pass | Brand check in utility |
| Update request new card journey | Pass | Both screens updated |
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

### Changes Overview
- 45 additions, 32 deletions across 3 files
- Updates npm dependencies to latest versions
- Updates lock file

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
