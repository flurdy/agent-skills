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

This validates the real degraded path. It does not validate a live non-degenerate Jira/release
workspace: this workspace has no root PRD/architecture/ADR content, no explicitly linked Jira key,
and no configured release source. The structured non-degenerate paths remain covered by the frozen
synthesis fixtures documented in
[`project-brief-synthesis-fixtures.md`](project-brief-synthesis-fixtures.md). A future workspace with
all three live sources should be reviewed before claiming broader production confidence.

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
