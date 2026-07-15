# Shared Agents

Claude Code sub-agents. Each is a single `*.md` file with YAML frontmatter (`name`, `description`, optional `tools`, `model`, `color`) and the agent's system prompt below.

See the [Claude Code sub-agents docs](https://docs.claude.com/en/docs/claude-code/sub-agents) for the frontmatter schema.

| Agent | Description |
|-------|-------------|
| tracking-auditor | Audit that the current branch's work is tracked correctly (beads/Jira/Trello) and that the diff matches the ticket's scope. Read-only. Invoke at PR boundaries. |

These Claude-style Markdown agents are applied only to Claude targets. `make apply-codex` skips this repository's agents layer (`SKIP_AGENTS=1`); installed Codex versions may provide their own native multi-agent tools.
