# Agent Skills

AI agent skills and sub-agents shared across clients and machines. These are the
common building blocks that get assembled into active skill sets for Claude,
Codex, and other AI agents.

Two kinds of units are managed:

- __Skills__ — folders with a `SKILL.md`, linked into the portable `~/.agents/skills/` root. Pi and Codex discover it natively; Claude Code receives per-skill aliases in `~/.claude/skills/`.
- __Agents__ — single `*.md` files defining Claude Code sub-agents, linked into `~/.claude/agents/`. Codex targets skip this repository's Claude-style Markdown agent layer; installed Codex versions may provide native multi-agent tools.

Pi prompt templates are also kept in `prompts/`. They are not skills or agents, so the assembler does not install them; configure Pi to load that directory directly.

## Using the skills

1. Clone this repo.

   `git clone https://github.com/flurdy/agent-skills.git`

2. Preview and apply the shared installation from the `agent-skills/` folder.

   ```bash
   make dry-run
   make apply
   ```

3. Verify the installation with `make doctor`:

   - Canonical skills: `~/.agents/skills`
   - Claude skill aliases: `~/.claude/skills`
   - Claude agents: `~/.claude/agents`

Pi and Codex discover `~/.agents/skills` natively. `make apply-codex` remains as a compatibility alias that applies the same shared skill root without touching Claude agents.

## Available Skills

See [skills/README.md](skills/README.md) for the full list of available skills.

## Pi prompt templates

Pi expands each Markdown file in [`prompts/`](prompts/) as a slash command using its filename: for example, `about.md` becomes `/about`. Merge this property into Pi's existing global settings:

```json
{
  "prompts": ["~/Code/flurdy/agent-skills/shared/prompts"]
}
```

Alternatively, symlink individual templates into Pi's default prompt directory:

```bash
mkdir -p ~/.pi/agent/prompts
ln -sfn "$PWD/prompts/about.md" ~/.pi/agent/prompts/about.md
ln -sfn "$PWD/prompts/squash-msg.md" ~/.pi/agent/prompts/squash-msg.md
ln -sfn "$PWD/prompts/trim-comments.md" ~/.pi/agent/prompts/trim-comments.md
```

Use one loading method, not both, to avoid duplicate command names. Keep either choice local to the user configuration; it is intentionally not a project setting that would load prompts automatically for collaborators. Restart Pi or run `/reload` after adding or changing templates.

## Model routing

These skills are shared across Claude Code, pi.dev, and Codex. Skill frontmatter
declares the portable capability tier and reasoning effort a workflow needs, while
exact providers, model IDs, fallback order, and spend controls stay in runtime-local
configuration. See [MODEL_ROUTING.md](MODEL_ROUTING.md) for the shared policy.

