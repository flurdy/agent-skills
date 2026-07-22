---
name: model-update-check
description: Read-only audit of Pi routing and configured second-opinion panel model IDs against the active Pi catalog and public live model metadata; reports when Pi or configured models merit review without editing config.
allowed-tools: "Read,Bash(~/.agents/skills/model-update-check/scripts/model-update-check.sh:*),Grep,AskUserQuestion"
model-tier: economy
model: haiku
effort: medium
version: "1.1.0"
author: "flurdy"
---

# Model Update Check

Check whether the installed Pi distribution or model IDs in these local configurations merit updating:

- `~/.pi/agent/model-tier-router.json`
- `~/.agents/second-opinion/config.json`

This is advisory and read-only. It never edits configuration, reads provider credentials, calls an
inference API, or treats a newer release date as sufficient reason to replace a model.

## Usage

```text
/model-update-check             # Hybrid: active Pi catalog + public live metadata
/model-update-check --offline   # Active installed Pi catalog only
```

## Procedure

### 1. Run the helper

Resolve `scripts/model-update-check.sh` relative to this `SKILL.md` and invoke it:

```bash
/path/to/model-update-check/scripts/model-update-check.sh
```

Pass `--offline` only when the user requested it. Hybrid mode fetches public metadata from
models.dev, OpenRouter's public model catalog, and the public npm package record. When Homebrew is
installed, it also reads local `brew info --json=v2 pi-coding-agent` metadata to determine whether
the installed formula has an available upgrade; it does not run `brew update` or `brew upgrade`.
It sends no API keys. The helper emits JSON and degrades each source independently.

Do not replace this with ad-hoc provider API calls. In particular, do not read Pi's auth store,
print environment variables, or send Anthropic/OpenAI/OpenRouter credentials merely to list models.

### 2. Check source health first

Read `sources` before interpreting models:

- Invalid or missing config is an error requiring local repair.
- `piCatalog.status != "ok"` means active availability is unknown.
- `modelsDev.status != "ok"` means live existence and recent candidates are unknown; do not infer
  staleness from the installed catalog alone.
- `openRouter.status != "ok"` means direct OpenRouter availability/expiration evidence is unknown;
  retain models.dev as secondary evidence rather than treating silence as removal.
- `homebrew.status == "ok"` is the authoritative update signal when Pi is installed from Homebrew.
  `piHomebrewUpdateAvailable` shows whether the current local Homebrew metadata reports the formula
  as outdated. `piNpmUpdateAvailable` is upstream-release context only in that case.
- If `piUpdateAvailable` is true, recommend updating Pi through its installed distribution and
  rerunning this check **before** changing model IDs. Pi ships built-in model metadata, so a stale
  release can create false config drift.

### 3. Classify configured models

Use both `piAvailable` and `liveFound`. For OpenRouter panel entries, also use `openRouterFound` and
`openRouterMetadata.expirationDate` as direct provider evidence. Local Claude/Codex/Gemini panel
routes are intentionally omitted because their native runtime configuration owns model resolution:

| State | Interpretation |
|---|---|
| both `true` | Configured model currently resolves; no mandatory update |
| Pi `false`, live `true` | Update/check Pi or authentication first; do not replace the model yet |
| Pi `true`, live `false` | Catalog mapping may lag or differ; investigate, do not auto-replace |
| both `false` | Strong replacement candidate, but still verify provider documentation |
| either `null` | Source unavailable; report uncertainty |

A model being newer is only a **review candidate**. Compare its intended role, stability, reasoning
support, input modalities, context/output limits, pricing, and billing route before recommending it.
Never choose by lexical model-name ordering or release date alone.

### 4. Preserve routing intent

For `model-tier-router.json`:

- Keep tier semantics from `MODEL_ROUTING.md`: cheap bulk, standard workflow, focused/advanced
  coding, long-context audit, premium reasoning, and premium review are different jobs.
- Preserve subscription/OAuth-first ordering and each candidate's trusted `metered` classification.
- Treat OpenAI Luna/Terra/Sol, Anthropic Haiku/Sonnet/Fable/Opus, and Gemini Flash/Pro as distinct
  capability/cost roles. A newer model in another role is not a drop-in upgrade.
- Do not copy prices, context sizes, or effort mappings into the router; Pi owns model metadata.

For `second-opinion/config.json`:

- Preserve explicit named profiles, bounded fan-out, configured quorum, and per-run OpenRouter
  consent.
- Audit all legacy `models` entries and only `kind: "openrouter"` entries in mixed `routes` profiles.
  Local routes retain their CLI-native model resolution and are not OpenRouter catalog entries.
- Use `recentOpenRouterByNamespace` only to find same-provider candidates. Preserve provider
  diversity; same-provider corroboration does not add an independent provider to quorum.
- Exact IDs stay local. Do not write them into shared skill documentation.

### 5. Render the report

```markdown
## Model Update Check
_Checked {generatedAt} · {hybrid|offline}_

**Verdict:** {UPDATE PI FIRST | REVIEW CONFIG | CURRENT | INCOMPLETE EVIDENCE}

### Source health
| Source | Status | Detail |
|---|---|---|

### Configured models
| Config / usage | Model | Pi | models.dev | OpenRouter | Release | Assessment |
|---|---|---|---|---|---|---|

### Review candidates
- {current model} → {candidate}: {role-aware evidence and trade-offs}

### Recommended actions
1. {smallest safe next action}
```

Rules for the verdict:

1. `UPDATE PI FIRST` when `piUpdateAvailable` is true and any model availability/catalog question is
   present; otherwise mention the distribution-specific update as a separate recommendation. For a
   Homebrew installation, do not treat a newer npm package as an available Homebrew upgrade.
2. `REVIEW CONFIG` when a model is missing, unavailable, deprecated by authoritative evidence, or a
   clearly role-compatible successor merits human review.
3. `CURRENT` when all configured IDs resolve and no evidence-backed role-compatible update is found.
4. `INCOMPLETE EVIDENCE` when required sources failed and no stronger finding exists.

Omit an empty candidates section. Clearly distinguish facts from judgement, and never say a config
"should update" merely because a model appears in a recent-model list.

## Maintainer validation

```bash
skills/model-update-check/tests/test-model-update-check.sh
make clean-code
```

The fixture test replaces both `pi` and `curl`; it must make no real network request.
