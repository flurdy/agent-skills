# Agent Skills

AI agent skills and sub-agents shared across clients and machines. These are the
common building blocks that get assembled into active skill sets for Claude,
Codex, and other AI agents.

Two kinds of units are managed:

- __Skills__ — folders with a `SKILL.md`, linked into `~/.claude/skills/` (and `~/.codex/skills/` for Codex).
- __Agents__ — single `*.md` files defining Claude Code sub-agents, linked into `~/.claude/agents/`. Codex has no sub-agent concept, so agents are skipped for Codex targets.

## Using the skills

1. Clone this repo.

   `git clone https://github.com/flurdy/agent-skills.git`

2. Apply the changes from the `agent-skills/` folder.

   `make apply`

   For Codex, use:

   `make apply-codex`

3. Verify units are in your active directories:

   - Claude skills: `~/.claude/skills`
   - Claude agents: `~/.claude/agents` (skipped for Codex)
   - Codex skills:  `~/.codex/skills`

Units are symlinked directly into their active directories, coexisting with any skills or agents you already have there.

## Available Skills

See [skills/README.md](skills/README.md) for the full list of available skills.

## Layout

- `skills/`: each skill lives in its own folder with a `SKILL.md`
- `agents/`: each sub-agent is a single `*.md` file with frontmatter
- Optional: `assets/`, `scripts/`, or `references/` inside a skill folder if needed

```plaintext
agent-skills/
  skills/
    common-skill/
      SKILL.md
  agents/
    my-agent.md
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

Path to skills directory:

- Claude: `SKILLS_DIR=$HOME/.claude/skills`
- Codex: `SKILLS_DIR=$HOME/.codex/skills`

Path to agents directory (Claude only):

- `AGENTS_DIR=$HOME/.claude/agents`

To skip the agents layer (e.g. for Codex targets), set `SKIP_AGENTS=1`.

There is an example in `.env.example` you can use,
and an example `.envrc.example` file if you use [direnv](https://direnv.net/).

## Adding a new skill

1. Create a folder under `skills/` with a descriptive kebab-case name
2. Add a `SKILL.md` with frontmatter and instructions (see below)
3. Add the skill to the table in [`skills/README.md`](skills/README.md)
4. Keep it focused and general-purpose
5. Test by running `make apply` or `make apply-codex` and verifying it appears in the target skills directory

## Adding a new agent

Sub-agents are single markdown files with frontmatter — see the [Claude Code sub-agents docs](https://docs.claude.com/en/docs/claude-code/sub-agents) for the schema.

1. Create `agents/<name>.md` with YAML frontmatter (`name`, `description`, optional `tools`, `model`, `color`) and the agent's system prompt below
2. Keep agents general-purpose; put machine- or client-specific ones in the private repo under `agents/`, `machines/<m>/agents/`, or `clients/<c>/agents/`
3. Run `make apply` and confirm the symlink in `~/.claude/agents/`

Agents are not applied for Codex (`make apply-codex` sets `SKIP_AGENTS=1`).

### SKILL.md format

Every skill needs a `SKILL.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: One-line description shown in skill listings
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
allowed-tools: "Bash(~/.claude/skills/my-skill/scripts/fetch-data.sh:*)"
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

- __Apply__ creates symlinks directly in `SKILLS_DIR` and `AGENTS_DIR`, alongside existing entries
- __Clean__ only removes symlinks that point to our repos, leaving your own skills and agents untouched
- __Collision handling__: If a skill or agent name already exists and isn't managed by us, `apply` will error out and the pre-existing one wins. Remove it manually if you want to use the managed version instead.

After running `make apply` or `make apply-codex`, your skills folder might look like this:

```plaintext
~/.claude/skills/   # or ~/.codex/skills/
  create-pr/       -> /path/to/agent-skills/skills/create-pr       (managed symlink)
  jira-ticket/     -> /path/to/agent-skills/skills/jira-ticket     (managed symlink)
  rebase-main/     -> /path/to/agent-skills/skills/rebase-main     (managed symlink)
  my-custom-skill/                                                  (your own skill)
  another-skill/   -> /some/other/path/skill                        (your own symlink)
```

### Cleaning up

Running `make clean` will only remove the symlinks pointing to `agent-skills/` or `agent-skills-private/` — in both `~/.claude/skills/` and `~/.claude/agents/` — leaving user-owned entries untouched.

## Bugs and pull requests

- Please report bugs and issues at [github.com/flurdy/agent-skills/issues](https://github.com/flurdy/agent-skills/issues).
- Pull requests are welcome at [github.com/flurdy/agent-skills/pulls](https://github.com/flurdy/agent-skills/pulls).


## Creator

Created by flurdy (https://flurdy.com).

## License

MIT License. See LICENSE file.
