---
name: total-review
description: "Portable pre-PR quality gauntlet: cleanup, verification, craft, correctness, security, and optional independent reviews. Binds every gate to the final scope, reports missing coverage, and caps fix/review passes at two."
allowed-tools: "Read,Write,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git ls-files:*),Bash(git rev-parse:*),Bash(git symbolic-ref:*),Bash(git merge-base:*),Bash(git remote get-url:*),Bash(gh pr view:*),Bash(gh pr diff:*),Bash(bd -C * list:*),Bash(bd -C * show:*),Bash(bd -C * search:*),Bash(bd -C * create:*),Bash(bd -C * update:*),Bash(~/.agents/skills/next/scripts/next-select resolve:*),Bash(~/.agents/skills/next/scripts/next-select stores:*),Skill(clean-code),Skill(verify-task),Skill(pedantic-review),Skill(second-opinion),AskUserQuestion"
model-tier: premium
model: fable
effort: xhigh
version: "1.0.2"
author: "flurdy"
---

# Total Review

A local, bounded pre-PR gauntlet in increasing cost order. Compose installed skills, use explicit
manual review where the host lacks a suitable reviewer, and keep one authoritative ledger of scope,
fixes, gate evidence, and findings. A command's absence or an old clean result is never clearance.

Use before a non-trivial PR or after a substantial refactor. For a trivial change use `clean-code`;
for unfinished work use `verify-task`; for someone else's PR use `review-pr`. This skill does not
commit, push, publish PR feedback, or change the installed client configuration.

## Usage

```text
/total-review                         # Branch changes plus selected local work
/total-review --uncommitted           # Local changes; initial HEAD is the fixed base
/total-review --pr <N> --repo <owner/repo>
/total-review --skip-external         # Explicit local-only coverage
/total-review --no-iterate            # One pass; no fix/review loop
/total-review --inline-findings       # No Beads writes
```

Flags compose; reject conflicting scopes, missing values, duplicate or unknown flags. `--pr` requires
an explicit repository or a verified current-checkout repository identity; never resolve a bare PR
number across repositories. No resume or halt-override flag exists.

## 0. Resolve capabilities and scope

### Portable composition

Read the installed skill by name and follow its instructions with the ledger's exact scope packet.
Use the native skill loader when exposed; otherwise read `~/.agents/skills/<name>/SKILL.md` and
execute its instructions using the current harness's tools. Do not type a slash command into a shell.

| Client | Shared skill resolution |
|---|---|
| Pi | Native skill loading when available; otherwise read the shared SKILL.md with Read. |
| Claude Code | Native Skill tool when available; otherwise read the shared SKILL.md with Read. |
| Codex | Native skill loading when available; otherwise read the shared SKILL.md with the file-reading tool. |

Never infer availability from the client name, a familiar command name, or catalog prose. Check the
exposed tools, installed skill files, and documented project commands first. Host-native correctness
or security reviewers are usable only if their read-only behavior, scope input, and cost policy are
known. Otherwise choose the explicit manual route *before launch*. No new reviewer skills or client
plugins are required. Do not let a composed skill replace the ledger scope with its default branch
or remote PR diff. Read and apply its review procedure to the supplied packet; if the route cannot
accept that scope, mark it unavailable rather than reviewing a different change.
Reading a skill does not grant its tools. G6/G7 require authorized composition of `second-opinion`
with its tools and consent policy; if the harness cannot provide that, record `unavailable`.
The read-file fallback never authorizes running provider CLIs directly from this skill.
Discovered cleanup/test commands require existing per-command permission or a current permission
request; this composer does not restore blanket build-tool grants removed by its delegates.

| Gate | Preferred route | Required | If unavailable |
|---|---|---|---|
| G1 Cleanup | `clean-code`, or documented project formatter/linter | Yes when applicable | Documented equivalent only; otherwise unavailable. |
| G2 Requirements/tests | `verify-task` with supplied requirements and exact scope | Yes | Use its manual requirements/coverage procedure and documented tests; missing execution evidence is unavailable. |
| G3 Craft/reuse | `pedantic-review` with exact scope | Yes for code | Use its installed review procedure manually; if unreadable, unavailable. |
| G4 Correctness | Verified read-only host reviewer | Yes | Run the manual correctness checklist in the reference. |
| G5 Security | Verified read-only host reviewer | Yes | Run the manual security checklist in the reference. |
| G6 Independent peer | `second-opinion` ask mode, peer route | Unless skipped | Record unavailable/declined/skipped, never pass. |
| G7 Premium panel | `second-opinion` ask mode, premium quorum | Opt-in | Record unavailable/declined/skipped, never pass. |

