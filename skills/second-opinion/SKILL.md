---
name: second-opinion
description: Query independent AI CLIs for a second opinion; an explicit, locally configured OpenRouter consensus profile is available for high-stakes reviews.
allowed-tools: "Read,Write,Bash(claude:*),Bash(codex:*),Bash(gemini:*),Bash(git:*),Bash(gh:*),Bash(mktemp:*),Bash(chmod:*),Bash(rm:*),Bash(~/.agents/skills/second-opinion/scripts/openrouter-panel.sh:*),Grep,Glob,AskUserQuestion"
model-tier: standard
model: sonnet
effort: medium
version: "1.4.1"
author: "flurdy"
---

# Second Opinion

Query Claude, Codex, or Gemini CLI for an independent review of plans, PRs, code, or bugs. For unusually high-stakes decisions, explicit `consensus` mode uses a locally configured, bounded cross-vendor OpenRouter panel.

## When to Use

- You want a second opinion on a plan, architecture decision, or approach
- You want an independent PR review from another AI
- You want to cross-check a bug triage or root cause analysis
- You want to validate a proposed change before committing
- You explicitly need broad cross-vendor consensus for a high-stakes or hard-to-reverse decision

## Usage

```
/second-opinion                          # Interactive — asks what to review and which agent
/second-opinion review-pr 123            # Review PR #123
/second-opinion review-pr                # Review current branch PR
/second-opinion validate-plan "<plan>"   # Validate a plan/approach
/second-opinion triage-bug "<description>"  # Get bug triage input
/second-opinion ask "<question>"         # Freeform question with repo context
/second-opinion ask "<question>" --agent claude   # Force a specific agent
/second-opinion ask "<question>" --agent codex
/second-opinion ask "<question>" --agent gemini
/second-opinion ask "<question>" --agent all      # Query the three subscription/OAuth-first CLIs
/second-opinion validate-plan "<plan>" --agent consensus  # Explicit bounded OpenRouter panel
/second-opinion review-pr --agent consensus --panel extreme # Select named local panel profile
/second-opinion review-pr --timeout 5             # Allow 5 minutes (default: 3, max: 10)
/second-opinion ask "..." --model fast            # Use the fast tier instead of smart
/second-opinion ask "..." --model gemini-3-pro    # Pass an explicit model ID through
```

## Requirements

- `claude` CLI installed and authenticated (part of Claude Code)
- `codex` CLI installed and authenticated (`codex login`)
- `gemini` CLI installed and authenticated
- `gh` CLI for PR operations
- Consensus mode only: `curl`, `jq`, `OPENROUTER_API_KEY`, and a named profile in `~/.agents/second-opinion/config.json`

Read [references/openrouter-consensus.md](references/openrouter-consensus.md) completely only when the user explicitly selects `--agent consensus`.

## Model Selection and Cost

This skill does not use a portable tier to classify the external model it launches. Exact model
IDs belong in the invoked CLI's configuration where possible, not in this shared skill. By
default, omit model flags and let each CLI use its configured default. Vendor independence and
fresh consent are enforced directly below. The rationale and precedence rules are recorded in
[references/external-model-resolution.md](references/external-model-resolution.md).

Independence rule: a second opinion is only independent if it comes from a **different
vendor than the model that produced the work** (normally the current session model).
Check which model you are running as and pick the default agent accordingly:

- Claude session (Claude Code) → `codex` first, then `gemini`.
- GPT session (pi/Codex) → `claude` first, then `gemini`.

Cost guardrails:

- Prefer subscription/OAuth routes for the first independent pass when the rule allows.
  In particular, `claude -p` uses the Claude CLI's existing authentication; a
  `claude.ai` subscription login consumes subscription usage rather than metered API billing.
- Treat Claude CLI API-key/BYOK authentication as metered. Use Claude deliberately for
  premium review/judgement, not as a default long loop.
- Use Gemini for long-context review or repo-wide summarisation.
- Treat OpenRouter-backed or other API-key/BYOK routes as metered: use `--timeout`, cap
  scope, or ask before broad panels.
- `--agent consensus` is never inferred from `all`, `smart`, a high-risk task, or a configured
  API key. It is separately named, must ask for fresh consent immediately before the first API
  request, and must not store that consent. Read the consensus reference before proceeding.

Overrides:

- `--model fast` — request the caller's configured cheap/fast tier; do not hard-code a model
  ID here. If the CLI has no configured fast alias, omit the flag and note the fallback.
- `--model <id>` — any other value is treated as an explicit model ID and passed through.

The `smart` default requires no maintenance here — it is whatever each CLI/runtime picks.

## Instructions

### 1. Parse Arguments

Extract from the arguments:
- **mode**: one of `review-pr`, `validate-plan`, `triage-bug`, `ask` (default: ask user)
- **target**: PR number, plan text, bug description, or freeform question
- **agent**: `claude`, `codex`, `gemini`, `all`, or explicit `consensus` (default: per the
  independence rule — `codex` from a Claude session, `claude` from a GPT session). `consensus`
  must never be selected implicitly.
- **timeout**: timeout in minutes (default: `3`, max: `10`)
- **panel**: named local consensus profile after `--panel` (default: `extreme`; valid only with explicit `consensus`)
- **model**: `smart` (default), `fast`, or an explicit model ID — see Model Selection and Cost

Look for `--agent <name>` anywhere in the arguments. If not specified, apply the independence
rule from Model Selection and Cost: `codex` in a Claude session, `claude` in a GPT session.
Look for `--timeout <minutes>` anywhere in the arguments. If not specified, default to `3`.
Look for `--model <value>` anywhere in the arguments. If not specified, default to `smart`.
Look for `--panel <name>` anywhere in the arguments. Reject it unless `--agent consensus` was explicit;
default to `extreme` only for consensus mode.

If no mode is provided, ask the user what they'd like a second opinion on.

### 2. Gather Context by Mode

#### review-pr

```bash
# If PR number provided:
gh pr view {PR_NUMBER} --json title,body,additions,deletions,changedFiles,state,baseRefName,headRefName
gh pr diff {PR_NUMBER}

# If no PR number, find current branch PR:
gh pr view --json number,title,body,additions,deletions,changedFiles,state,baseRefName,headRefName
gh pr diff
```

Build a prompt:
```
Review this pull request. Focus on:
- Correctness and potential bugs
- Security concerns
- Performance implications
- Code quality and maintainability
- Missing edge cases or error handling

PR: {title}
Description: {body}

Diff:
{diff}
```

#### validate-plan

The user provides the plan text as the target. Gather additional context:

```bash
# Get repo structure overview for context
git ls-files | head -100
```

Build a prompt:
```
Evaluate this implementation plan for the codebase in the current directory.
Flag any concerns about:
- Feasibility and completeness
- Missing steps or dependencies
- Potential risks or gotchas
- Better alternatives

Plan:
{plan_text}
```

#### triage-bug

Build a prompt:
```
Help triage this bug in the codebase in the current directory.
Analyze:
- Likely root cause
- Which files/components are probably involved
- Suggested investigation steps
- Potential fixes

Bug description:
{bug_description}
```

#### ask

Pass the question directly with repo context:
```
Given the codebase in the current directory, answer this question:
{question}
```

### 3. Invoke the Agent CLI

#### Consensus (explicit OpenRouter panel)

Only when the user explicitly passed `--agent consensus`, read
[references/openrouter-consensus.md](references/openrouter-consensus.md) completely and follow it.
That reference owns local profile validation, immediate metered consent, safe prompt transfer,
bounded multi-model invocation, model-specific failure handling, and consensus presentation.

Pass the assembled prompt directly as a positional argument to ensure commands match
auto-approve permission patterns like `Bash(claude:*)`, `Bash(codex:*)`, and `Bash(gemini:*)`.

**Resolve the model flag** before building the command. Given the parsed `--model` value:

- `smart` (default) → omit the model flag entirely; let the CLI use its configured default.
- `fast` → use the CLI's configured cheap/fast alias if one exists in that runtime; otherwise
  omit the model flag and report that no explicit fast alias was available.
- anything else → treat as a literal model ID, pass through unchanged.

In the snippets below, `{model_flag}` expands to the relevant CLI's flag + value when a
model was resolved, and to an empty string when `smart` or an unavailable `fast` alias is in
effect.

#### For Claude

Pass the prompt via the `-p` flag and restrict the available tools to read-only ones:
```bash
claude -p "{assembled_prompt}" --tools "Read,Grep,Glob" {model_flag}
```

