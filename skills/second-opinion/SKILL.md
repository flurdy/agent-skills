---
name: second-opinion
description: Query an independent peer or a configurable local/OpenRouter review panel, with distinct quorum and evidence-backed consensus interpretation policies.
allowed-tools: "Read,Write,Bash(claude:*),Bash(codex:*),Bash(gemini:*),Bash(git:*),Bash(gh:*),Bash(mktemp:*),Bash(chmod:*),Bash(rm:*),Bash(~/.agents/skills/second-opinion/scripts/review-panel.sh:*),Grep,Glob,AskUserQuestion"
model-tier: standard
model: sonnet
effort: high
version: "2.0.0"
author: "flurdy"
---

# Second Opinion

Query one independent CLI peer or a bounded named review panel for plans, PRs, code, or bugs.
`quorum` and `consensus` execute the same selected panel. Quorum means enough independent providers
returned; consensus is a later claim-level interpretation that is allowed only after quorum.
Agreement and vote count never establish correctness.

## Usage

```text
/second-opinion
/second-opinion review-pr 123
/second-opinion validate-plan "<plan>"
/second-opinion triage-bug "<description>"
/second-opinion ask "<question>"

# One independent route
/second-opinion ask "..." --agent peer       # explicit/default independent peer
/second-opinion ask "..." --agent claude
/second-opinion ask "..." --agent codex
/second-opinion ask "..." --agent gemini
/second-opinion ask "..." --agent codex --model <id>

# Policy-neutral named panels
/second-opinion review-pr --agent quorum                    # defaults to focused
/second-opinion validate-plan "..." --agent consensus       # defaults to extreme
/second-opinion review-pr --agent consensus --panel large
/second-opinion ask "..." --agent quorum --panel large \
  --route-model claude-fable=opus --route-effort claude-fable=max

# Temporary compatibility
/second-opinion review-pr --agent all   # deprecated alias: quorum --panel local-legacy
```

`--timeout <minutes>` defaults to 3 and is capped at 10.

## Requirements

- Single/local routes: the selected `claude`, `codex`, or `gemini` CLI installed and authenticated.
- Panel orchestration: `jq` plus `scripts/review-panel.sh`.
- OpenRouter subset only: `curl`, `OPENROUTER_API_KEY`, and a configured panel/profile in
  `~/.agents/second-opinion/config.json`.
- `gh` for PR context.

Read [references/review-panels.md](references/review-panels.md) when `quorum`, `consensus`, or the
compatibility alias `all` is selected. If the selected panel contains OpenRouter routes, also read
[references/openrouter-consensus.md](references/openrouter-consensus.md) completely before executing.
Model/effort precedence is in
[references/external-model-resolution.md](references/external-model-resolution.md).

## Model independence and cost

A second opinion should come from a different vendor than the model that produced the work:

- Claude session → Codex first, then Gemini.
- GPT/Codex session → Claude first, then Gemini.
- Other session → the best available independent Claude or Codex route.

`peer` is the explicit name for this selection and is also the no-`--agent` default. Direct
`claude`, `codex`, and `gemini` remain supported.

Prefer subscription/OAuth routes for one peer. Treat API-key/BYOK and unknown-cost direct routes as
metered and obtain current-run consent before invocation. A named panel does not infer billing from a
provider name. Its configured local routes are the approved local subset; every OpenRouter route is a
separately metered subset requiring fresh consent immediately before requests.

For a direct single agent only:

- no `--model` or `--model smart` → retain the CLI-native default;
- `--model fast` → use a verified CLI-native fast alias, otherwise retain and report the native
  default;
- `--model <id>` → pass the literal ID through.

For panels, generic `--model` is invalid. Use repeated `--route-model ID=VALUE` and
`--route-effort ID=VALUE`. OpenRouter identities cannot be overridden. Unsupported effort is rejected,
never translated.

## 1. Parse arguments

Extract:

