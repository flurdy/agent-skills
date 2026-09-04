---
name: watch-rollout
description: Choose and launch the appropriate rollout watcher. Prompts between implemented deployment stacks unless an explicit selector is supplied, then delegates without weakening stack-specific safety.
allowed-tools: "AskUserQuestion,Skill(watch-actions-rollout),Skill(watch-flux-rollout)"
model-tier: economy
model: haiku
effort: medium
version: "1.0.0"
author: "flurdy"
---

# Choose Rollout Watcher

Select the deployment stack, then delegate the entire rollout watch to its specialist skill. This
router does not inspect deployments, run commands, schedule polling, or combine stack-specific
safety rules.

## Usage

```text
/watch-rollout                         # ask which implemented stack to watch
/watch-rollout actions [arguments]     # GitHub Actions
/watch-rollout github [arguments]      # alias for actions
/watch-rollout flux [arguments]        # CircleCI + FluxCD
```

Legacy target forms remain valid. For example, `/watch-rollout 6790`, `/watch-rollout <sha>`, and
`/watch-rollout --run 28440286944` ask for the stack and then pass the original arguments to the
selected implementation.

## Route selection

Recognize an explicit first argument as follows:

| Selector | Delegate |
|---|---|
| `actions`, `github`, `github-actions` | `watch-actions-rollout` |
| `flux`, `circleci-flux` | `watch-flux-rollout` |

When a selector matches, remove only that first argument. Forward all remaining arguments unchanged.
Invoke the mapped skill immediately without prompting.

Always ask when no explicit stack selector is supplied. Use `AskUserQuestion` with exactly these
implemented choices:

- **GitHub Actions** — invoke `watch-actions-rollout` with every original argument.
- **CircleCI + FluxCD** — invoke `watch-flux-rollout` with every original argument.

Do not infer a stack from repository files or remember a previous answer. Do not list planned or
unimplemented providers. Cloudflare Workers/Pages, Google Cloud Build, and other stacks may be added
later as specialist skills plus one explicit row and prompt option here.

## Delegation contract

Invoke exactly one specialist through `Skill` and stop. The specialist owns argument validation,
revision identity, configuration, confirmation, polling, smoke tests, terminal behavior, and error
reporting. Never reproduce or relax those rules in this router.

Direct specialist invocation remains supported:

```text
/watch-actions-rollout [arguments]
/watch-flux-rollout [arguments]
```
