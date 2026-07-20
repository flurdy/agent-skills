---
name: circleci-status
description: Check CircleCI build status and failed job logs for the current GitHub repository. Use when asked whether CircleCI is green, failing, pending, or when needing CircleCI job logs.
allowed-tools: "Bash(~/.agents/skills/circleci-status/scripts/status.sh:*), Bash(~/.agents/skills/circleci-status/scripts/logs.sh:*), Bash(gh api:*), Bash(gh auth status:*), Bash(git config:*), Bash(git branch:*), Bash(git rev-parse:*), Bash(curl:*)"
model-tier: economy
model: haiku
effort: medium
version: "1.0.0"
author: "flurdy"
---

# CircleCI Status

Check the latest CircleCI pipeline/workflow status for the current GitHub repository, with optional failed job logs.

## Authentication

- Basic GitHub commit status/check-run summaries use `gh` when authenticated.
- CircleCI pipeline/workflow/job details require `CIRCLECI_TOKEN` in the local environment.
- CircleCI project slug is derived from `origin`: `gh/{owner}/{repo}`.

Set up once locally if detailed CircleCI API access is needed:

```bash
export CIRCLECI_TOKEN=...
```

or configure the CircleCI CLI/token storage separately and export the token before invoking the skill.

## Usage

```bash
/circleci-status          # Summarise latest status for current branch/HEAD
/circleci-status logs     # Show latest failed job logs for current branch
/circleci-status main     # Summarise latest CircleCI pipeline for branch main
/circleci-status logs main
```

## Instructions

Always run the helper scripts fresh; never reuse prior status output.

### Status mode

For no argument, or an argument other than `logs`, run:

```bash
~/.agents/skills/circleci-status/scripts/status.sh {optional-branch-or-ref}
```

Render:

```markdown
## CircleCI status — {repo} `{branch}`

- GitHub commit status: {state}
- GitHub check runs: {counts by conclusion/status}
- CircleCI: {workflow statuses or token-missing note}
```

If `---CIRCLECI-STATUS---` is `NO_TOKEN`, say:

> CircleCI API details unavailable: set `CIRCLECI_TOKEN` locally. GitHub commit/check status above may still show CircleCI's reported state.

If GitHub status includes CircleCI contexts with `target_url`, include links for failing/pending contexts.

### Logs mode

For `logs` as the first argument, run:

```bash
~/.agents/skills/circleci-status/scripts/logs.sh {optional-branch}
```

Render:

```markdown
## CircleCI logs — {repo} `{branch}`

| Job | Status | Number |
|-----|--------|--------|
```

Then include the tail or relevant failure portion of `---LOGS---`. Keep output concise; prefer the final failing command/error block over dumping thousands of lines. If no token is configured, explain that logs require `CIRCLECI_TOKEN`.

## Failure handling

- `NO_GIT_REPO`: say this must be run inside a GitHub-backed git repo.
- `NO_TOKEN`: show GitHub status if available, and explain how to set `CIRCLECI_TOKEN`.
- CircleCI API errors: report the error and fall back to GitHub commit/check status when present.