- mode: `review-pr`, `validate-plan`, `triage-bug`, or `ask`;
- target: PR number, plan, bug description, or question;
- agent: `peer`, `claude`, `codex`, `gemini`, `quorum`, `consensus`, or deprecated `all`;
- panel: a local profile name;
- timeout: 1–10 minutes, default 3;
- direct model or repeated route-specific model/effort overrides.

Defaults and compatibility:

- no agent → `peer`;
- `quorum` with no panel → `focused`;
- `consensus` with no panel → `extreme`;
- `all` → warn once that it is deprecated, then use the reserved local-only built-in
  `quorum --panel local-legacy`;
- reject `--panel`, `--route-model`, or `--route-effort` for a direct single agent;
- reject generic `--model` for `quorum` or `consensus`.

If no mode is supplied, ask what to review. `consensus` must always be explicitly named; never infer
it from task risk, panel size, `all`, or an API key.

## 2. Gather and sanitize context

### review-pr

```bash
gh pr view {PR_NUMBER} --json title,body,additions,deletions,changedFiles,state,baseRefName,headRefName
gh pr diff {PR_NUMBER}
```

Without a number, use the current branch PR. Build a prompt covering correctness, security,
performance, maintainability, and missing edge/error handling, followed by PR metadata and the exact
diff.

### validate-plan

```bash
git ls-files | head -100
```

Ask for feasibility, completeness, dependencies, risks, and simpler alternatives, followed by the
plan.

### triage-bug

Ask for likely root causes, relevant components, investigation steps, falsification tests, and
potential fixes, followed by the bug description.

### ask

Pass the question with current-repository context.

For every mode, remove secrets, credentials, `.env` contents, private keys, and irrelevant personal
data. Never silently truncate oversized context; summarize before route selection and say so. Local CLI
routes are explicitly approved read-only repository reviewers and may inspect files in the current
repository, so use them only when that repository's readable contents are safe to share with those
providers. OpenRouter receives only the sanitized prompt bytes and no tools.

## 3. Execute one peer/direct agent

Resolve `peer` using the independence rule, then invoke exactly one route. Pass an assembled prompt
without allowing writes.

### Claude

```bash
claude -p "{assembled_prompt}" --tools "Read,Grep,Glob" {model_flag}
```

Use `--model <id>` only for an explicit resolved model.

### Codex

For a PR, prefer the native review command:

```bash
codex review --base {base_branch} {review_model_config}
```

`codex review` has no `--model` flag. For an explicit resolved model, expand
`{review_model_config}` to `-c 'model="<id>"'`; otherwise omit it and report the native default.
Do not claim an effective effort unless an explicit native Codex config override was supplied.

For other modes:

```bash
codex exec --sandbox read-only {exec_model_flag} "{assembled_prompt}"
```

For `codex exec`, `{exec_model_flag}` is `--model <id>` for an explicit resolved model and empty for
the native default.

### Gemini

```bash
gemini -p "{assembled_prompt}" --sandbox -o text {model_flag}
```

Apply the parsed timeout. If the route fails or times out, preserve the error and offer another
independent direct route; never retry or substitute silently.

## 4. Execute a named panel

Use the same exact sanitized prompt for every route. Create a private file with `mktemp`, set mode
`600`, and write the prompt with `Write`. Do not put panel prompt text in shell argv.

### 4.1 Check and bind

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh check \
  --panel {panel_name} \
  --prompt-file {prompt_file} \
  {repeated_route_overrides}
```

Retain and display:

- ordered route IDs, kinds, providers, roles, availability, effective model/effort, and provenance;
- configured quorum and limits;
- `panelSha256`, `openrouterSha256`, and `promptSha256`.

If profile validation fails, stop before any route invocation. Missing route prerequisites degrade the
panel; they do not authorize substitution.

### 4.2 Run the local subset

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh run-local \
  --panel {panel_name} \
  --prompt-file {prompt_file} \
  --panel-sha256 {panelSha256} \
  --prompt-sha256 {promptSha256} \
  --timeout {timeout_seconds} \
  {repeated_route_overrides}
```

