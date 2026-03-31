---
name: second-opinion
description: Query an alternative AI CLI (Codex or Gemini) for a second opinion on plans, PRs, bugs, or code.
allowed-tools: "Read,Bash(codex:*),Bash(gemini:*),Bash(git:*),Bash(gh:*),Bash(cat:*),Bash(mktemp:*),Bash(rm:*),Grep,Glob,AskUserQuestion"
version: "1.0.0"
author: "flurdy"
---

# Second Opinion

Query Codex or Gemini CLI for an independent review of plans, PRs, code, or bugs.

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
/second-opinion ask "<question>" --agent codex   # Force a specific agent
/second-opinion ask "<question>" --agent gemini
/second-opinion ask "<question>" --agent both     # Query both in parallel
```

## Requirements

- `codex` CLI installed and authenticated (`codex login`)
- `gemini` CLI installed and authenticated
- `gh` CLI for PR operations

## Instructions

### 1. Parse Arguments

Extract from the arguments:
- **mode**: one of `review-pr`, `validate-plan`, `triage-bug`, `ask` (default: ask user)
- **target**: PR number, plan text, bug description, or freeform question
- **agent**: `codex`, `gemini`, or `both` (default: `codex`)

Look for `--agent <name>` anywhere in the arguments. If not specified, default to `codex`.

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

Write the gathered prompt to a temp file to avoid shell quoting issues:

```bash
PROMPT_FILE=$(mktemp /tmp/second-opinion-XXXXXX.txt)
cat <<'PROMPT_EOF' > "$PROMPT_FILE"
{assembled_prompt}
PROMPT_EOF
```

#### For Codex

For `review-pr` mode, prefer the built-in review command:
```bash
# PR review using codex's native review (--base and positional prompt are mutually exclusive)
codex review --base {base_branch}

# Or for uncommitted changes:
codex review --uncommitted
```

For all other modes:
```bash
codex exec "$(cat "$PROMPT_FILE")"
```

**Timeout**: Set a 3-minute timeout. Codex can be slow on large prompts.

#### For Gemini

```bash
gemini -p "$(cat "$PROMPT_FILE")" --sandbox -o text
```

The `--sandbox` flag prevents Gemini from modifying files. The `-o text` flag gives clean text output.

**Timeout**: Set a 3-minute timeout.

#### For Both

Run both agents in parallel (use parallel Bash tool calls). Present both results.

### 4. Clean Up

```bash
rm -f "$PROMPT_FILE"
```

### 5. Present Results

Format the response clearly:

```markdown
## Second Opinion ({agent_name})

{agent_response}

---
*Source: {agent_name} CLI, mode: {mode}*
```

If both agents were queried:

```markdown
## Codex Opinion

{codex_response}

## Gemini Opinion

{gemini_response}

## Key Differences

{brief comparison of where they agree/disagree}
```

After presenting, offer: "Want me to act on any of these suggestions?"

## Error Handling

- If a CLI is not installed or not authenticated, tell the user and suggest the other agent
- If a CLI times out (>3 min), report partial output if any and suggest trying the other agent
- If the prompt is too large, summarize the diff/context before sending
- If both agents fail, report the errors and suggest the user try manually

## Rules

- Never let the external agent modify files — use read-only/sandbox modes
- Always use `--sandbox` for Gemini and default (no write) permissions for Codex
- Do not send sensitive data (env vars, secrets, credentials) to external CLIs
- Present the external agent's response faithfully — do not editorialize or filter it
- Make clear which agent provided which opinion
- The temp file approach avoids shell injection from prompt content
