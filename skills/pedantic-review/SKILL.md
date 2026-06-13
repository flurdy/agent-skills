---
name: pedantic-review
description: "Opinionated craft review of your own changes — flags rushed code, missed reuse, misplaced symbols, weak test coverage deltas, and drift from project consensus. Principles-driven (KISS, DRY, SOLID, TDD, YAGNI, DDD) but with anti-noise guardrails. Use when you want the dreaded-but-useful senior reviewer pass before requesting human review."
allowed-tools: "Read,Grep,Glob,Bash(git:*),Bash(gh:*),Bash(make:*),AskUserQuestion"
model: opus
effort: high
version: "1.0.1"
author: "flurdy"
---

# Pedantic Review

A pain-in-the-ass craft review of your own changes — the reviewer you dread but learn from. Flags shortcuts, missed reuse, misplaced code, weak test deltas, and drift from project consensus. Opinionated about software principles, but disciplined about evidence and noise.

This skill complements existing reviews:

- `verify-task` — does it meet the requirements?
- `review-pr` — does it match the Jira AC + CI?
- `clean-code` — does it lint and format?
- `second-opinion` — what does another model think?
- `pedantic-review` — **is the craft any good?**

## When to Use

- Before opening a PR for human review, when you suspect you cut corners
- After a refactor to confirm you actually reduced complexity, not just moved it
- When the change touches a part of the codebase with strong existing conventions
- When you want a critical second pass focused on craftsmanship, not correctness

Do **not** use this skill for:

- Routine config / dependency / docs / translation changes (run `clean-code` instead)
- Reviewing somebody else's PR (use `review-pr`)
- Validating an approach before implementing (use `second-opinion validate-plan`)

## Usage

```
/pedantic-review                  # Review current branch vs main
/pedantic-review --uncommitted    # Review uncommitted changes only
/pedantic-review --staged         # Review staged changes only
/pedantic-review --pr <N>         # Review a specific PR by number
/pedantic-review --verbose        # Include "Consider" tier findings
```

## Operating Principles

The reviewer's job is to make the codebase better, not to demonstrate erudition. Apply these rules to keep findings high-signal:

### 1. Evidence over speculation

Every finding must point to concrete evidence:

- "Possible duplication" → grep for it; if no second site exists, drop the finding.
- "Misplaced method" → name the file it should live in and *why* (existing peers there, naming convention, layering rule).
- "Weak test coverage" → name the specific branch/condition that is uncovered.

If you cannot produce evidence, do not raise the finding.

### 2. Principle-conflict rules

Software principles routinely conflict. When they do, apply this precedence (highest wins):

1. **Match the codebase consensus.** If the repo has a strong existing pattern, follow it even if a textbook would disagree. Note divergence only if the codebase is itself migrating to a new pattern.
2. **YAGNI.** Don't flag missing abstractions for hypothetical future needs. Three similar blocks is fine; only flag duplication on the fourth, or when the duplicates have already begun to drift.
3. **KISS.** Flag added complexity that doesn't pay for itself today. A factory wrapping one constructor is worse than the constructor.
4. **DRY.** Real duplication of *logic* (not just shape) — flag with the specific extraction proposal.
5. **SOLID / DDD / FP idioms.** Flag only when violation actively bites: a class with two unrelated responsibilities that both change frequently is real; one with two methods that *could* be split is not.
6. **TDD discipline.** Flag missing or post-hoc tests that don't exercise the new branches.

### 3. Severity tiers

Each finding gets one of:

| Tier | Meaning | Default visibility |
|------|---------|--------------------|
| **Must** | Real bug, real duplication, real breakage of project consensus, missing test for new branch | Always shown |
| **Should** | Notable craft issue worth fixing now: misplaced symbol, weak abstraction, drifted naming, missed obvious reuse | Always shown |
| **Consider** | Subjective taste call, refactor that *could* help but isn't required | Only with `--verbose` |

If a finding doesn't clearly belong to **Must** or **Should**, demote it to **Consider** or drop it.

### 4. No manufactured concerns

If the change is genuinely small and well-crafted, the verdict is "Looks good" with a one-line note on why. The skill must not invent findings to justify its own existence.

## Instructions

### 1. Determine scope

Parse arguments:

- `--uncommitted` → diff against working tree (`git diff`)
- `--staged` → diff staged changes (`git diff --cached`)
- `--pr <N>` → fetch PR diff (`gh pr diff <N>`) and metadata (`gh pr view <N>`)
- *(default)* → diff current branch vs main (`git diff main...HEAD`)

If the diff is empty, stop and tell the user there's nothing to review.

If the diff is enormous (>1500 lines or >25 files), ask the user whether to:

- Review a subset (specify files / globs)
- Sample the most complex files
- Proceed in full (slower)

### 2. Gather repository context

Before reviewing, build a picture of the surrounding code so findings reference real conventions:

```bash
# Find peer files in the directories being changed — what conventions exist?
git ls-files <changed-dir> | head -50

# Look at recent commits in the touched areas — what patterns have been used?
git log --oneline -20 -- <changed-files>
```

For each significantly changed file, read at least:

- The file itself (full content)
- 1–2 sibling files in the same directory (to see existing conventions)
- The test file(s) for the changed module

This is the most important step. **Most pedantic-review findings come from comparing the change to its neighbours, not from textbook principles.**