Save the returned JSON array to a mode-private result file. The coordinator invokes each configured
local route at most once, in bounded parallel batches, with read-only tools/sandboxing and prompt
stdin. Preserve missing CLIs, timeouts, and failures.

### 4.3 Decide the OpenRouter subset

If `openrouter.requestCount == 0`, skip this step.

If prerequisites are unavailable, make no request and allow evaluation to report those routes as
missing/unavailable. Otherwise, immediately before requests use one `AskUserQuestion` that discloses
only the OpenRouter subset: exact routes/models/vendors, request count, concurrency, prompt cap,
output-token cap, timeout, variable pricing, and that OpenRouter credits will be consumed.

- **Approve** → invoke `run-openrouter --confirmed` with all three digests and the same profile,
  prompt, timeout, and overrides.
- **Decline/ambiguous/abandoned** → invoke `decline-openrouter` with all three digests. It generates
  explicit declined results and makes no network request.

Consent applies once and is never persisted. A digest mismatch requires a new check and fresh
consent. Never retry, substitute, expand, or run a metered subset unattended.

### 4.4 Evaluate mechanical quorum

Write the `check`, local-result, and OpenRouter-result JSON to private files, then run:

```bash
~/.agents/skills/second-opinion/scripts/review-panel.sh evaluate \
  --policy {quorum|consensus} \
  --check-file {check_file} \
  --results-file {local_results_file} \
  --results-file {openrouter_results_file}
```

Omit a result file only when that subset did not run and produced no results. The evaluator preserves
panel order, counts unique successful providers, reports unavailable routes and same-provider
corroboration, and sets `consensusEligible`. It deliberately does not compare natural-language claims.
Remove all private prompt/result files after evaluation, success or failure.

## 5. Present panel results

First show every route faithfully:

```markdown
## Review Panel: `{panel}` — {quorum|consensus}

| Route | Kind | Provider | Role | Model / effort | Status |
|---|---|---|---|---|---|
| ... |

**Quorum:** {successful unique providers}/{required} — met / not met
```

Then include each successful response under its route heading and every error/decline/timeout under
Unavailable routes.

### Quorum policy

When quorum is met, present findings by route/provider without requiring agreement. When not met,
state that quorum failed and identify unavailable providers. Do not relabel repeated claims as
consensus.

### Consensus policy

If `consensusEligible` is false, state **no consensus assessment was made**. Preserve returned
opinions but do not synthesize agreement.

If eligible, compare claims and report all five categories:

1. **Evidence-backed agreements** — independently supported claims, not repeated prompt premises.
2. **Disagreements / uncertainty** — conflicting conclusions and unresolved evidence.
3. **Shared assumptions** — repeated claims without independent support.
4. **Same-provider corroboration** — explicitly separate from independent-provider agreement.
5. **Unavailable routes** — missing, declined, failed, and timed-out perspectives.

Never convert a majority into correctness.

## 6. Repository-grounded assessment

Critically verify every material external claim against actual repository evidence. Present a concise
assessment table:

```markdown
### My Assessment

| # | Finding | Verdict | Evidence |
|---|---|---|---|
| 1 | ... | Valid / Non-issue / Already handled / Uncertain | file/path:line or reason |
```

List only genuinely actionable items. A unique, well-evidenced concern may outweigh repeated weak
claims; repeated unsupported claims remain invalid.

## Error handling and rules

- Never let any route modify files.
- Never send secrets or credentials to a route.
- Never expose OpenRouter credentials or place the bearer token in argv.
- Never give OpenRouter routes tools or repository access.
- Never retry/substitute a failed route or silently change a configured panel.
- Always report effective route provenance; `native-default` is honest when the runtime does not
  reveal a concrete setting.
- Preserve external responses faithfully before adding your own assessment.
- A partial panel is partial coverage, not a complete panel.
