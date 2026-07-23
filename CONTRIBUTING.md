# Contributing

Contributions should keep skills and agents focused, portable, and safe to install
alongside user-owned content.

## Add a skill

1. Create `skills/<name>/SKILL.md` using a descriptive kebab-case name.
2. Add frontmatter and focused agent instructions.
3. Declare a semantic `model-tier` and `effort`; see
   [MODEL_ROUTING.md](MODEL_ROUTING.md).
4. Add one alphabetical description row to [skills/README.md](skills/README.md).
5. Run `make validate-skills`.
6. Run `make apply` and confirm the canonical skill and Claude alias links.

A minimal skill looks like:

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

Allowed portable tiers are `economy`, `standard`, and `premium`. Allowed effort
values are `low`, `medium`, `high`, and `xhigh`. An optional floating `model:` alias
(`haiku`, `sonnet`, or `opus`) is a Claude Code-only hint, not portable routing
metadata. Exact providers, model IDs, billing classification, and fallback policy
remain runtime-local.

## Add an agent

Claude-style sub-agents are single Markdown files under `agents/`. See the
[Claude Code sub-agents documentation](https://docs.claude.com/en/docs/claude-code/sub-agents)
for the native schema.

1. Create `agents/<name>.md` with `name`, `description`, `model-tier`, `effort`, and
   optional `tools` or `color` frontmatter.
2. Keep the agent general-purpose. Put machine- or client-specific definitions in
   the optional private repository.
3. Run `make apply` and confirm the link under `~/.claude/agents/`.

Shared agents omit `model:` because Pi may honor that field directly. Codex targets
skip this repository's Claude-style agent layer.

## Helper scripts and permissions

Put shell commands, API calls, and other executable helpers under a skill's
`scripts/` directory. This gives `allowed-tools` a stable, narrow command prefix and
avoids repeated broad approvals.

```text
skills/
  my-skill/
    SKILL.md
    scripts/
      fetch-data.sh
    templates/
      body.md
```

Declare the installed helper path in frontmatter:

```yaml
allowed-tools: "Bash(~/.agents/skills/my-skill/scripts/fetch-data.sh:*)"
```

Separate multiple patterns with commas. Glob patterns match the full command
string. Without `allowed-tools`, users may be prompted for every tool call.

## Validation and tests

Run the checks relevant to the change:

```bash
make validate-skills       # metadata, catalog parity, and local references
make test-validate-skills  # validator fixture suite
make test-assemble         # installer behavior
make test-second-opinion   # second-opinion helper suites
make clean-code            # repository formatting and quality checks
```

Every new, renamed, or removed skill or agent changes the managed link set. After
such changes:

```bash
make dry-run
make apply
make doctor
```

Editing a file inside an existing linked unit is live immediately, but validation
still applies.

## Pull requests

Keep pull requests atomic and explain what changed and why. Report issues at
[github.com/flurdy/agent-skills/issues](https://github.com/flurdy/agent-skills/issues)
and open pull requests at
[github.com/flurdy/agent-skills/pulls](https://github.com/flurdy/agent-skills/pulls).