Where `{model_flag}` is `--model <id>` when resolved, or empty for `smart`.
Omitting the model flag lets the Claude CLI choose its configured default; this skill does
not implicitly select Opus, Fable, or Sonnet. The tool allowlist enforces read-only operation.

**Timeout**: Use the parsed timeout value (default 3 min, converted to milliseconds).

#### For Codex

For `review-pr` mode, prefer the built-in review command:
```bash
# PR review using codex's native review (--base and positional prompt are mutually exclusive)
codex review --base {base_branch} {model_flag}

# Or for uncommitted changes:
codex review --uncommitted {model_flag}
```

For all other modes, pass the prompt as a positional argument:
```bash
codex exec {model_flag} "{assembled_prompt}"
```

Where `{model_flag}` is `-m <id>` when resolved, or empty for `smart` (which lets
`~/.codex/config.toml` decide the model and reasoning effort).

**Timeout**: Use the parsed timeout value. Codex is slow on large prompts — consider `--timeout 5` or higher for PR reviews in large repos.

#### For Gemini

Pass the prompt via the `-p` flag:
```bash
gemini -p "{assembled_prompt}" --sandbox -o text {model_flag}
```

Where `{model_flag}` is `-m <id>` when resolved, or empty for `smart`.

The `--sandbox` flag prevents Gemini from modifying files. The `-o text` flag gives clean text output.

**Timeout**: Use the parsed timeout value (default 3 min, converted to milliseconds).

#### For All

Run all available subscription/OAuth-first agents in parallel (use parallel Bash tool calls). Present all results. `all` never includes OpenRouter; the explicit `consensus` path above is the only panel route.

### 5. Present Results

Format the response clearly:

```markdown
## Second Opinion ({agent_name})

{agent_response}

---
*Source: {agent_name} CLI, mode: {mode}*
```

If multiple agents were queried, present each under its own heading:

```markdown
## Claude Opinion

{claude_response}

## Codex Opinion

{codex_response}

## Gemini Opinion

{gemini_response}

## Key Differences

{brief comparison of where they agree/disagree}
```

After presenting the raw results, add your own assessment (see step 6).

### 6. Your Assessment

Critically review the external agent's findings against the actual codebase. For each finding, verify
whether it is correct by reading the relevant code — do not take the agent's claims at face value.

#### Single PR

```markdown
### My Assessment

| # | Finding | Verdict | Rationale |
|---|---------|---------|-----------|
| 1 | {short description} | Valid / Non-issue / Already handled | {one-line reason} |
| 2 | ... | ... | ... |

**Actionable items:** {list only the valid findings worth acting on, or "None."}
```

#### Batch (multiple PRs)

When reviewing several PRs in one session, present a summary table after all individual reviews:

```markdown
### Batch Summary

| PR | Title | Findings | Actionable |
|----|-------|----------|------------|
| #123 | feat: add caching | 4 | 1 — readCookie split bug |
| #124 | fix: session init | 3 | 0 |
| ... | ... | ... | ... |
```

Then list only the genuinely actionable items across all PRs, grouped by severity.

#### Follow-up

After the assessment, offer:
- "Want me to create beads for the actionable items?"
- Or, if nothing is actionable: "Nothing worth following up — want me to act on anything else?"

## Error Handling

- If a CLI is not installed or not authenticated, tell the user and suggest another available agent
- For `consensus`, follow the reference's profile check and per-model failure handling. Report every
  missing prerequisite without installing software, exposing a key, or making an API request; offer
  the existing subscription/OAuth-first routes instead.
- If a CLI times out (>3 min), report partial output if any and suggest trying another agent. A panel
  timeout/error remains a per-model error and is never retried or substituted automatically.
- If the prompt is too large, summarize the diff/context before sending; never silently truncate it.
- If both agents fail, report the errors and suggest the user try manually

## Rules

- Never let the external agent modify files — use read-only/sandbox modes
- Always restrict Claude to `--tools "Read,Grep,Glob"`, use `--sandbox` for Gemini, and use default (no write) permissions for Codex
- Do not send sensitive data (env vars, secrets, credentials) to external CLIs
- Present the external agent's response faithfully in step 5 — save your own judgement for step 6
- Make clear which agent provided which opinion
- For consensus, follow the reference's private prompt-file and immediate-consent protocol exactly.
  Never persist consent, use `consensus` in a loop, expand a profile during a run, or treat it as a
  replacement for regular independent review.
