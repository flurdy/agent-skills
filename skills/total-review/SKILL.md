---
name: total-review
description: "Full pre-PR quality gauntlet — runs clean-code, verify-task, simplify, pedantic-review, /review, /security-review, and tiered /second-opinion in increasing cost order. Halts on security/test/p0 findings, emits beads for the rest, iterates the heavy phases up to twice. Local cousin of /ultrareview."
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(gh:*),Bash(bd:*),Bash(make:*),Bash(npm:*),Bash(npx:*),Skill,AskUserQuestion"
model: opus
effort: high
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
| `/simplify` | Phase 3 — cheap reuse/quality cleanup |
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

A **critical finding** halts the gauntlet immediately: emit a P0/P1 bead, report, and stop. Do not proceed to later phases. The user can override and resume by re-invoking with `--continue` (note in the report).

Critical means **any** of:

- Failing test (from `/verify-task` or `make test`)
- Any finding from `/security-review` (no exceptions — every security finding halts)
- Any P0 / P1 severity finding from `/pedantic-review`, `/review`, or `/second-opinion` (in pedantic terms: a **Must Fix** tier finding)
- Secrets detected in the diff (`.env`, credentials, API keys grep)
- Missing required behaviour from `/verify-task` (requirement not met, not just under-tested)

Everything else — partial coverage, minor pedantic findings, style preferences, individual second-opinion suggestions — goes onto the **bead pile** for the final report.

## Instructions

### 0. Parse arguments and orient

Extract from the arguments:

- **scope**: `branch` (default), `uncommitted`, or `pr` (with PR number)
- **--skip-external**: bool, default false
- **--no-iterate**: bool, default false
- **--continue**: bool, default false — resume past a halt, only if user explicitly passes it

Confirm context:

```bash
git status --porcelain
git rev-parse --abbrev-ref HEAD
git log --oneline @{u}..HEAD 2>/dev/null || git log --oneline main..HEAD
```

If `--pr <N>`, fetch the PR diff via `gh pr view {N}` and `gh pr diff {N}` and treat that as the scope.

If there are no changes in scope, stop with a friendly message.

### 1. Phase 1 — Clean Code (auto-fix)

```
Skill /clean-code
```

`clean-code` auto-fixes mechanical issues and must exit zero warnings/errors. If it can't reach a clean state, halt — downstream tools assume a lint-clean tree.

### 2. Phase 2 — Verify Task (requirements + tests)

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

### 3. Phase 3 — Simplify (cheap auto-fix)

```
Skill /simplify
```

`/simplify` auto-applies cheap reuse/quality improvements. Treat any **prompt-before-apply** suggestions as findings — apply them inline only if mechanical and safe, otherwise queue as a P2 bead.

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

### 7. Phase 7 — Single External Opinion (Codex, cheap)

If `--skip-external` is set, jump to Phase 9.

```
Skill /second-opinion review-pr --agent codex
```

The intent here is **another critic** at low cost — runs Codex alone, smaller context. Parse findings:

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

If `--skip-external` is set, jump to Phase 10.

```
Skill /second-opinion review-pr --agent all
```

This runs Claude + Codex + Gemini in parallel. The purpose is **consensus**, not new criticism — the code should already be clean. Treat any finding here as:

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
- {file:line} — {what clean-code/simplify changed}

### Next steps
- {recommended action based on outcome}
```

Recommended next steps by outcome:

- **All clear, no beads** → "Run `/create-pr` to open the PR. Optionally `/ultrareview` for a deeper cloud-agent pass before requesting human review."
- **Bead pile (no halts)** → "Address bead pile (`/next` to pick), then re-run `/total-review`. Or open PR now and address beads as follow-ups if the pile is low-priority only."
- **Halted** → "Fix the halt finding (bead {id}), then re-run `/total-review --continue` to resume past the halt, or re-run normally to restart from Phase 1."

## Bead Emission

Use `bd create` for every finding that isn't fixed inline:

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

If `bd` is unavailable in the repo, fall back to listing findings in the final report under a "Findings (no beads created — `bd` not available)" section.

## Auto-fix Policy

| Phase | Auto-fix? |
|-------|-----------|
| 1 — clean-code | Yes — that's its job |
| 2 — verify-task | No — never modifies code |
| 3 — simplify | Yes for mechanical; prompt for behavioural |
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
