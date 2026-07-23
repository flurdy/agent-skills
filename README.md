# Agent Skills

Portable AI-agent workflows for [Pi](https://pi.dev), Claude Code, and Codex.
This repository keeps reusable skills, Claude-style sub-agents, and shared prompt
templates in one source so workflows can be authored once and used across clients.

## What you get

- **Skills** — focused workflows stored as `skills/<name>/SKILL.md` and installed
  into the portable `~/.agents/skills/` root.
- **Agents** — Claude-style sub-agent definitions stored in `agents/` and installed
  into `~/.claude/agents/`.
- **Prompt templates** — shared Pi and Claude Code slash commands stored in
  `prompts/` and configured manually per client.

Browse the [skills catalog](skills/README.md) for the complete list.

## Quick start

```bash
git clone https://github.com/flurdy/agent-skills.git
cd agent-skills
make dry-run   # preview managed symlink changes
make apply     # install skills, Claude aliases, and Claude agents
make doctor    # verify the installation
```

The installer manages individual symlinks rather than replacing destination
roots, so unrelated user-owned skills and agents remain untouched.

## Client support

| Client | Skills | Agents | Prompt templates |
|---|---|---|---|
| Pi | Discovers `~/.agents/skills/` | Not managed by this repository | Manual configuration |
| Codex | Discovers `~/.agents/skills/` | Uses Codex-native agent support | Not installed; custom prompts are deprecated |
| Claude Code | Managed aliases in `~/.claude/skills/` | Managed links in `~/.claude/agents/` | Manual configuration |

`make apply-codex` remains as a compatibility alias for applying the shared skill
root without the Claude-style agent layer.

## How it works

The assembler resolves shared and optional private layers, preflights collisions,
and creates managed symlinks in each client location. Later layers can override
units with the same name without copying shared content.

```text
agent-skills/
  skills/<name>/SKILL.md
  agents/<name>.md
  prompts/<name>.md
  docs/
  assemble.sh
  Makefile
```

Detailed destination variables, private layers, migration behavior, and cleanup
rules live in the [installation and configuration guide](docs/installation.md).

## Model routing

Shared skills declare portable capability and reasoning requirements in frontmatter:

```yaml
model-tier: standard
effort: medium
```

The supported tiers are `economy`, `standard`, and `premium`; reasoning effort is
`low`, `medium`, `high`, or `xhigh`. These values describe what a workflow needs,
not a fixed provider or model. Exact model IDs, fallback order, billing
classification, and spend controls remain runtime-local.

See [MODEL_ROUTING.md](MODEL_ROUTING.md) for the policy. Pi can optionally enforce
this metadata with the
[model-tier router](https://github.com/flurdy/ai-tools/tree/main/pi/model-tier-router)
from [flurdy/ai-tools](https://github.com/flurdy/ai-tools); Claude Code and Codex
use their own runtime configuration and capabilities.

## Prompt templates

The shared templates currently provide:

- `/about <id-or-name>`
- `/squash-msg [PR-number]`
- `/trim-comments [file-or-PR]`

They use `$ARGUMENTS`, which Pi and Claude Code both expand. Templates are not
installed by `make apply`; follow the
[prompt-template setup](docs/installation.md#prompt-templates) for either client.
The commands provide instructions only: `/squash-msg` drafts a message for
approval, and none performs Git operations itself.

## Optional private overlays

A sibling `agent-skills-private/` repository can add private shared units plus
machine-, client-, and profile-specific overrides. The resolved order is shared →
private → machine → clients. The shared repository remains usable without any
private repository.

See [Private overlays](docs/installation.md#private-overlays) for the directory
layout and commands.

## Documentation

- [Skills catalog](skills/README.md) — available workflows and descriptions
- [Installation and configuration](docs/installation.md) — destinations, prompts,
  private layers, migrations, and cleanup
- [Contributing](CONTRIBUTING.md) — authoring skills and agents, metadata,
  permissions, validation, and tests
- [Model routing](MODEL_ROUTING.md) — portable tier and effort policy
- [Documentation index](docs/README.md) — evaluations and historical plans

## Bugs and pull requests

- Report issues at [github.com/flurdy/agent-skills/issues](https://github.com/flurdy/agent-skills/issues).
- Pull requests are welcome at [github.com/flurdy/agent-skills/pulls](https://github.com/flurdy/agent-skills/pulls).

## Creator

Created by [flurdy](https://flurdy.com).

## License

MIT License. See [LICENSE](LICENSE).
