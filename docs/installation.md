# Installation and configuration

This guide covers installation destinations, prompt templates, private overlays,
migration, and cleanup. For the shortest adoption path, start with the root
[README](../README.md#quick-start).

## Shared installation

From the repository root:

```bash
make dry-run
make apply
make doctor
```

The default destinations are:

- Canonical skills: `~/.agents/skills`
- Claude skill aliases: `~/.claude/skills`
- Claude agents: `~/.claude/agents`

Pi and Codex discover `~/.agents/skills` natively. `make apply-codex` is a
compatibility alias that applies the same shared skill root with `SKIP_AGENTS=1`.

## Prompt templates

Top-level Markdown files in `prompts/` become slash commands named after their
filename. They use `$ARGUMENTS` for optional input.

### Pi

Merge the repository prompt directory into Pi's existing global settings:

```json
{
  "prompts": ["~/Code/flurdy/agent-skills/prompts"]
}
```

Alternatively, symlink individual templates into Pi's default prompt directory:

```bash
mkdir -p ~/.pi/agent/prompts
ln -sfn "$PWD/prompts/about.md" ~/.pi/agent/prompts/about.md
ln -sfn "$PWD/prompts/squash-msg.md" ~/.pi/agent/prompts/squash-msg.md
ln -sfn "$PWD/prompts/trim-comments.md" ~/.pi/agent/prompts/trim-comments.md
```

Use one loading method, not both, to avoid duplicate command names. Restart Pi or
run `/reload` after changing templates.

### Claude Code

Symlink templates into Claude Code's user command directory:

```bash
mkdir -p ~/.claude/commands
ln -sfn "$PWD/prompts/about.md" ~/.claude/commands/about.md
ln -sfn "$PWD/prompts/squash-msg.md" ~/.claude/commands/squash-msg.md
ln -sfn "$PWD/prompts/trim-comments.md" ~/.claude/commands/trim-comments.md
```

Prompt setup is intentionally manual and local. `make apply` does not install
prompt templates. Codex custom-prompt installation is deferred because that
feature is deprecated.

## Private overlays

Create an optional sibling repository named `agent-skills-private/`, or set
`PRIVATE_REPO` to another path:

```text
agent-skills/
  skills/
  agents/
agent-skills-private/
  skills/
  agents/
  machines/
    my-machine/
      skills/
      agents/
  clients/
    my-client/
      skills/
      agents/
  profiles/
    my-machine-profile.env
```

Skills and agents use the same resolution order. Later layers override earlier
units with the same name:

1. Shared: `agent-skills/{skills,agents}/`
2. Private shared: `agent-skills-private/{skills,agents}/`
3. Private machine: `agent-skills-private/machines/<machine>/{skills,agents}/`
4. Private client(s): `agent-skills-private/clients/<client>/{skills,agents}/`

Select layers directly:

```bash
make apply MACHINE=my-machine CLIENTS="my-client my-other-client"
```

Or put the selection in `agent-skills-private/profiles/my-machine-profile.env`:

```properties
MACHINE=my-machine
CLIENTS="my-client my-other-client"
```

Then apply it with:

```bash
make apply PROFILE=my-machine-profile
```

## Configuration variables

Set these as environment variables or accept the defaults:

| Variable | Purpose | Default |
|---|---|---|
| `SHARED_REPO` | Shared repository path | This repository |
| `PRIVATE_REPO` | Optional private repository path | Sibling `agent-skills-private/` |
| `SKILLS_DIR` | Canonical skills root | `~/.agents/skills` |
| `CLAUDE_SKILLS_DIR` | Claude per-skill aliases | `~/.claude/skills` |
| `LEGACY_CODEX_SKILLS_DIR` | Old managed Codex links removed during apply/clean | `~/.codex/skills` |
| `AGENTS_DIR` | Claude agent links | `~/.claude/agents` |
| `SKIP_AGENTS` | Skip the Claude-style agent layer when `1` | `0` |

See `.env.example` and `.envrc.example` for shell and direnv examples.

## Coexisting with existing content

The assembler is designed to preserve user-owned content:

- `apply` creates managed links in the canonical skills root, Claude aliases, and
  Claude agent directory.
- `clean` removes only repository-managed links and compatibility aliases.
- An unmanaged entry with the same name causes a preflight failure before mutation.
- Destination roots must be real directories; the assembler refuses to traverse or
  replace a user-managed root symlink.

After `make apply`, a typical installation looks like:

```text
~/.agents/skills/
  create-pr/       -> /path/to/agent-skills/skills/create-pr
  jira-ticket/     -> /path/to/agent-skills/skills/jira-ticket
  my-custom-skill/                                            # preserved

~/.claude/skills/
  create-pr/       -> ~/.agents/skills/create-pr              # managed alias
  jira-ticket/     -> ~/.agents/skills/jira-ticket            # managed alias
  claude-only/                                               # preserved
```

## Migrating an existing installation

`make dry-run` previews the migration. `make apply` moves repository-managed skill
links into `~/.agents/skills`, replaces old managed Claude links with aliases, and
removes old managed links from `~/.codex/skills`. Unmanaged files, directories, and
third-party symlinks remain in place.

Pi already discovers `~/.agents/skills`. After `make doctor` confirms the canonical
installation, remove `"~/.claude/skills"` from Pi's user-level `skills` array to
avoid duplicate discovery, then restart Pi or run `/reload`. Keep unrelated skill
paths.

To roll back, check out the previous repository version and run that version's
`make apply` and `make apply-codex` targets. Do not replace an existing skills root
with a directory symlink unless all user-owned content has been reconciled manually.

## Cleaning up

```bash
make clean-dry-run
make clean
```

`make clean` removes managed canonical skill links, Claude aliases, legacy managed
Codex links, and managed Claude agents. User-owned entries are preserved.
