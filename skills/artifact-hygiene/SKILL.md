---
name: artifact-hygiene
description: Run a local-only, read-only advisory audit of publishable working-tree files and unpublished branch history with redaction-safe findings.
allowed-tools: "Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)"
model-tier: standard
effort: high
version: "0.1.0"
author: "flurdy"
---

# Artifact Hygiene

Run the local-only proof of concept that checks whether repository content is safe to publish. The
helper is the only component allowed to read candidate content. The active model receives normalized,
redacted findings and coverage—not raw candidate content.

This skill is advisory and read-only. It never fetches, follows links, calls remote services, validates
credentials, installs hooks, blocks CI, edits files, changes Git state, rewrites history, or creates
tracker or remote state.

## Scope

The proof of concept scans:

- the full publishable working tree: tracked regular text files plus staged, unstaged, and
  untracked-not-ignored regular text files; and
- unpublished branch commit messages and per-path patches relative to a locally available
  default-branch ref, without fetching. If no remote-backed base is available, it scans all commits
  reachable from `HEAD` rather than treating the current local branch as published.

It uses an audit-owned Gitleaks configuration and empty ignore file, scrubs scanner configuration from
the environment, ignores inline scanner allow-comments, and never passes a baseline. Repository
scanner configuration cannot suppress the audit. Before any clean result, a private runtime canary
must prove that the selected scanner and audit configuration can detect the pinned secret shape. The
helper also reports known session-share links and scanner-suppression controls without exposing
matched values.

GitHub pull requests, Jira, comments, attachments, linked pages, other repositories, full-history
remediation, policy authoring, and enforcement are out of scope.

## Requirements

- Python 3.10 or newer
- Git
- Gitleaks; the proof of concept is locally verified with Gitleaks 8.30.1

A missing or failed scanner produces partial coverage rather than a clean result.

## Run

From the repository to inspect:

```bash
~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py --pretty
```

The helper always emits `artifact-hygiene/v1` JSON to stdout and emits no candidate or child-process
text to stderr.

Exit codes:

- `0` — every required local source completed; inspect `verdict` for `clean` or `findings`.
- `2` — coverage is `partial`; never describe this result as clean.
- `3` — the audit failed before it could establish usable coverage.

## Report

Render coverage before findings:

1. State the overall `status` and `verdict` exactly.
2. List each source and its `complete`, `partial`, or `failed` status plus safe error codes.
3. Group findings by severity and category, using only the normalized location, evidence token, and
   remediation supplied by the helper.
4. If status is partial or failed, name the unavailable coverage and stop short of publication
   assurance.

Never recover raw evidence by reading a reported file, commit, scanner output, temporary file, or
repository configuration. Remediation is a separate explicitly approved task. This skill never mutates
the audited repository.
