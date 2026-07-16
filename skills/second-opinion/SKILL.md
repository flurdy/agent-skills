---
name: second-opinion
description: Query alternative AI CLIs for a second opinion, or run an explicitly approved bounded cross-vendor consensus panel for high-stakes reviews.
allowed-tools: "Read,Bash(claude:*),Bash(codex:*),Bash(gemini:*),Bash(git:*),Bash(gh:*),Bash(mktemp:*),Bash(chmod:*),Bash(cat:*),Bash(rm:*),Bash(~/.claude/skills/second-opinion/scripts/openrouter-panel.sh:*),Grep,Glob,AskUserQuestion"
model-tier: standard-workflow
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-before-metered-panel
model: sonnet
model-second-opinion-tier: independent-reasoning
effort: medium
version: "1.3.0"
author: "flurdy"
---

# Second Opinion

Query Claude, Codex, or Gemini CLI for an independent review of plans, PRs, code, or bugs. For unusually high-stakes decisions, an explicit `consensus` mode adds two configured OpenRouter models under strict cost and fan-out caps.

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
/second-opinion validate-plan "<plan>" --agent consensus  # Explicit bounded cross-vendor panel
/second-opinion review-pr --timeout 5             # Allow 5 minutes (default: 3, max: 10)
/second-opinion ask "..." --model fast            # Use the fast tier instead of smart
/second-opinion ask "..." --model gemini-3-pro    # Pass an explicit model ID through
```

## Requirements

- `claude` CLI installed and authenticated (part of Claude Code)
- `codex` CLI installed and authenticated (`codex login`)
- `gemini` CLI installed and authenticated
- `gh` CLI for PR operations
- Consensus mode only: `curl`, `jq`, `OPENROUTER_API_KEY`, and two model IDs configured as `OPENROUTER_PANEL_QWEN_MODEL` (`qwen/...`) and `OPENROUTER_PANEL_XAI_MODEL` (`x-ai/...`)

OpenRouter's official `@openrouter/cli` is **not** a chat-completions CLI: v1 provides SDK devtools and a Claude Code statusline. It is optional and is not used here. Consensus mode calls OpenRouter's OpenAI-compatible chat-completions API through the bundled `scripts/openrouter-panel.sh` helper.

## Model Selection and Cost

This skill declares `model-second-opinion-tier: independent-reasoning`. Exact model IDs belong in
the invoked CLI's configuration where possible, not in this shared skill. By default, omit
model flags and let each CLI use its configured default.

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
  API key. It is a separately named two-model panel and must ask for fresh consent immediately
  before the first API request. Do not store that consent.

### Consensus panel contract

`--agent consensus` is an exceptional, **opt-in** escalation for decisions that merit two additional
vendor perspectives after the regular independent pass. It must not be used by default or in an
unattended loop. The panel is exactly these two roles, loaded from the environment rather than
hard-coded model IDs:

| Role | Required ID prefix | Purpose |
|---|---|---|
| Qwen reasoning | `qwen/` | Cost-conscious independent reasoning |
| xAI reasoning | `x-ai/` | Distinct frontier/vendor perspective |

The helper rejects absent, duplicate, or wrong-vendor IDs. It makes exactly two requests, at most
two concurrently; caps the assembled prompt at **65,536 bytes**, each response at **2,000 tokens**,
and each request timeout at **10 minutes** (default: 3). It sends no tools, does not install software,
and puts the bearer token in a private temporary header file rather than argv or output. Do not claim
an exact price: pricing, routing, and usage can change. Before consent, disclose the two configured
model IDs, request count, caps, timeout, and that this consumes OpenRouter credits.

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
- **model**: `smart` (default), `fast`, or an explicit model ID — see Model Selection and Cost

Look for `--agent <name>` anywhere in the arguments. If not specified, apply the independence
rule from Model Selection and Cost: `codex` in a Claude session, `claude` in a GPT session.
Look for `--timeout <minutes>` anywhere in the arguments. If not specified, default to `3`.
Look for `--model <value>` anywhere in the arguments. If not specified, default to `smart`.

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

Do this **only** when the user passed `--agent consensus`:

1. Keep the standard assembled prompt, but remove secrets, credentials, `.env` content, and any
   sensitive data. If it exceeds 65,536 bytes, create a focused summary before proceeding; never
   silently truncate a diff or plan.
2. Check prerequisites without a network request. The official `openrouter` executable is irrelevant
   to this flow; use the helper and report its structured status:
   ```bash
   ~/.claude/skills/second-opinion/scripts/openrouter-panel.sh check
   ```
   If `curl`/`jq`, `OPENROUTER_API_KEY`, or either configured model ID is absent, say which item is
   unavailable. Do not install the CLI, request a key in chat, print environment values, or fall
   back to an OpenRouter request. Offer `--agent all` or a configured single CLI instead.
3. If prerequisites are present, use one `AskUserQuestion` immediately before the call. State the
   two **model IDs** returned by `check`, two parallel OpenRouter API requests, the 65,536-byte input
   cap, 2,000-token/model output cap, the selected timeout, and that usage is metered against the
   user's OpenRouter credits. Options: **Run metered panel (recommended only when warranted)** and
   **Keep subscription-only review**. A negative/abandoned answer ends the panel with no request.
4. After affirmative consent, write the exact sanitized prompt to a mode-600 temporary file, then
   invoke the helper. Do not interpolate the prompt into a shell command:
   ```bash
   prompt_file=$(mktemp)
   chmod 600 "$prompt_file"
   # Write the assembled sanitized prompt verbatim to "$prompt_file".
   ~/.claude/skills/second-opinion/scripts/openrouter-panel.sh run \
     --confirmed --prompt-file "$prompt_file" --timeout {timeout_seconds}
   rm -f "$prompt_file"
   ```
   Convert the parsed timeout minutes to seconds (default 180; maximum 600). The helper is bounded
   to its two configured models and returns one success/error object per model. A timeout, bad model,
   rate limit, or API error is a model-specific failure: show it and continue with any successful
   result; never retry automatically or substitute another model.
5. Continue with the consensus presentation in step 5 and the repository-grounded assessment in
   step 6. The panel adds evidence; it does not establish correctness by vote.

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

#### Consensus panel results

For `--agent consensus`, preserve the helper's per-model success/error status and do not hide a
failed model. Label results with the configured **model ID** and vendor; usage fields are telemetry,
not a reliable pre-run price estimate.

```markdown
## Extreme Consensus Panel

