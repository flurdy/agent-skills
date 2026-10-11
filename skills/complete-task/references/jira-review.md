# Jira review offer after completion

Shared, opt-in procedure owned by `complete-task` and used by `create-pr`. After a completion
milestone, it may offer to move the explicitly associated Jira ticket to review when the completing
bead was the last unfinished associated bead. It never transitions without a fresh, visible approval
for one exact ticket and transition.

## Policy

Unconfigured projects are unchanged: no policy means disabled and nothing is reported. A policy is
`.agents/jira-review.toml`, found by searching upward from the repository's **logical** path (the path
you invoked, such as a workspace's `repos/<member>`), then from its physical Git root. The search
stops below `$HOME`, so `~/.agents` never applies everywhere. Nearest wins: a repository file replaces
a workspace or client-directory file entirely; files are never merged.

```toml
milestones = ["pr-created"]         # trunk-commit and/or pr-created
source_statuses = ["In Progress"]   # only these current statuses are eligible
target_status = "In Review"         # the workflow's review status name
```

Status names compare case-insensitively. Unknown keys, empty or duplicate lists, unknown milestones,
or a target that is also a source make the policy invalid: report the skip; never guess. There are no
defaults, universal status names or Done transitions. Unlike `merge-timing.toml`, this file may live
in the repository: it only enables an offer that still needs approval.

| Milestone | Caller and condition |
|---|---|
| `trunk-commit` | `complete-task` closed the bead in trunk mode. The commit may still be unpushed; the prompt shows it. |
| `pr-created` | `create-pr` closed the bead after creating a non-draft PR targeting the default branch. |

## Association and scope

- Only an exact bead `external_ref` of `jira-<KEY>` (the `/triage` convention) associates a bead.
  Keys in titles, descriptions or branch names never do. A caller's branch key that differs skips.
- When the logical path lies in a validated workspace (nearest `workspace.json`, validated by
  `next-select stores`) that registers this repository, every unique workspace store is read once.
  Otherwise only the repository's own store is read. An unvalidated `workspace.json` skips. A physical
  member path cannot discover its workspace, so invoke workspace members through the workspace path.
- Every bead with that reference whose status is anything but `closed` blocks the offer. An unusable
  store, failed or malformed read, row without the exact reference, a completing bead outside the
  scope or missing from its own inventory skips with the reason. Coverage that cannot be proven does
  not prove the ticket is finished.

## Helper

`~/.agents/skills/complete-task/scripts/jira-review.py` requires Python 3.11+, Git, `bd` and the
installed next resolver. It prints one JSON object and exits 0 for every evaluated outcome; treat any
non-zero exit or unparseable output as a skip. It is read-only: it never contacts Jira, writes
tracking, fetches refs or synchronizes stores.

Common arguments: `--bead <id> --store <resolver-proven directory> --milestone <milestone>`, plus
`--repo <logical path>` when not run from the repository, and the caller-specific `--expected-key`,
`--draft` and `--stacked` flags.

## Procedure

Start only after the caller's own successful completion close in this run. Never start from an
abandoned, duplicate or superseded closure, an already-closed bead found later, verification,
tracking sweeps or merges. A later explicit user request may repeat the procedure for that bead.

1. **Local gate.** Run `jira-review.py plan {arguments}`. `disabled`: say nothing. `skip`: report
   one line with reason and detail. `ready`: continue.
2. **Read Jira.** Use [jira-ticket](../../jira-ticket/SKILL.md)'s tool discovery. Read the current
   status and the transitions with their fields: native `jira_get_issue` (fields `status`) and
   `jira_get_transitions`, or the generic adapter's `mcp__jira__jira_get` with paths
   `/rest/api/3/issue/{KEY}?fields=status` and `/rest/api/3/issue/{KEY}/transitions?expand=transitions.fields`.
   A missing capability, permission or request failure is a manual fallback: name the ticket and target
   status; do not repair configuration, retry or guess.
3. **Decide.** Pass the raw responses unedited:

   ```bash
   ~/.agents/skills/complete-task/scripts/jira-review.py decide {arguments} <<'JIRA_REVIEW'
   {"issue": <raw issue response>, "transitions": <raw transitions response>}
   JIRA_REVIEW
   ```

   `noop` (already in the target), `skip` or `disabled`: report and stop. `propose`: continue.
4. **Confirm.** Immediately ask one question with exactly **Move to review** and **Skip**. Show the
   key, `from → to`, transition name, associated bead count, and delivery (commit SHA and whether it
   is pushed, or the PR URL). Skip or an abandoned prompt ends the procedure.
5. **Revalidate after approval.** Repeat steps 1–3, adding `"previous": <proposal>` to the decide
   input. Anything but `propose` is final: `changed`, `skip` or `noop` means no mutation. Approval does
   not carry to a new proposal.
6. **Transition once.** As the next tool call, apply only the approved `transitionId`: native
   `jira_transition_issue`, or `mcp__jira__jira_post` to `/rest/api/3/issue/{KEY}/transitions` with
   body `{"transition": {"id": "<id>"}}`, discovered as [jira-comment](../../jira-comment/SKILL.md)
   discovers its poster. No fields, no retry, no second transition.
7. **Observe.** Re-read the status once:

   | Transition call | Re-read status | Report |
   |---|---|---|
   | Any | Target status | `transitioned` |
   | Reported error | Unchanged source status | `failed` — move it manually |
   | Anything else, or unreadable | Any | `uncertain` — check Jira; do not retry |

## Reporting

Report local completion (commit, bead close, PR) first and the Jira outcome separately. A Jira skip,
decline, failure or uncertainty never reopens the bead, undoes a commit or hides a PR. Repeating the
procedure after a successful move yields `noop`, so it never transitions twice.
