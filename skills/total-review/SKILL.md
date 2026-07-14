---
name: total-review
description: "Full pre-PR quality gauntlet — runs clean-code, verify-task, code-review, pedantic-review, /review, /security-review, and tiered /second-opinion in increasing cost order. Halts on Must-Fix tier findings (failing tests, security, blocking-severity bugs), emits beads for the rest, iterates the heavy phases up to twice. Local cousin of /ultrareview."
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(gh:*),Bash(bd:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Skill,AskUserQuestion"
model-tier: premium-review
model-cost-policy: deliberate-premium
model-metered-policy: ask-above-standard
effort: xhigh
version: "0.1.0"
author: "flurdy"
---

# Total Review

The complete pre-PR quality gauntlet. Runs every review skill in increasing cost order, halts on critical findings, emits beads for the rest, and iterates the heavy phases up to twice. The local-iterating cousin of `/ultrareview`.

## When to Use

- Before opening a PR for human review, when the change is non-trivial and you want a thorough self-check
- After a refactor or a feature that touched several files
- When you want a deliberate "everything I have, in the right order" sweep without remembering the sequence yourself

## When NOT to Use

- Trivial config / docs / translation changes — run `/clean-code` alone
- WIP commits mid-task — use `/verify-task` instead
- Reviewing someone else's PR — use `/review-pr`
- As the final external panel — `/ultrareview` is the cloud multi-agent version; this skill ends by suggesting it

## Relationship to other skills

This is a **synthesis layer**. It calls existing skills, it does not reimplement them.

| Skill | Role in this gauntlet |
|-------|-----------------------|
| `/clean-code` | Phase 1 — auto-fix lint/format |
| `/verify-task` | Phase 2 — requirements + test coverage |
| `/code-review` | Phase 3 — cheap reuse/quality cleanup (formerly `/simplify`) |
| `/pedantic-review` | Phase 4 — craft critique |
| `/review` | Phase 5 — built-in correctness review |
| `/security-review` | Phase 6 — security audit (any finding halts) |
| `/second-opinion` | Phase 7 — tiered external review (single → panel) |
| `/ultrareview` | Suggested next step after the gauntlet — deeper cloud-agent pass |
| `/ready-to-merge` | Suggested next step after `/create-pr` — post-PR merge gate |

## Usage

```
/total-review                # Branch vs main, full sequence
/total-review --uncommitted  # Uncommitted changes only
/total-review --skip-external # Skip /second-opinion phases (cost cap)
/total-review --no-iterate   # Single pass through analytical phases
/total-review --pr <N>       # Run against an existing PR
```

## Critical Findings (Halt Criteria)

A **critical finding** halts the gauntlet immediately: emit a P0 bead, report, and stop. Do not proceed to later phases. Restart from Phase 1 after fixing the halt finding (re-run normally — there is no resume mode).

Critical means **any** of:

- Failing test (from `/verify-task` or `make test`)
- Any finding from `/security-review` (no exceptions — every security finding halts)
- A **Must Fix** tier finding from `/pedantic-review`, or a **blocking-severity** finding from `/review` or `/second-opinion` (these phases label findings explicitly — only that top tier halts)
- Secrets detected in the diff (`.env`, credentials, API keys grep)
- Missing required behaviour from `/verify-task` (requirement not met, not just under-tested)

Everything else — including `Should Fix` (P1) pedantic findings, generic correctness bugs, partial coverage, style preferences, and individual second-opinion suggestions — goes onto the **bead pile** for the final report. P1 is heavy enough to track but not heavy enough to stop the gauntlet.

## Instructions

### Tier guard

This skill is `model-tier: premium-review`. Before starting, check which model you are
running as. If it is below the premium tier for this runtime (e.g. Sonnet or Haiku in
Claude Code), say so and ask via `AskUserQuestion` whether to:

- **Continue here** — accept reduced depth on this run
- **Stop** — switch model (`/model` in Claude Code) or rerun in a premium session

Skip the prompt when the user explicitly chose the current model. On a premium model,
stay silent and proceed.

### 0. Parse arguments and orient

Extract from the arguments:

- **scope**: `branch` (default), `uncommitted`, or `pr` (with PR number)
- **--skip-external**: bool, default false
- **--no-iterate**: bool, default false
- **--inline-findings**: bool, default false — skip `bd create`, render all findings in the final report only

Confirm context, then **snapshot the scope** so later phases compare against a fixed SHA even if new commits land mid-run:

```bash
git status --porcelain
git rev-parse --abbrev-ref HEAD
SCOPE_HEAD=$(git rev-parse HEAD)
SCOPE_BASE=$(git merge-base origin/main HEAD 2>/dev/null || echo main)
git log --oneline ${SCOPE_BASE}..${SCOPE_HEAD}
```

Record `SCOPE_BASE` and `SCOPE_HEAD` once at Phase 0 and use `git diff ${SCOPE_BASE}..${SCOPE_HEAD}` for every subsequent phase. Do not re-read `HEAD` between phases — the gauntlet reviews a frozen scope, not a moving target.

For `--uncommitted` scope, snapshot the staged+unstaged diff once into `/tmp/total-review-scope.patch` and re-use it across phases.

If `--pr <N>`, set the scope to that PR. Phases 1–3 (`clean-code`, `verify-task`, `code-review`) mutate the working tree, so they require a checkout of the PR branch:

- If the local working tree is clean (`git status --porcelain` empty) **and** no unrelated branch is checked out — run `gh pr checkout {N}` and proceed normally through all phases.
- Otherwise — fall back to **diff-only mode**: skip Phases 1–3, fetch the PR diff via `gh pr diff {N}` and `gh pr view {N}`, and run Phases 4–9 against that diff. Note the skip in the final report.

Never run Phases 1–3 against the current checkout when `--pr <N>` points at a different branch — that would mutate the wrong tree.

If there are no changes in scope, stop with a friendly message.

### 1. Phase 1 — Clean Code (auto-fix)

```
Skill /clean-code
```

`clean-code` auto-fixes mechanical issues and must exit zero warnings/errors. If it can't reach a clean state, halt — downstream tools assume a lint-clean tree.

### 2. Phase 2 — Verify Task (requirements + tests)

First, check whether the scope contains any **code files** — files outside `*.md`, `*.txt`, `docs/`, `LICENSE`, and other pure-documentation paths:

```bash
git diff --name-only ${SCOPE_BASE}..${SCOPE_HEAD} | grep -vE '\.(md|txt|rst)$|^docs/|^LICENSE' | head -1
```

If empty (markdown / docs / config only) → **skip Phase 2 with a note**: "Phase 2 skipped — diff contains no code files." `verify-task` has nothing meaningful to verify against a docs-only diff.

Otherwise:

```
Skill /verify-task
```

Read the verification report carefully. Map outcomes:

| `/verify-task` says | Action here |
|---|---|
| Verdict: Ready to commit | Continue |
| Test failure | **Critical — halt** |
| Requirement not met | **Critical — halt** |
| Partial test coverage | Add to bead pile (priority 2), continue |
| Tests not needed | Continue |

If halted, emit a P0 bead and stop.

### 3. Phase 3 — Code-review (cheap auto-fix)

Apply the same code-files-in-scope check as Phase 2. If the diff is docs-only, **skip Phase 3 with a note**: "Phase 3 skipped — diff contains no code files." `/code-review` is a code reuse/quality scan and has no signal on prose.

Otherwise:

```
Skill /code-review
```

`/code-review` (formerly `/simplify`) auto-applies cheap reuse/quality improvements. Treat any **prompt-before-apply** suggestions as findings — apply them inline only if mechanical and safe, otherwise queue as a P2 bead. An effort level can be passed (e.g. `/code-review high`) if a deeper pass is wanted, but the default is appropriate for this phase.

After this phase, re-run `make clean-code` if any edits were applied (a cheap sanity check that auto-fixes didn't reintroduce lint).

### 4. Phase 4 — Pedantic Review (craft critique)

```
Skill /pedantic-review
```

Parse findings by tier:

- **Must Fix** → critical, halt
- **Should Fix** → P1 bead, add to pile
- **Consider** → P2/P3 bead, add to pile

Do **not** auto-apply pedantic fixes — the value of pedantic-review is the user making the call. Emit beads, don't edit code.

### 5. Phase 5 — Built-in Review (`/review`)

```
Skill /review
```

Parse the output:

- Bugs / correctness issues → P1 bead at minimum; if "blocking severity" wording, treat as critical and halt
- Style / preference notes → P3 bead
- Compliments / "looks good" → ignore

### 6. Phase 6 — Security Review (`/security-review`)

```
Skill /security-review
```

**Any** non-empty finding here is critical. Emit P0 bead per finding, halt the gauntlet. Re-runs after fixing must come back clean before continuing.

If `/security-review` returns clean, continue.

### 7. Phase 7 — Single External Opinion (standard independent pass)

If `--skip-external` is set, jump to Phase 9.

Use the lowest responsible independent route first. Prefer Codex/OpenAI OAuth where configured.
Do not use Claude or OpenRouter as an unbounded default loop; if the selected route is metered,
keep the timeout/scope small and state that it is a deliberate external pass.

First, check whether the scope has a reviewable PR:

```bash
gh pr view --json number 2>/dev/null
```

Branch with an open PR → invoke the review mode:

```
Skill /second-opinion review-pr --agent codex
```

No PR (test run on `main`, unpublished branch, `--uncommitted` scope) → fall back to ask mode, feeding the diff as the question body:

```
Skill /second-opinion ask "Review this diff as a critical PR reviewer. Focus on internal contradictions, under-specified behaviour, wrong commands or paths, and silent failure modes. Be terse, severity-tagged. Diff follows:\n\n<diff>" --agent codex
```

**Never call `codex exec` directly from this skill.** The `/second-opinion` skill handles CLI invocation, stdin, and quoting safely; bypassing it risks shell-quoting hangs (e.g. backtick-laden diffs in `$(cat patch)` substitutions).

Parse findings either way:

- "Bug" / "incorrect" / "missing handling" → P1 bead; if the reviewer flags blocking severity, halt
- "Consider" / "suggest" → P2 bead
- Style / nit → P3 bead

After this phase, decide whether to iterate (Phase 8) or proceed to the wide panel (Phase 9).

### 8. Phase 8 — Iterate (optional, max 2 total passes through phases 4–7)

Iterate **only if** all of:

- `--no-iterate` was not passed
- Some bead-worthy non-trivial findings were emitted in phases 4–7 **and the user has just applied fixes** for them (ask via `AskUserQuestion` — "Apply fixes for these findings now and re-run analytical phases?")
- The current pass count is < 2

If iterating, jump back to Phase 1 (re-lint the new state) and proceed through Phase 7 again. The second pass should converge — if new critical findings appear in pass 2 that didn't exist in pass 1, halt and report (the change introduced regressions).

If not iterating, proceed to Phase 9.

### 9. Phase 9 — Wide Panel Consensus

If `--skip-external` is set, jump to Phase 10. A normal `/total-review` run approves one
standard external pass, not necessarily an expensive panel. Because this phase may invoke
multiple premium or metered routes, ask for confirmation unless the user explicitly requested
`--agent all`, a wide panel, or full premium review.

Same PR-detection as Phase 7. Branch with an open PR:

```
Skill /second-opinion review-pr --agent all
```

No PR (fall back to ask mode):

```
Skill /second-opinion ask "Review this diff for consensus. Focus on issues not yet caught by /pedantic-review, /review, /security-review, and a prior Codex pass. Be terse, severity-tagged. Diff follows:\n\n<diff>" --agent all
```

This runs Claude + Codex + Gemini in parallel when those CLIs are configured. The purpose is
**consensus**, not new criticism — the code should already be clean. Claude is a deliberate
premium review lane; Gemini is especially useful for long-context review; any OpenRouter-backed
routes must be capped or explicitly approved. Treat any finding here as:

- Agreed by ≥2 agents → P1 bead (multi-agent consensus is a stronger signal)
- Single-agent finding → P2/P3 bead, add to pile

If multiple agents agree on a critical finding, halt — that's a strong signal something is genuinely wrong.

### 10. Phase 10 — Final Report

Render a single readout. Quiet success — only show sections that have content.

```markdown
## Total Review — {branch | PR #N | uncommitted}

**Outcome**: ✅ All clear | ⚠️ Bead pile ready | ❌ Halted at Phase {N}

**Passes**: {1 or 2}
**External phases**: {ran | skipped}

### Halt reason _(omit if not halted)_
{Phase, finding, bead id created}

### Bead pile _(omit if empty)_
| Bead | Priority | Source phase | Summary |
|------|----------|--------------|---------|
| {id} | P{0–3}   | {phase}      | {one line} |

### Auto-applied fixes _(omit if none)_
- {file:line} — {what clean-code/code-review changed}

### Next steps
- {recommended action based on outcome}
```

Recommended next steps by outcome:

- **All clear, no beads** → "Run `/create-pr` to open the PR. Optionally `/ultrareview` for a deeper cloud-agent pass before requesting human review."
- **Bead pile (no halts)** → "Address bead pile (`/next` to pick), then re-run `/total-review`. Or open PR now and address beads as follow-ups if the pile is low-priority only."
- **Halted** → "Fix the halt finding (bead {id}), then re-run `/total-review` to restart from Phase 1. The full re-run is intentional — cheap phases stay cheap, and any new lint/test fallout from the fix gets caught."

## Bead Emission

Default behaviour: use `bd create` for every finding that isn't fixed inline:

```bash
bd create --title="<short title>" \
  --type=<bug|task> \
  --priority=<0|1|2|3> \
  --description="<finding details + source phase + file:line refs>"
```

Conventions:

- **Type**: `bug` for correctness/security/test failures, `task` for cleanups/refactors/style.
- **Title**: prefix with `[total-review]` so they're easy to find later.
- **Description**: must include source phase, severity rationale, and file paths so future-you can act on it without re-running the gauntlet.
- Capture each finding as its own bead — do NOT batch unrelated findings together.

**Skip bead emission entirely** in any of these cases — render findings inline in the final report instead, under a "Findings" section grouped by source phase:

- `--inline-findings` flag was passed (e.g. utility / skills / docs repos where beads add noise)
- `bd` is not available in the repo (`which bd` fails)
- The repo has no beads configuration (`.beads/` missing and no `bd` initialised)

In all three cases the final report grows a "Findings" section; halts still print but reference a finding number rather than a bead id.

## Auto-fix Policy

| Phase | Auto-fix? |
|-------|-----------|
| 1 — clean-code | Yes — that's its job |
| 2 — verify-task | No — never modifies code |
| 3 — code-review | Yes for mechanical; prompt for behavioural |
| 4 — pedantic-review | No — emit beads only |
| 5 — review | No — emit beads only |
| 6 — security-review | No — emit beads only (and halt) |
| 7, 9 — second-opinion | No — emit beads only |

After any auto-fix, re-run lint (`make clean-code`) to confirm a clean tree before proceeding.

## Rules

- **Order matters** — never reorder cheaper phases after expensive ones. The whole point is failing fast and cheap.
- **Halt is sticky** — if a phase halts, do not silently continue. Either stop or require `--continue`.
- **Iteration cap is 2 total passes** through phases 4–7. Hard cap. No exceptions.
- **External phases are skippable** via `--skip-external` for cost control. Local phases are not skippable — they're the floor.
- **Never auto-apply fixes** from pedantic / review / security / second-opinion. Their value is in the user's judgement call.
- **Always emit beads, never just print findings**. The bead pile is the deliverable when the gauntlet finishes with non-critical issues.
- **Suggest `/ultrareview` at the end** when the outcome is clean — it's the deeper external follow-up.
- **Be quiet on success.** A clean phase is a one-line "✅ Phase N passed". Save the verbose readout for actual findings.

## Failure modes

- **A sub-skill errors out**: report the error, halt the gauntlet, do NOT silently skip. The user decides whether to retry or skip-with-flag.
- **`/second-opinion` CLI not authenticated**: suggest `--skip-external` or fixing the auth, then continue without external phases.
- **`bd` not available**: fall back to in-report findings list, warn the user.
- **No `make clean-code` target**: try project-appropriate fallbacks (`npm run lint`, `make lint`); if none exist, skip Phase 1 with a warning.
- **`--pr` against a PR with no checkout**: fetch the branch (`gh pr checkout {N}`) before running phases that need a working tree, or fall back to diff-only phases (skip 1–3, run 4–9 on the diff).