### 3. Review across dimensions

Walk through these dimensions in order. For each, produce findings with evidence or move on.

#### 3a. Shortcuts and rushed code

Look for:

- TODO / FIXME / XXX added in this diff
- Stub returns, hardcoded test values, magic numbers without names
- Empty catch blocks, swallowed errors, silent fallbacks
- Commented-out code (delete it; git remembers)
- Obvious copy-paste blocks (look for nearly-identical sequences)
- Inconsistent error handling within the same change

#### 3b. Reuse and duplication

For each new function / helper / utility:

```bash
# Does something similar already exist?
grep -r "<key-words-from-new-function>" --include="<extension>"
```

Flag a **Must** if the new code reimplements existing logic. Flag a **Should** if existing helpers were *almost* a fit and could have been generalised cheaply. Otherwise drop it.

#### 3c. Symbol placement

For each new method / class / constant, ask:

- Does this file's existing purpose match the new addition? Or is it being used as a junk drawer?
- Are siblings of this symbol elsewhere? (e.g., other validators in `validators/`, other date helpers in `date.ts`)
- Does the import graph make sense, or does this create an awkward cross-layer dependency?

```bash
# Find peers of the new symbol
grep -r "function <similar-name-pattern>" --include="*.<ext>"
```

Flag misplacement only when there is a clear better home with existing peers.

#### 3d. Test coverage delta

Not "are there tests" — `verify-task` already covers that. The pedantic question is: **did the tests actually improve?**

- Do the new tests exercise the new branches, or do they assert the same thing the old tests did?
- Is a regression test present for any bug fix? Does it fail without the fix?
- Did test count go up roughly in proportion to code complexity, or did the diff add behaviour with cosmetic test changes?
- Are mocks / fixtures hiding the real behaviour being claimed?

Flag specific uncovered branches by file:line.

#### 3e. Project consensus / style drift

Compare the change to neighbours:

- Naming — does `getUserById` match the codebase or is it `findUser` / `userById` everywhere else?
- Error handling — does this throw / return Result / use a callback the same way as siblings?
- Async style — promises vs async/await consistency
- File / folder structure — does this respect the existing layering?
- Import style, ordering, barrel files
- Test style — do new tests match the framing of existing tests in the same file?

Drift is a **Should** when consistent with the rest of the file; a **Must** when it breaks a load-bearing project convention (e.g., a documented architecture rule).

#### 3f. Principle violations (with the conflict rules from above)

Only flag when a textbook violation actually bites:

- **KISS**: needless layer of indirection, premature factory, over-parameterised function
- **DRY**: real logic duplication, not surface similarity
- **SOLID**: a class doing two unrelated things that *both* change frequently; an interface no caller benefits from
- **YAGNI** *in reverse*: speculative hooks, extension points with no current consumer
- **TDD**: tests written after, asserting the implementation rather than behaviour
- **DDD**: domain logic leaking into transport/UI layers (or vice versa)
- **FP**: needless mutation in a codebase that's otherwise immutable, or vice versa

Each finding must reference the principle *and* the project context that makes it bite.

### 4. Produce the report

Output a structured report. Be ruthless about brevity per finding — one or two sentences each.

```markdown
## Pedantic Review — <scope description>

**Diff:** <files changed>, <+lines>/<-lines>
**Verdict:** <Looks good | Needs craft work | Significant rework recommended>

### Must (<count>)
1. **<short title>** — `path/to/file.ts:42`
   <one-sentence problem>. <one-sentence concrete suggestion>.

### Should (<count>)
1. **<short title>** — `path/to/file.ts:88`
   <one-sentence problem>. <one-sentence concrete suggestion>.

### Consider (<count>) <!-- only with --verbose -->
1. **<short title>** — `path/to/file.ts:120`
   <one-sentence problem>. <one-sentence concrete suggestion>.

### Strengths
- <one or two things the change got right — only if genuinely true>
```

If the change is solid:

```markdown
## Pedantic Review — <scope>

**Verdict:** Looks good.

No significant craft issues. <One-line reason — "matches surrounding conventions, tests cover the new branch, no duplication of existing helpers".>
```

### 5. Offer follow-up

After the report, offer one of:

- "Want me to apply the Must-tier fixes?" (if any)
- "Want me to draft beads for the Should-tier items as follow-up?" (if any)
- "Looks good — ready for `/create-pr`?" (if verdict is clean)

Do not auto-apply fixes. Always ask.

## Anti-Patterns to Avoid

This skill should never produce:

- **Generic citations** — "violates SOLID" without naming which letter and where
- **"Could refactor X"** without an actual reuse target
- **Style nits** the linter would catch (use `clean-code` for those)
- **Restating the diff** — the user just wrote it; they know what they did
- **Praise inflation** — "Strengths" should only list things that are genuinely strong, not filler
- **Hedging** — "this might be a problem" → either it is and you have evidence, or it isn't
- **Ivory-tower critique** — every finding must propose a concrete action the user can take

## Rules

- Read-only — never modify files
- Always cite `file:line` for findings
- Demote or drop findings that lack evidence
- Match-the-codebase trumps textbook correctness
- "Looks good" is a valid and common verdict; do not manufacture concerns
- Do not duplicate `verify-task` (requirements) or `clean-code` (formatting) — focus on craft
