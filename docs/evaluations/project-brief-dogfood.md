# Project-brief workspace dogfood

- **Date:** 2026-07-28
- **Epic:** `agents-esz`
- **Slice:** `agents-esz.4`
- **Runtime:** Pi delegate with the installed `project-brief` skill
- **Run:** `516c3257-f2de-4361-bba4-6b5dc7fb462d`

## Installation evidence

- `~/.agents/skills/project-brief` resolves to the shared skill checkout.
- `~/.claude/skills/project-brief` resolves through the canonical shared skill link.
- The installed `scripts/collect.sh` is executable.
- `make dry-run` completed without stale-link changes.
- `make apply` reinstalled the managed links successfully with zero stale-link removals.
- `make doctor` reported 54 managed canonical skills and `Doctor: PASS`.

## Captured workspace result

The installed skill ran its fresh collector from the Coding Agent Workbench root, then
queried open and merged PRs only for the three repositories in `workspace.json`.
The rendered headline was:

```text
Verdict: INCOMPLETE EVIDENCE
Scope: workspace root + 3 included repositories
Sources: local workspace/Git/Beads snapshot, current scoped GitHub queries,
         empty root intent documents, no eligible Jira keys, release not assessed
Next: LINK the `agents-0kw` dotfiles dependency to explicit ownership and delivery evidence
```

Decisive evidence:

- Workspace, Beads, and mgit validation passed.
- All three registered repositories were included; Git refs remained explicitly unfetched.
- `INTENT-DOCUMENTS` was `EMPTY`, so repository activity was not presented as project-level health.
- Workspace Beads supplied explicit item-level outcomes and acceptance criteria.
- Six bounded GitHub queries (open and merged for each registered repository) returned empty arrays.
- No explicit Jira key was discovered, so Jira was not broadened to the user's assigned portfolio.
- No project release source was configured; release remained `NOT ASSESSED`.
- The brief cited Bead IDs, topology, local Git evidence, and source limitations rather than inventing progress or deployment state.

This validates the real degraded path. It does not validate live Jira or release composition because
this workspace has no root PRD/architecture/ADR content, no explicitly linked Jira key, and no
configured release source.

## BLC live Jira and GitHub result

A subsequent interactive run in the BLC `blc-2` workspace supplied a non-degenerate visual review of
current Jira and GitHub composition:

```text
Verdict: AT RISK
Scope: /home/ivar/Code/blc/workspace + 8 registered repositories
Sources: current Jira/GitHub queries, local Git snapshot, empty root intent documents and
         workspace Beads, PR evidence truncated at 20/21, one repository without an origin
Next: RECONCILE GE-1882 Jira Done with open PRs #82/#83 and failing exact-head Terraform gates
```

The rendered brief preserved four distinct live concerns:

- `GE-1882` was Jira Done while two linked PRs remained open and PR `#83` had six failed exact-head
  Terraform plans.
- `GE-1869` required CMS pages and a homepage while merged PR `#6971` explicitly covered only pilot
  CMS pages.
- `AP-1110` required immediate session revocation while its latest discussion recorded JWT access
  continuing for up to one hour.
- `PROD-2144` remained an in-progress P2 issue after an approved, green revert was merged.

The run also reported eight omitted item-level outcomes, unavailable unresolved-thread counts, one
repository without an origin, unfetched Git remotes, and release `NOT ASSESSED`. It did not infer
release readiness or project-level health from those gaps.

This validates live Jira/GitHub querying, exact-head CI use, contradiction preservation, bounded PR
selection, action ranking, and independent source degradation. Root intent documents, workspace
Beads, and a project-specific release source were still absent, so those live composition paths
remain unvalidated. The frozen synthesis scenarios documented in
[`project-brief-synthesis-fixtures.md`](project-brief-synthesis-fixtures.md) continue to cover them.

The user-supplied screenshot also exposed a contract interpretation to revisit: the headline selected
`AT RISK`
from confirmed item-level threats even though project-level intent was incomplete. That is consistent
with choosing the most severe supported coordination signal, but the degraded-source phrase “cannot
exceed `INCOMPLETE EVIDENCE` for project-level outcome coherence” could be read as requiring an
`INCOMPLETE EVIDENCE` headline. The `High` confidence shown for the unknown project-level-outcome row
was confidence in the observed absence, but may read as confidence in project health.

## Harness finding

The delegate returned the complete brief but the subagent wrapper marked the run failed because it
inferred an implementation acceptance contract and expected changed files despite explicit read-only
instructions. That is a subagent acceptance-inference issue, not a project-brief failure. It is
tracked separately as `agents-ot9`; the captured output and command evidence were still complete.

The subagent also created its normal `.pi-subagents/` transcript artifacts before collection, so the
brief correctly reported that generated untracked root path. The artifacts were removed after the
run and are not part of project state.

## Rollback

The skill has no persistent project state or migration. Rollback is removal of the
`skills/project-brief` source/catalog entry followed by installer re-application. Jira, Beads,
GitHub, and release systems require no cleanup.
