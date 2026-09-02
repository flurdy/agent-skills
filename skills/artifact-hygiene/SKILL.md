---
name: artifact-hygiene
description: Run a local-only, read-only advisory audit of publishable working-tree files and unpublished branch history with redaction-safe findings.
allowed-tools: "Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)"
model-tier: standard
effort: high
version: "0.3.3"
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
helper also reports known session-share links, Bead references, email addresses, name-like personal data (personal names),
AI attribution trailers or boilerplate, and scanner-suppression controls without exposing matched values.

The `custom-detectors` coverage source proves every built-in non-secret detector still matches its
private canary. Missing detector coverage produces a partial result, never a clean result. Personal-name
detection is advisory and contextual: it detects direct requests to contact a named person or handle, not
capitalized technical phrases. Expected `Co-authored-by:` and `Signed-off-by:` trailers are excluded from
personal-data findings. Bead-reference, personal-data, and AI-attribution detectors scan unpublished history only—commit
messages and added patch lines—rather than re-reporting content already published on the base branch. Bead references and
personal-data matches in dependency lockfiles are ignored, as are email addresses under reserved example domains.
Email addresses in the `owner`, `created_by`, and `assignee` fields of Beads `.beads/issues.jsonl`
records are treated as structural attribution; unrelated fields remain reportable.

A clone may allow Bead references only with local, unshared configuration:

```bash
git config --local artifactHygiene.allowBeadReferences true
# or ARTIFACT_HYGIENE_ALLOW_BEAD_REFERENCES=1 artifact_hygiene.py --pretty
```

The selected override is reported in `target.policy`; a checked-in configuration file cannot disable a
detector.

A clone may allow one exact public-by-design client key using the redacted finding's `allowId`:

```bash
git config --local --add artifactHygiene.allowSecretFingerprints ah1:<fingerprint>
```

The fingerprint is bound to the scanner rule and exact matched value, not its path or line, so replacing
the key produces a new finding. Matching findings remain visible under `suppressed` and in the summary.
Only valid IDs from clone-local Git configuration are honored; repository files, environment variables,
global Git configuration, paths, and scanner rule names cannot grant this allowance. The helper hashes
the scanner match in private process memory and never emits the raw value.

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
4. Report any `suppressed` count and state that clone-local fingerprint allowances were applied; use
   only normalized fields and never attempt to recover the matched value.
5. If status is partial or failed, name the unavailable coverage and stop short of publication
   assurance.

Never recover raw evidence by reading a reported file, commit, scanner output, temporary file, or
repository configuration. Remediation is a separate explicitly approved task. This skill never mutates
the audited repository.
