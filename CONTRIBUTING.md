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
(`haiku`, `sonnet`, `opus`, or `fable`) is a Claude Code-only hint, not portable routing
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

### Portable resource and tool discovery

Project setup defaults to `~/.agents/skills`. A nonempty `SKILLS_DIR` is an explicit override:
validate its absolute path and required unit files; do not silently replace a bad override.
Without an override, a Claude alias root may be a documented compatibility fallback when the
canonical unit is absent. Legacy Codex-only installations can supply their root explicitly.
Validate resources before creating links, never just the existence of the root directory. Reuse
one validated root for a skill's scripts and templates, and do not overwrite user-owned links.

Keep harness permission syntax explicit: `Bash(...)` and skill `allowed-tools` are Claude-style
metadata, not a portable enforcement guarantee. Never install permission settings as a side effect
of resource discovery. Document which template grants permit mutations.

Tool names and schemas vary by harness. Prefer adequate exposed tools; if absent, use discovery
only when actually provided (`ToolSearch` in Claude Code, or a runtime-specific alternative).
An unavailable tool/search result does not prove missing server configuration. Inspect the schema
before invocation and give a precise missing-capability or request-error handoff. Do not turn a
request failure into repeated discovery, copy credential-bearing configuration, or claim runtime
MCP behavior from static skill tests. Consumer skills should delegate discovery to the tool-owning
skill rather than copying another partial fallback. Tests for these conventions live in
`tests/test_portability.py`; run `make test-portability`.

## Validation and tests

`make check` is the full gate and is what CI runs. It takes a couple of minutes:

```bash
make check                 # clean-code, lint-python, validate-skills, security-scan, test
```

`lint-python` needs `ruff` (`pip install ruff`); `clean-code` needs `shellcheck`.

While iterating, run only what the change touches:

```bash
make validate-skills       # metadata, catalog parity, and local references
make security-scan         # security classes; fails the build on any HIGH
make test                  # every test-* suite
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
