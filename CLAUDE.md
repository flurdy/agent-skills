# Repo guide

Assembles Claude Code skills and agents from layered source dirs into
`~/.claude/{skills,agents}` as **symlinks**. See `README.md` for the full model (layers,
profiles, machines, clients) and `make help` for every target.

Also supports other LLMs and harnesses such as Codex, Gemini, Pi, and OpenRouter
that can use the same skills and agents. See `README.md` for the full model.

## After changing skills or agents

The active dirs hold symlinks *into this repo*, so editing files inside an existing
skill/agent is live immediately — no re-apply needed. But **adding, renaming, or removing** a
skill/agent dir changes the set of symlinks, so re-apply:

- `make validate-skills` — check skill metadata, catalog parity, and local references
- `make test-validate-skills` — run the validator's fixture suite after validator changes
- `make dry-run` — preview what would change (read-only)
- `make apply` — (re)create the symlinks; run after a new / renamed / removed unit
- `make doctor` — check for broken or duplicate links
- `make apply-codex` — same for Codex (skips agents)

`make apply` cleans and re-applies all managed symlinks each run, leaving your own
non-managed skills/agents untouched. Options (`PROFILE`, `MACHINE`, `CLIENTS`, `FORCE`) are
in `README.md`.

## Authoring conventions

- A skill is `skills/<name>/SKILL.md`; declare `model-tier` (`economy`, `standard`, or
  `premium`) plus `effort` (`low`, `medium`, `high`, or `xhigh`), `version`, and `author`
  in frontmatter. Avoid hard-coding provider/model IDs in shared skills — the exception
  is an optional floating `model:` alias (`haiku`/`sonnet`/`opus`) as a Claude Code
  routing hint; agents omit it because Pi may honor `model:` in agent files. See
  `MODEL_ROUTING.md` and `README.md` for the add-a-skill steps.
- Add one alphabetical description row to `skills/README.md` for every new skill.
