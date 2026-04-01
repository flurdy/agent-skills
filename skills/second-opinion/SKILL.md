---
name: second-opinion
description: Query an alternative AI CLI (Claude, Codex, or Gemini) for a second opinion on plans, PRs, bugs, or code.
allowed-tools: "Read,Bash(claude:*),Bash(codex:*),Bash(gemini:*),Bash(git:*),Bash(gh:*),Grep,Glob,AskUserQuestion"
version: "1.0.0"
author: "flurdy"
---

# Second Opinion

Query Claude, Codex, or Gemini CLI for an independent review of plans, PRs, code, or bugs.

## When to Use

- You want a second opinion on a plan, architecture decision, or approach
- You want an independent PR review from another AI
- You want to cross-check a bug triage or root cause analysis
- You want to validate a proposed change before committing

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
/second-opinion ask "<question>" --agent all      # Query all agents in parallel
/second-opinion review-pr --timeout 5             # Allow 5 minutes (default: 3, max: 10)
```

## Requirements

- `claude` CLI installed and authenticated (part of Claude Code)
- `codex` CLI installed and authenticated (`codex login`)
- `gemini` CLI installed and authenticated
- `gh` CLI for PR operations

## Instructions

### 1. Parse Arguments

Extract from the arguments:
- **mode**: one of `review-pr`, `validate-plan`, `triage-bug`, `ask` (default: ask user)
- **target**: PR number, plan text, bug description, or freeform question
- **agent**: `claude`, `codex`, `gemini`, or `all` (default: `codex`)
- **timeout**: timeout in minutes (default: `3`, max: `10`)

Look for `--agent <name>` anywhere in the arguments. If not specified, default to `codex`.
Look for `--timeout <minutes>` anywhere in the arguments. If not specified, default to `3`.

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

Pass the assembled prompt directly as a positional argument to ensure commands match
auto-approve permission patterns like `Bash(claude:*)`, `Bash(codex:*)`, and `Bash(gemini:*)`.

#### For Claude

Pass the prompt via the `-p` flag:
```bash
claude -p "{assembled_prompt}" --no-input
```

The `--no-input` flag prevents Claude from asking interactive questions. Claude runs in read-only mode by default when using `-p`.

**Timeout**: Use the parsed timeout value (default 3 min, converted to milliseconds).

#### For Codex

For `review-pr` mode, prefer the built-in review command:
```bash
# PR review using codex's native review (--base and positional prompt are mutually exclusive)
codex review --base {base_branch}

# Or for uncommitted changes:
codex review --uncommitted
```

For all other modes, pass the prompt as a positional argument:
```bash
codex exec "{assembled_prompt}"
```

**Timeout**: Use the parsed timeout value. Codex is slow on large prompts — consider `--timeout 5` or higher for PR reviews in large repos.

#### For Gemini

Pass the prompt via the `-p` flag:
```bash
gemini -p "{assembled_prompt}" --sandbox -o text
```

The `--sandbox` flag prevents Gemini from modifying files. The `-o text` flag gives clean text output.

**Timeout**: Use the parsed timeout value (default 3 min, converted to milliseconds).

#### For All

Run all available agents in parallel (use parallel Bash tool calls). Present all results.

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

After presenting, offer: "Want me to act on any of these suggestions?"

## Error Handling

- If a CLI is not installed or not authenticated, tell the user and suggest another available agent
- If a CLI times out (>3 min), report partial output if any and suggest trying another agent
- If the prompt is too large, summarize the diff/context before sending
- If both agents fail, report the errors and suggest the user try manually

## Rules

- Never let the external agent modify files — use read-only/sandbox modes
- Always use `--no-input` for Claude, `--sandbox` for Gemini, and default (no write) permissions for Codex
- Do not send sensitive data (env vars, secrets, credentials) to external CLIs
- Present the external agent's response faithfully — do not editorialize or filter it
- Make clear which agent provided which opinion
- The temp file approach avoids shell injection from prompt content