The portable policy lives in this repository. Pi can enforce the metadata through
the optional [model-tier router](https://github.com/flurdy/ai-tools/tree/main/pi/model-tier-router)
maintained in [flurdy/ai-tools](https://github.com/flurdy/ai-tools); Claude Code and
Codex use their own runtime configuration and capabilities.

## Layout

- `skills/`: each skill lives in its own folder with a `SKILL.md`
- `agents/`: each sub-agent is a single `*.md` file with frontmatter
- `prompts/`: Pi prompt templates; each top-level `*.md` file becomes a `/name` command
- `docs/`: repository documentation; historical and implementation plans live in [`docs/plans/`](docs/plans/)
- Optional: `assets/`, `scripts/`, or `references/` inside a skill folder if needed

```plaintext
agent-skills/
  skills/
    common-skill/
      SKILL.md
  agents/
    my-agent.md
  prompts/
    about.md
  docs/
    plans/
      implementation-plan.md
  assemble.sh
  Makefile
```

## Private skills 

If you have machine- or client-specific skills or overrides, you can create a
__sibling__ repo named `agent-skills-private/` alongside this `agent-skills/` repo.

(You are free to name it something else, but you'll need to set the `PRIVATE_REPO` environment variable, see below).

This `agent-skills-private/` repo is optional, and can be kept private and secure. With both repos the layout is this:

```plaintext
agent-skills/
  skills/
    common-skill/
      SKILL.md
  agents/
    common-agent.md
  assemble.sh
  Makefile
agent-skills-private/
  skills/
    my-private-skill/
      SKILL.md
  agents/
    my-private-agent.md
  clients/
    my-client/
      skills/
         my-private-skill/
           SKILL.md
      agents/
         my-client-agent.md
  machines/
    my-machine/
      skills/
        my-machine-skill/
          SKILL.md
      agents/
        my-machine-agent.md
  profiles/
    my-machine-profile.env
```

You can then specify machine or clients specific skills to use:

`make apply MACHINE=my-machine CLIENTS="my-client my-other-client"`

Or instead configure `private/profiles/my-machine-profile.env` with:

```properties
MACHINE=my-machine
CLIENTS="my-client my-other-client"
```

`make apply PROFILE=my-machine-profile` to do the same

### Layering order

Skills and agents use the same layering. If a unit exists in multiple layers, later layers override earlier ones:

1. Shared: `agent-skills/{skills,agents}/`
2. Private shared: `agent-skills-private/{skills,agents}/`
3. Private machine: `agent-skills-private/machines/<machine>/{skills,agents}/`
4. Private client(s): `agent-skills-private/clients/<client>/{skills,agents}/`

## Common vars

Set these as environment variables, or accept the defaults.

Path to shared repo (this repo):

- `SHARED_REPO=/path/to/agent-skills`

Path to optional private repo:

- `PRIVATE_REPO=/path/to/agent-skills-private`

Path to the canonical skills directory:

- `SKILLS_DIR=$HOME/.agents/skills`

Compatibility and migration directories:

- `CLAUDE_SKILLS_DIR=$HOME/.claude/skills` — per-skill aliases because Claude Code does not natively scan the portable root
- `LEGACY_CODEX_SKILLS_DIR=$HOME/.codex/skills` — old managed links are removed during apply/clean; unmanaged entries are preserved

Path to agents directory (Claude only):

- `AGENTS_DIR=$HOME/.claude/agents`

To skip the agents layer (e.g. for Codex targets), set `SKIP_AGENTS=1`.

There is an example in `.env.example` you can use,
and an example `.envrc.example` file if you use [direnv](https://direnv.net/).

## Adding a new skill

1. Create a folder under `skills/` with a descriptive kebab-case name
2. Add a `SKILL.md` with frontmatter and instructions (see below)
3. Declare a semantic `model-tier` plus `effort`; see [MODEL_ROUTING.md](MODEL_ROUTING.md). An optional floating `model:` alias is a Claude Code-only hint, not portable routing metadata
4. Add the skill to the alphabetical description table in [`skills/README.md`](skills/README.md)
5. Keep it focused and general-purpose
6. Run `make validate-skills` to check metadata, catalog parity, and local references
7. Run `make apply` and verify it appears in `~/.agents/skills` and through its Claude alias

When changing the validator itself, run `make test-validate-skills` for its fixture suite.

## Adding a new agent

Sub-agents are single markdown files with frontmatter — see the [Claude Code sub-agents docs](https://docs.claude.com/en/docs/claude-code/sub-agents) for the schema.

1. Create `agents/<name>.md` with YAML frontmatter (`name`, `description`, `model-tier`, `effort`, and optional `tools`/`color`) and the agent's system prompt below. Shared agents omit `model:` because Pi may honor that field directly
2. Keep agents general-purpose; put machine- or client-specific ones in the private repo under `agents/`, `machines/<m>/agents/`, or `clients/<c>/agents/`
3. Run `make apply` and confirm the symlink in `~/.claude/agents/`

Agents are not applied for Codex (`make apply-codex` sets `SKIP_AGENTS=1`).

### SKILL.md format

Every skill needs a `SKILL.md` with YAML frontmatter. `model-tier` and `effort` are portable capability metadata; runners that do not understand them should ignore them. Exact providers, model IDs, billing classification, and confirmation policy remain runtime-local:

```markdown
---
name: my-skill
description: One-line description shown in skill listings
model-tier: standard
effort: high
version: "1.0.0"
author: "yourname"
---

# My Skill

Instructions for the agent go here.
```

### Helper scripts and `allowed-tools`

If your skill runs shell commands (API calls, `gh` commands, build tools, etc.), wrap them in scripts under a `scripts/` subfolder. This lets you grant auto-approval for specific commands via the `allowed-tools` frontmatter field, so the user isn't prompted on every invocation:

```plaintext
skills/
  my-skill/
    SKILL.md
    scripts/
      fetch-data.sh
```

```yaml
---
name: my-skill
description: Fetch and display data from the API
allowed-tools: "Bash(~/.agents/skills/my-skill/scripts/fetch-data.sh:*)"
---
```

Without `allowed-tools`, the user will be prompted to approve each tool call. Multiple patterns are comma-separated. Glob patterns match against the full command string.

### Skill folder structure

```plaintext
skills/
  my-skill/
    SKILL.md              # Required — instructions and frontmatter
    scripts/              # Optional — shell scripts for auto-approval
      fetch-data.sh
    templates/            # Optional — text templates the skill reads at runtime
      body.md
```

## Coexisting with existing skills and agents

This tool is designed to coexist with skills and agents you already have:

- __Apply__ creates managed links in `~/.agents/skills`, per-skill Claude aliases, and Claude agent links.
- __Clean__ removes only repository-managed links and compatibility aliases, leaving user content untouched.
- __Collision handling__: apply preflights every destination before mutation. An unmanaged entry with the same name causes a safe failure with the previous installation intact.
- __Root safety__: destination roots must be real directories. The assembler refuses to traverse or replace a user-managed root symlink.

After `make apply`, the portable and Claude roots look like this:

```plaintext
~/.agents/skills/
  create-pr/       -> /path/to/agent-skills/skills/create-pr
  jira-ticket/     -> /path/to/agent-skills/skills/jira-ticket
  my-custom-skill/                                            # preserved

~/.claude/skills/
  create-pr/       -> ~/.agents/skills/create-pr              # managed alias
  jira-ticket/     -> ~/.agents/skills/jira-ticket            # managed alias
  claude-only/                                               # preserved
```

### Migrating existing installations

`make dry-run` shows the one-time migration. `make apply` moves repository-managed skill links into `~/.agents/skills`, replaces old managed Claude links with aliases, and removes old managed links from `~/.codex/skills`. Unmanaged files, directories, and third-party symlinks remain in place.

Pi already discovers `~/.agents/skills`. After `make doctor` confirms the canonical installation, remove `"~/.claude/skills"` from Pi's user-level `skills` array to avoid duplicate discovery, then restart Pi or run `/reload`. Keep unrelated configured skill paths.

To roll back, check out the previous repository version and run its separate `make apply` and `make apply-codex` targets. Do not replace an existing skills root with a directory symlink unless you have manually reconciled all user-owned content.

### Cleaning up

`make clean` removes managed canonical skill links, Claude aliases, legacy managed Codex links, and managed Claude agents. User-owned entries are preserved.

## Bugs and pull requests

- Please report bugs and issues at [github.com/flurdy/agent-skills/issues](https://github.com/flurdy/agent-skills/issues).
- Pull requests are welcome at [github.com/flurdy/agent-skills/pulls](https://github.com/flurdy/agent-skills/pulls).


## Creator

Created by flurdy (https://flurdy.com).

## License

MIT License. See LICENSE file.
