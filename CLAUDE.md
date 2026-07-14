# Repo guide

Assembles Claude Code skills and agents from layered source dirs into
`~/.claude/{skills,agents}` as **symlinks**. See `README.md` for the full model (layers,
profiles, machines, clients) and `make help` for every target.

## After changing skills or agents

The active dirs hold symlinks *into this repo*, so editing files inside an existing
skill/agent is live immediately — no re-apply needed. But **adding, renaming, or removing** a
skill/agent dir changes the set of symlinks, so re-apply:

- `make dry-run` — preview what would change (read-only)
- `make apply` — (re)create the symlinks; run after a new / renamed / removed unit
- `make doctor` — check for broken or duplicate links
- `make apply-codex` — same for Codex (skips agents)

`make apply` cleans and re-applies all managed symlinks each run, leaving your own
non-managed skills/agents untouched. Options (`PROFILE`, `MACHINE`, `CLIENTS`, `FORCE`) are
in `README.md`.

## Authoring conventions

- A skill is `skills/<name>/SKILL.md`; declare semantic routing metadata
  (`model-tier`, `model-cost-policy`, `model-metered-policy`) plus `effort`, `version`, and
  `author` in frontmatter. Avoid hard-coding provider/model IDs in shared skills —
  the exception is a floating `model:` alias (`haiku`/`sonnet`) as a Claude Code
  routing hint on non-premium skills; agents omit it (pi agents honor `model:`).
  See `MODEL_ROUTING.md` and `README.md` for the add-a-skill steps.
- Add a row to both `skills/README.md` tables for any new skill: the description table
  (alphabetical) and the model-routing table (grouped by tier, cheapest first).