| Role | Model | Status | Result |
|---|---|---|---|
| Qwen reasoning | `{qwen_model_id}` | ok / error | concise response or error |
| xAI reasoning | `{xai_model_id}` | ok / error | concise response or error |

### Agreements
- {only points supported by at least two successful panel responses; otherwise "No confirmed agreement."}

### Disagreements / uncertainty
- {materially conflicting claims, unsupported assumptions, and failed/missing responses}

*Sources: OpenRouter chat-completions API; two explicitly user-approved, metered requests; mode: {mode}.*
```

This is a comparison, not a vote: panel agreement does not make a finding true, and a single
response must be treated as an uncorroborated suggestion.

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
- For `consensus`, run the helper's `check` command first. Report every missing prerequisite without
  installing the OpenRouter CLI, exposing a key, or making an API request; offer the existing
  subscription/OAuth-first routes instead.
- If a CLI times out (>3 min), report partial output if any and suggest trying another agent. A panel
  timeout/error remains a per-model error and is never retried automatically.
- If the prompt is too large, summarize the diff/context before sending; never silently truncate it.
- If both agents fail, report the errors and suggest the user try manually

## Rules

- Never let the external agent modify files — use read-only/sandbox modes
- Always restrict Claude to `--tools "Read,Grep,Glob"`, use `--sandbox` for Gemini, and use default (no write) permissions for Codex
- Do not send sensitive data (env vars, secrets, credentials) to external CLIs
- Present the external agent's response faithfully in step 5 — save your own judgement for step 6
- Make clear which agent provided which opinion
- Use a private temporary prompt file for consensus mode; it avoids shell injection from prompt content. Remove it after the request, including on failure.
- Never make an OpenRouter request without an explicit, immediately preceding, per-run affirmative
  answer. Never persist consent, use `consensus` in a loop, expand its two-model panel, or treat it
  as a replacement for the regular independent review.
