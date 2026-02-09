---
name: review-pr
description: Review a pull request by checking the code changes, PR description, and CI status against the linked Jira ticket requirements. Produces an AC checklist and flags concerns.
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

Fetch comprehensive PR information:

```bash
# Get PR metadata
gh pr view {PR_NUMBER} --json title,body,additions,deletions,changedFiles,files,state,author,baseRefName,headRefName

# Get the full diff
gh pr diff {PR_NUMBER}

# Get CI status
gh pr checks {PR_NUMBER}
```

If no PR number provided:

```bash
gh pr view --json number
```

### 2. Extract Jira Ticket

Find the Jira ticket from (in order of preference):

1. PR title (e.g., `feat: AB-841 pii warning`)
2. PR body (e.g., `Jira ticket number? AB-841`)
3. Branch name (e.g., `feat/AB-841-pii-warning`)

Ticket pattern: 2-4 uppercase letters, dash, numbers (e.g., `AB-23`, `SSP-456`, `MAMA-89`)

### 3. Fetch Jira Ticket Details

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

### 4. Analyze the Code Changes

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

### 5. Compare PR Against Jira ACs

Create a checklist comparing each acceptance criterion against the implementation:

| AC | Status | Implementation |
|----|--------|----------------|
| {AC from ticket} | {pass/fail/partial} | {How it's implemented or why it fails} |

### 6. Check CI Status

Summarize the CI status:

- All checks passing?
- Any failures or warnings?

### 7. Identify Concerns

Flag any issues:

- **Scope creep**: Changes not related to the ticket
- **Missing ACs**: Requirements not implemented
- **Deleted code**: Large deletions that might break things
- **Missing tests**: New features without test coverage
- **Security**: Potential vulnerabilities
- **Breaking changes**: API changes, removed exports

### 8. Produce Review Summary

Output a structured review:

```markdown
## PR #{number} Review

**Title:** {title}
**Jira:** {ticket} - {summary}
**Status:** {CI status}

### Changes Overview
- {additions} additions, {deletions} deletions across {changedFiles} files
- {Brief summary of what changed}

### AC Checklist
| AC | Status | Implementation |
|----|--------|----------------|
| ... | ... | ... |

### Concerns
- {List any concerns or none}

### Verdict
{Safe to merge / Needs changes / Needs discussion}
```

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