Determine whether G7 is requested at preflight, not after seeing review results; this scope choice
never authorizes metered routes. Freeze the expected gate set before starting: G1–G5 when applicable, G6 by default (excluded only
by `--skip-external`), and G7 only when explicitly requested/accepted. An unrequested G7 is recorded
`skipped` with reason "not requested", never passed. Cost consent remains separate: a requested
review whose route is missing or whose metered consent is declined remains expected but incomplete.
Report intentional exclusions even when the requested coverage is clear.

`clean-code` owns mechanical cleanup; `pedantic-review` already covers reuse. There is no separate
assumed auto-fix command. Manual routes are explicitly labeled self-review, never independent coverage.
Read [evidence and manual gates](references/evidence.md) before starting; it defines the ledger,
snapshot recipe, state meanings, and concrete manual review checks. Git is required; `gh` is required
only for PR scope. Use [verify-task's repository-native gate discovery](../verify-task/SKILL.md#4-discover-repository-native-gates)
for execution obligations; do not maintain a second runner catalog here or guess `npx` downloads.
Missing dependencies degrade as above. Do not install or reconfigure tools during a run.

Honor the runtime's configured model-tier/effort routing. If reduced capability is known, disclose it
and ask to continue or stop, unless the user explicitly selected that model. Never invent a model ID.

### Local scope

Record repository root, current branch, initial HEAD, task requirements, and included/excluded local
paths. Use a **fixed comparison base** for the whole run:

- Branch mode: resolve the actual default branch from `origin/HEAD` or documented repository policy
  (local `main`/`master` only when verified). Resolve its merge-base with initial HEAD to a full SHA.
  Missing/ambiguous base or failed Git commands stop scope collection; never fall back to a literal ref.
- Uncommitted mode: fix the base to initial HEAD, not whichever HEAD exists after a later fix commit.
- Unborn HEAD: ask the user to make the initial commit first; this gauntlet needs a comparison commit.

The initial scope includes committed branch work (branch mode), staged, unstaged, and selected
untracked files. If unrelated local work exists, ask which paths belong before mutation. `clean-code`
is repository-wide: if its writes cannot be separated safely, stop or choose a nonmutating partial
review rather than touching unrelated work. Never discard/stash/reset another change for this skill.
A valid empty scope yields `NO CHANGES`, not a passed gauntlet.

### PR scope

Collect qualified metadata and diff using read-only commands:

```bash
gh pr view {N} --repo {owner}/{repo} --json url,headRefOid,baseRefOid,headRefName,baseRefName,isCrossRepository
gh pr diff {N} --repo {owner}/{repo}
```

Bind repository, PR number, head SHA, and base SHA. Re-read identities after diff collection; a moving
head/base invalidates the packet. For a local full run, prove that the current repository and checkout
match the selected PR, the tree is clean, and local HEAD equals the PR head. Resolve the local
merge-base from those exact commits before mutation. If any proof or commit is unavailable, use
**diff-only** mode, not the current checkout's code. Do not auto-checkout, fetch into a worktree, or
switch branches. Offer a separate user-controlled checkout and fresh run if full local coverage is wanted.

In diff-only mode G1 and executable tests in G2 are `unavailable`. Requirements can still be reviewed,
but that does not imply test execution. Run the read-only gates against the qualified packet; return
`PARTIAL` even if those gates are clean. Do not apply local fixes in diff-only mode.

Once a matching local PR checkout receives accepted fixes, the result is a **local candidate derived
from that PR**, not clearance of the published PR: local fixes are not evidence for the remote PR head.
Do not switch back to a remote-only diff for external review. At the final checkpoint, re-read the
qualified PR head and base; unexpected remote movement invalidates the run and requires fresh scope.

## 1. Run the gates in cost order

Initialize `pass_count=1`. Every gate receives the current scope revision plus requirements and writes
its method, result, evidence, and finding IDs back to the ledger. Missing output, nonzero commands,
partial reads, or an unavailable route are not a clean result. Recheck the scope after every gate.

### G1 — Cleanup and scope refresh

Run `clean-code` when its project target is available. Otherwise use an existing documented equivalent;
never invent commands or silently install dependencies. If no applicable cleanup exists, record `na`
with repository evidence. A missing expected linter is `unavailable`; a failing one halts.

Only mechanical cleanup is automatic. Behavioral fixes need a concrete user choice first. Record all
accepted edits, including files outside the starting diff. Rebuild the scope after every accepted fix,
including formatter changes, before verification or review. Repeat the cleanup check if its first
invocation changed files; only a successful stable run earns `pass` for the new revision.

### G2 — Requirements and tests

Apply `verify-task` to the stated requirements, not an inferred nearby task. Check requirements for
**all** changes, including documentation and config. Docs-only may make executable tests `na`, not the
whole gate. Record the reason; file extensions alone do not establish that config or skill behavior
needs no tests. Use the project's actual test command. Diff-only analysis cannot borrow local tests.

Failing tests or unmet requirements halt. Partial coverage becomes a finding with its concrete gap;
missing required execution evidence is `unavailable`, so the verdict cannot be CLEAR.

### G3 — Craft and reuse

Apply `pedantic-review` read-only to the scope packet and nearby repository patterns. In diff-only
mode use head-pinned neighboring context from the same qualified repository; if unavailable, mark
G3 incomplete rather than reading an unrelated checkout. Its **Must** (or **Must Fix**) tier halts, **Should** becomes a P1 candidate, and **Consider** a P2/P3 candidate.
For pure prose with no meaningful craft dimension, record `na` and why. Do not auto-apply suggestions.
A craft **Owner handoff** naming a new requirements/coverage gap must invalidate G2 even when the
revision is unchanged. Record it under its actual owner, not as a second craft score. A material
handoff halts this run with G2 incomplete; there is no in-pass jump back to G2. Revalidation belongs
to a fresh run from G1 under the sticky-halt rule below, never a hidden extra pass or CLEAR.

### G4 — Correctness

Use the verified native route or the [manual correctness checklist](references/evidence.md#correctness-fallback).
Validate findings against actual code and requirements. Blocking correctness issues halt; other proven
bugs become P1 candidates. Missing context needed to assess correctness is `unavailable`, not pass.

### G5 — Security

Use the verified native route or the [manual security checklist](references/evidence.md#security-fallback).
Any validated security finding halts. A speculative concern remains a finding or evidence gap until
validated; do not label it a clean audit. Never send secrets to reviewers or reproduce secret values
in evidence, prompts, output, or Beads. Sanitize context before independent review; if sanitizing removes
material review context, mark that coverage incomplete rather than pretending to review the whole diff.

### G6 — One independent peer

With `--skip-external`, record `skipped` and continue to the final checkpoint (or the fix decision if
there are findings). Otherwise load `second-opinion` and use its **ask** mode with the current sanitized
scope packet, never a separately fetched PR diff:

```text
second-opinion ask "Review the attached scope revision and requirements. Focus on correctness, contradictions, unsafe commands, and silent failures; cite evidence." --agent peer
```

The skill owns provider independence, read-only tools, bounded timeouts, and metered-route consent.
Include the actual packet, not just the template above. Report incomplete or failed responses faithfully.
Validate material claims before severity assignment; repeated agreement does not prove correctness.

### Fix decision — at most two passes

Halt is sticky: any halt stops later gates and goes to the final report. After the user fixes the halt,
start a fresh run from G1; no hidden resume bypass exists.

Offer the fix option only when iteration is still available. For nonblocking findings within that
budget, offer **Apply selected fixes and re-review** or **Keep findings and finish**; otherwise report
findings and finish without offering in-run edits. Apply nothing without a concrete selection. If selected and iteration is allowed, record the accepted
fix paths, increment `pass_count` before returning to G1, refresh the scope, and rerun G1–G6. The cap is
**2 total passes**, including the first, and never resets inside this run. `--no-iterate` caps it at one.
No fixes are applied inside this run once the cap is reached; changes made anyway invalidate earlier
evidence and produce `PARTIAL` pending a new run. Never report stale reviews as completed on new code.

### G7 — Premium quorum panel

Run once, after the final local pass and peer pass, only with explicit approval (or an explicit current-run
request for that panel). `--skip-external` always skips it. Decline means `declined`, not a completed panel.
This uses the configured `premium` profile; an absent profile is `unavailable`, not a decline or a
built-in default panel. Never substitute another profile silently. Load `second-opinion` and let it enforce configured routes, quorum, independence reporting, and separate
metered-route consent:

```text
second-opinion ask "Review the attached final scope revision for material issues missed by the prior gates; cite repository evidence." --agent quorum --panel premium
```

Use the same final packet and record prior findings without instructing reviewers to agree. Incomplete
quorum is unavailable coverage even if some routes succeed. Panel findings do not start another fix loop;
record them and require a fresh run if fixes change the revision. Never invoke model CLIs directly here.

## 2. Final checkpoint and verdict

Recapture scope immediately before reporting. Any unexpected branch/HEAD/content change, unknown file
provenance, or moved PR identity makes affected evidence `stale`; stop and ask for a fresh scope rather
than silently expanding it. Expected accepted fixes require their own revision and gate reruns.
The final ledger—not an early snapshot, phase counter, or saved "looks good"—is authoritative.

Derive the outcome in this order:

1. **HALTED** — validated halt finding or failed required command; record later gates as `not-run`.
2. **PARTIAL** — missing expected gate evidence (unavailable, stale, pending, not-run, failed,
   declined, or skipped), or diff-only execution. If core gates pass but an expected independent
   route is incomplete, say "core gates clear; external coverage incomplete"—never full-gauntlet clearance.
3. **FINDINGS** — complete current evidence with nonblocking unresolved findings.
4. **CLEAR** — every expected applicable gate passed on the final revision, no unresolved findings,
   and no expected coverage missing. Evidence-backed `na` is permitted only for an inapplicable check.

CLEAR is scoped to the expected gate set: label intentional exclusions explicitly, e.g. "CLEAR —
local-only; external skipped" or "CLEAR — core + peer; premium panel not requested". Neither claims
the omitted reviewer ran; only all seven passed gates permit full-gauntlet clearance.

`PARTIAL` can include actionable findings; neither hides the other. Preserve successful individual
routes without promoting a partial panel to complete. Never claim merge readiness or clearance of
unpublished changes on the remote PR.

Render one compact report from the ledger:

```markdown
## Total Review — {scope / local candidate derived from PR}
**Outcome:** CLEAR | FINDINGS | PARTIAL | HALTED | NO CHANGES
**Scope:** {repository, fixed base, final HEAD, revision, included/excluded paths}
**Passes:** {1 or 2}; **Coverage:** {local/manual/independent/panel limitations}

| Gate | Method | Result | Revision | Evidence / finding IDs |
|---|---|---|---|---|
| ...all seven gates, including skipped and unavailable ones... |

**Accepted fixes:** {paths and reasons, or none}
**Findings:** {validated severity, source, file:line, open/fixed, bead or inline ID}
**Next:** {fix blocker, fill evidence gap, address findings, or create PR}
```

## Findings and tracking

The ledger owns finding identity and status; Beads are downstream tracking, not a second verdict.
Validate and deduplicate findings across gates/passes before writes. Recheck a previously reported
finding on the final revision; a stale finding cannot silently become fixed. Prioritize from validated
impact, not a blanket P0 for every halt. Do not create duplicate beads on the second pass.

With `--inline-findings`, absent Beads, or unproven ownership, keep numbered findings inline. Otherwise
load the Beads baseline, prove the outcome's owning store with `next-select stores`, inspect candidate
existing items in that store, and use `bd -C <directory>` for every read/write. Reuse an existing item
when it owns the same issue; resolve it with `next-select resolve <id>` before updating. New items name
source gate, final revision, severity rationale, and redaction-safe file references. Do not synchronize
Dolt, initialize a store, or close tracking merely because a report says the finding was fixed.

## Failures

- Missing capabilities are recorded before execution. An actual route failure is not permission to switch execution modes.
  Preserve the exact failure and state, stop, and request a same-route retry or explicit user decision.
  In particular, never silently replace a failed subagent with a foreground/CLI process.
- Authentication, timeout, malformed output, or denied cost consent never count as completed review.
  An unavailable optional route may leave the run PARTIAL; no silent retry, cost expansion, or substitution.
- If lint/tests/review generate new source changes, refresh and revalidate them like any other fix.
  Unapproved or unrelated generated changes are a scope blocker; do not hide or revert them.
- No automatic remote mutations, branch switches, commits, broad staging, or history rewrites.
