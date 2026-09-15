---
name: artifact-hygiene
description: Run a local-only, read-only advisory audit of publishable working-tree files and unpublished branch history with redaction-safe findings.
allowed-tools: "Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)"
model-tier: standard
model: sonnet
effort: high
version: "0.6.1"
author: "flurdy"
---

# Artifact Hygiene

Run the local-only proof of concept that checks whether repository content is safe to publish. The
helper is the only component allowed to read candidate content. The active model receives normalized,
redacted findings and coverage—not raw candidate content. Claude Code uses the Sonnet alias for this
bounded interpretation; Pi continues to route by `model-tier`.

This skill is advisory and read-only. It never fetches, follows links, calls remote services, validates
credentials, installs hooks, blocks CI, edits files, changes Git state, rewrites history, or creates
tracker or remote state.

## Placement and enforcement

The helper and skill remain together under `~/.agents/skills/` as the portable, client-neutral audit
discovered by Pi, Claude Code, and Codex. The model can render its redacted advisory report; a hook
cannot. Enforcement therefore stays in thin client-specific hooks that call the helper and map its
result to allow or deny, such as the
[Claude Code push gate in ai-tools](https://github.com/flurdy/ai-tools/tree/main/claude/artifact-hygiene-gate),
without copying detectors or report logic.

## Scope

The proof of concept scans:

- the full publishable working tree: tracked regular text files plus staged, unstaged, and
  untracked-not-ignored regular text files; and
- unpublished branch commit messages and per-path patches relative to a locally available
  default-branch ref, without fetching. If no remote-backed base is available, it scans all commits
  reachable from `HEAD` rather than treating the current local branch as published.

History is scanned through bounded per-record stdin calls, not an unrestricted scanner Git walk.
Blob sizes are checked before generating patches; deletions introduce no content. When a large
predecessor becomes a small file, the full new file is scanned conservatively instead of building a
huge deletion patch. Such findings can include unchanged lines. Repository diff attributes cannot hide
text, and paths are treated literally.

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

The Bead-reference detector matches known prefixes with any 3–8 character base36 suffix and
optional `.N` children, plus a generic digit-bearing shape so a checked-in file can only widen
detection. Known prefixes come from clone-local `artifactHygiene.beadPrefixes` (multi-valued or
comma-separated), `ARTIFACT_HYGIENE_BEAD_PREFIXES`, and the repository's own `.beads/config.yaml`
`issue-prefix` and `.beads/issues.jsonl` IDs; `target.beadPrefixSource` reports which. Plain
hyphenated words such as `dry-run` are not reported, nor are `<prefix>-beads` Dolt remote repository
names. Email matches immediately followed by `:` are treated as scp-style Git URLs and matches
immediately preceded by `://` as URL userinfo (`git+ssh://git@host/…`); personal-name matches stop
at identifier boundaries, and paths under
an `artifact-hygiene/` directory are exempt from the non-secret detectors because the audit's own
source and fixtures necessarily contain canary shapes; secret scanning still covers them.

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

## Oversized blobs

Files over 1,000,000 bytes (including binary files) are not scanned. The helper hashes working-tree
bytes incrementally using Git's raw blob format, without running filters or writing objects. Index
and history entries use their exact Git blob IDs. SHA-1 and SHA-256 repositories are supported.

- A blob reachable anywhere in the locally available remote-backed default base's history is
  `skipped-by-policy` with reason `published-base-history`, including renamed or reintroduced blobs.
  This proves local remote-tracking reachability, not live remote state; the helper never fetches.
- An unpublished blob remains partial (`file-too-large`) and denies publication, with its path,
  blob ID, and required manual override in `sizeDecisions`.
- After independently reviewing the unscanned content, a clone may allow exactly that blob:

  ```bash
  git config --local --add artifactHygiene.allowLargeBlobs <full-blob-id>
  ```

  Only lowercase, full-length IDs matching the repository object format are accepted (multi-valued
  or comma-separated). Changed bytes require another allowance. Only direct clone-local Git
  configuration is honored: checked-in files, Git config includes, environment variables, and global
  configuration cannot grant it. Active allowances appear as `+allow-large-blobs` in `target.policy`;
  applied skips have reason `local-blob-allowance`.

`sizeDecisions` records each skipped or denied source/path/commit/blob combination, the byte size,
reason, and safe remediation. Policy skips keep coverage complete and do not consume the scanned-byte
budget; they do not claim content was inspected. A missing base cannot prove publication. Failed or
bounded-out reachability checks produce `publication-proof-failed`; scanner failures, history-read
failures, file changes, timeouts, and other resource limits still deny, even with a blob allowance.
Reachability first reads one bounded base-tip tree, then uses a cached, bounded
`git log --find-object` proof for each distinct blob absent from that tree. Checks use the
remote-backed base commit, with replace refs, grafts, repository log presentation, commit graphs,
renames, signatures, and path limits disabled. Git 2.31 or newer is required for published-blob
skips. The shared command output and audit deadline still apply; proof failures deny. Size decisions
are capped at 2,000, with overflow reported as partial rather than silently omitted.

GitHub pull requests, Jira, comments, attachments, linked pages, other repositories, full-history
remediation, policy authoring, and enforcement are out of scope.

## Graded publication policy

The v2 report separates coverage `status` from publication `verdict`: `clean`, `advisory`, or `block`.
`policy.grade` is the single finding-grade authority. Severity and confidence remain visible; grading
never relabels a secret match as a verified false positive or a confirmed live credential.

| Condition (first matching row) | Grade |
| --- | --- |
| Partial/failed coverage, unknown category/severity/confidence/location, or failed publication proof | `block` |
| Critical severity | `block` |
| Informational scanner-control finding | `advisory` |
| New working-tree/index or branch-history finding | `block` |
| Already-published, private repository, non-critical finding | `advisory` |
| Already-published Bead reference, AI attribution, or scanner-control finding | `advisory` |
| Already-published secret, session link, or personal data in public/unknown repository | `block` |

Known confidence levels (`high`, `medium`, `low`) are recorded and validated; lower confidence alone
never permits a new finding. Unknown and future categories fail closed. Complete reports with no
unsuppressed findings are `clean`; any blocking finding yields `block`; otherwise they are `advisory`.
Suppressed exact fingerprint matches remain separately visible and do not count toward the verdict.

`location.publication` distinguishes `working-tree`, `branch-history`, and `already-published`.
Working-tree includes staged/index candidates: each occurrence is bound to its containing `blobId`,
so a published file cannot mask different staged bytes at the same path and line. Only proof that the
exact blob is reachable from the remote-backed default base permits `already-published`. Hashes use
raw bytes without Git filters; CRLF conversion, LFS, or other filters can therefore conservatively
leave a working-tree finding blocking even when its index copy is published. Branch history remains conservatively blocking even if a commit was pushed to a feature branch: the scan
range is relative to the default base, not a claim that all those commits are unpushed. Full local
history fallback is reported as `coverage.base: all-reachable`, not as a coverage error when that
scan completes. The informational scanner-control row is the explicit exception to new-content
blocking; repository controls still cannot suppress the scan.

Visibility is an owner assertion, not inferred from a URL, host, or authentication. No network lookup
is performed. The default is `unknown`, which uses the public-safe policy. Only one valid direct
clone-local Git config value is accepted, with includes disabled:

```bash
git config --local artifactHygiene.remoteVisibility private  # or public
```

The result is reported in `target.remoteVisibility` and `target.policy`. Checked-in files, included or
global Git config, and environment variables cannot supply visibility or grading rules. Do not set it
automatically. A private assertion is not proof of the audience of a future push; recheck it when the
repository destination or visibility changes. Advisory findings still deserve review, not rotation
or suppression based solely on the scanner result.

Consumers must validate `artifact-hygiene/v2`, complete coverage, and the verdict's consistency with
finding grades. A v1/v2 mismatch denies; deploy the helper and gate contracts together. Advisory
output never authorizes a push by itself. Grading rules live only in this installed helper.

## Requirements

- Python 3.10 or newer
- Git 2.31 or newer
- Gitleaks; the proof of concept is locally verified with Gitleaks 8.30.1

A missing or failed scanner produces partial coverage rather than a clean result.

## Run

From the repository to inspect:

```bash
~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py --pretty
```

The helper always emits `artifact-hygiene/v2` JSON to stdout and emits no candidate or child-process
text to stderr. The audit has one 600-second deadline, configurable for manual runs with `--timeout`
from 1 to 600 seconds. A deadline expiry is reported only as `deadline-exceeded` on affected coverage
sources; it remains partial and denies publication. `summary.truncated` states whether reported finding
counts are incomplete because the deadline or report-size cap stopped collection.

Exit codes:

- `0` — every required local source completed; `verdict` may be `clean`, `advisory`, or `block`.
- `2` — coverage is `partial`; verdict is `block`, never clean.
- `3` — the audit failed before it could establish usable coverage; verdict is `block`.

## Report

Render coverage before findings:

1. State the overall `status` and `verdict` exactly.
2. List each source and its `complete`, `partial`, or `failed` status plus safe error codes. If
   `summary.truncated` is true, state explicitly that finding counts are incomplete.
3. Group findings by grade, severity, and category, using only the normalized location, evidence
   token, and remediation supplied by the helper. Show `location.publication` and the asserted or
   unknown visibility. An advisory does not mean the content was verified harmless.
4. Report any `suppressed` count and state that clone-local fingerprint allowances were applied; use
   only normalized fields and never attempt to recover the matched value.
5. Render `sizeDecisions`, including every `skipped-by-policy` entry and its reason/blob ID. For
   denied entries, name the file and show the exact clone-local override supplied by the helper;
   never apply it automatically or describe skipped content as scanned.
6. If status is partial or failed, name the unavailable coverage and stop short of publication
   assurance.

Never recover raw evidence by reading a reported file, commit, scanner output, temporary file, or
repository configuration. Remediation is a separate explicitly approved task. This skill never mutates
the audited repository.
