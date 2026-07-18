# Simplify Shared Model Routing

> **Status:** Implemented and locally validated 2026-07-18; tracked by `ai-tools-8vx`
> and `skills-1hp`. See
> [`model-routing-simplification-dogfood-evidence.md`](model-routing-simplification-dogfood-evidence.md).
> **Date:** 2026-07-18

## Decision summary

Replace the current seven portable model tiers and three policy fields with:

```yaml
model-tier: economy | standard | premium
effort: low | medium | high | xhigh
```

Keep the native Claude Code `model:` alias as an optional, explicitly runtime-specific hint. Remove `model-cost-policy`, `model-metered-policy`, and `model-second-opinion-tier` from shared frontmatter. Runtime configuration owns provider order and metered classification; skills that launch external models own their own fresh-consent rules.

This deliberately trades fine-grained provider preference for a smaller capability contract that runtimes can enforce consistently.

## Why change

The current scheme has 51 skills spread across seven ordinary routing tiers, plus an `independent-reasoning` pseudo-tier, three cost-policy values, three metered-policy values, Claude-only pins, and premium guards.

The metadata distribution shows substantial duplication:

- `model-cost-policy`: 38 `prefer-subscription-oauth`, 10 `cheapest-adequate`, 3 `deliberate-premium`.
- `model-metered-policy`: 40 `ask-above-standard`, 10 `cap-or-ask`, 1 `ask-before-metered-panel`.
- `model-tier`: 24 `standard-workflow`; several other tiers differ mainly by `effort` or prose.

The Pi router confirms the practical boundary:

- `model-tier` selects a locally configured route.
- `effort` selects thinking depth.
- The selected candidate's local `metered` boolean alone controls confirmation.
- Cost/metered policy strings are only displayed as context and cannot alter the gate.
- `model-second-opinion-tier` and Claude's `model:` are ignored by Pi.

The shared validator currently requires and mirrors the extra metadata without proving that a runtime acts on it.

## Goals

- Retain the cheapest-adequate capability distinction that affects runtime routing.
- Keep thinking effort independent from model capability.
- Keep exact model IDs, provider order, authentication, and spend classification local to each runtime.
- Preserve Pi's fail-closed metered confirmation.
- Preserve Claude Code's useful native `model:` hint without pretending it is portable.
- Keep external-model consent and vendor independence where they can actually be enforced.
- Reduce authoring choices, duplicated catalog data, and policy prose.

## Non-goals

- Choosing exact provider/model IDs in this repository.
- Changing Pi's one-way nested upgrade/restoration behavior.
- Making shared skills resolve or classify child models.
- Weakening `/second-opinion` panel consent or `/orchestrate` child consent.
- Rewriting historical plans or evidence logs to use the new terminology.
- Reassessing each skill's present capability requirement during the mechanical migration.

## Proposed replacement `MODEL_ROUTING.md`

The following is the proposed complete steady-state policy, not an edit to the current file yet.

---

# Model Routing

This repository is shared by Claude Code, Pi, and Codex. Shared skills declare only the model capability class and reasoning depth they need. Exact providers, model IDs, fallback order, authentication, and billing classification belong to runtime-local configuration.

## Skill frontmatter

Every active shared skill declares:

```yaml
model-tier: standard
effort: medium
```

Allowed tiers:

| Tier | Use for |
|------|---------|
| `economy` | Deterministic status checks, retrieval, mechanical scans, and low-risk summaries. |
| `standard` | Normal workflow orchestration, bounded implementation, and broad audits with established patterns and objective validation. This is the default. |
| `premium` | Work where substantial judgment or a costly mistake justifies the strongest configured capability: unclear design boundaries, complex migrations/conflicts, architecture, high-risk verification, and final craft review. |

Allowed shared defaults for `effort` are `low`, `medium`, `high`, and `xhigh`:

- `low`: dogfooded deterministic workflows where the saving matters.
- `medium`: routine retrieval, status, and workflow orchestration.
- `high`: implementation, broad audits, and complex coordination.
- `xhigh`: high-risk reasoning or review where subtle misses are costly.

Capability and effort are independent. Use `standard` plus `high` for bounded implementation or a broad audit. Do not create another model tier merely to express more thinking.

## Runtime ownership and spend safety

Runtime configuration owns:

- exact provider/model IDs;
- candidate and fallback order;
- authentication route;
- whether a candidate is metered;
- confirmation and token/usage controls.

Shared metadata must not infer billing from provider, model name, or authentication type. In Pi, the locally configured candidate's explicit `metered` value is the spend authority. Metered candidates require the router's confirmation; absent skill policy strings cannot waive it.

A skill that directly launches an external model must implement fresh consent at the point of exposure when that route is metered or unknown. Parent routing approval never authorizes child fanout or an external panel. Keep those rules in the launching skill or runtime adapter, where they can be enforced.

## Claude Code `model:` hint

`model:` is an optional Claude Code-only floating alias (`haiku`, `sonnet`, or `opus`). It is not portable routing metadata:

- Pi's skill router ignores it.
- Codex uses its own configuration.
- Agents omit it because Pi may honor `model:` in agent files.

Use a pin only when running the skill on that Claude capability class is intentional. An unpinned `premium` skill rides the session model and must retain its existing advisory tier guard. Runtime-specific exceptions such as `watch-prs` belong in that skill, not in this shared policy.

## Parent and child routing

Skill metadata routes the current parent only. It does not classify or authorize child launches. Metered or unknown child routes require fresh current-run consent; otherwise inherit the parent route or continue serially. Runtime-specific child discovery and evidence rules belong in `/orchestrate` and its adapter references.

## Client behavior

- **Pi:** a local router maps `model-tier` to configured candidates, honors `effort`, confirms locally classified metered candidates, permits nested upgrades but not downshifts, and restores the previous route after settlement.
- **Claude Code:** reads native `model:` and `effort`; semantic `model-tier` remains the portable source classification.
- **Codex:** keeps exact routing in Codex configuration or explicit CLI/runtime controls.

## Authoring rule

Choose the lowest tier that can responsibly complete the work:

1. Use `economy` only for low-risk, mostly deterministic work.
2. Use `standard` by default, including bounded coding with fixed scope and objective validation.
3. Use `premium` when unresolved design judgment or the cost of a mistake is material.
4. Express reasoning depth with `effort`, not another tier.
5. Put exceptional consent or runtime behavior in the skill that performs it.

---

## Exact skill migration

This is a mechanical initial mapping. Keep each skill's current `effort` and current Claude `model:` value unless explicitly noted.

### `economy` — 8 skills

Map current `cheap-bulk` skills to `economy`:

- `beads-check-dolt-migration`
- `browser-screenshot`
- `circleci-status`
- `confluence`
- `jira-ticket`
- `model-update-check`
- `next`
- `start-ticket`

### `standard` — 30 skills

Map current `standard-workflow`, `focused-coding`, and `long-context-audit` skills to `standard`:

- `backlog-groom`
- `clean-code`
- `complete-task`
- `contract-check`
- `create-pr`
- `eas-build-error`
- `handoffs`
- `handoffs-tidy`
- `landscape`
- `name-session`
- `outstanding-work`
- `pr-status`
- `ready-to-merge`
- `ready-to-release`
- `release-manager`
- `release-status`
- `reply-comments`
- `second-opinion`
- `setup-multirepo-git`
- `simplify-solution`
- `stack-branch`
- `tidy-settings`
- `tracking-sweep`
- `trello-beads`
- `triage`
- `watch-flux-rollout`
- `watch-prs`
- `watch-release`
- `watch-rollout`
- `wrap-up`

The former distinctions remain visible through effort:

- former `standard-workflow`: usually `medium`;
- former `focused-coding`: `high`;
- former `long-context-audit`: retain the current declared effort initially, then reassess separately if evidence supports `high`.

### `premium` — 13 skills

Map current `advanced-coding`, `premium-reasoning`, and `premium-review` skills to `premium`:

- `architect`
- `beads-migrate-to-dolt`
- `contract-test`
- `diagnose-bug`
- `orchestrate`
- `pedantic-review`
- `rebase-main`
- `rebase-merged-parent`
- `rebase-parent`
- `review-comments`
- `review-pr`
- `total-review`
- `verify-task`

Keep current effort differences:

- implementation/conflict work: usually `high`;
- architecture, diagnosis, verification, and craft review: usually `xhigh`;
- `orchestrate`: retain deliberate `high`.

### Agent metadata

`agents/tracking-auditor.md` maps from `long-context-audit` to `standard` and drops the two policy strings. It remains without a Claude `model:` pin.

## Claude pin migration

Preserve native Claude behavior during the first migration rather than combining taxonomy cleanup with model-behavior retuning:

- Existing `haiku`, `sonnet`, and `opus` pins remain unchanged.
- `watch-prs` remains unpinned for its documented wakeup/session-model reason.
- Former `premium-reasoning` and `premium-review` skills remain unpinned and keep their advisory guard.
- Former `advanced-coding` skills retain `model: opus` initially.

This means `model:` is an optional runtime-specific override, not a deterministic projection of the three portable tiers. Any later normalization of pins should be a separately evidenced change.

## Intentional behavior changes

Pi will have one `premium` candidate order instead of separate `advanced-coding`, `premium-reasoning`, and Claude-first `premium-review` orders. The proposed default is to copy the current `premium-reasoning`/`advanced-coding` capability order into `premium`.

This removes skill-specific vendor preference from the portable taxonomy. Review independence remains available through `/second-opinion`; a user who wants a particular provider can select it explicitly in the runtime. If retaining a Claude-first Pi review route is considered essential, use four tiers and keep `premium-review`; do not add cost-policy metadata back.

Former `long-context-audit` skills also move from their current Pi premium-capability route to `standard`. Their current Claude pin and declared effort are already `sonnet`/`medium`, and their work is broad rather than inherently high-judgment. Runtime standard candidates must still have an adequate context window; a specific audit with material judgment or context pressure should use `premium` rather than reintroducing a permanent long-context tier.

Recommendation: accept both consolidations. The economy/standard/premium capability boundaries are valuable; encoding review taste or document breadth as separate portable provider-order tiers is not.

## Metadata removed

Remove from all active skills and agents:

```yaml
model-cost-policy: ...
model-metered-policy: ...
model-second-opinion-tier: ...
```

Replacement ownership:

| Removed metadata | Replacement |
|------------------|-------------|
| `model-cost-policy` | One runtime-configuration recommendation: prefer subscription/OAuth candidates when appropriate. |
| `model-metered-policy` | Runtime-local candidate `metered` classification and confirmation. |
| `model-second-opinion-tier` | `/second-opinion` body rules for vendor independence and explicit panel consent. |

Update `/second-opinion` prose to describe its behavior directly without claiming a routing tier. Keep `ask-before-metered-panel` behavior unchanged in the skill body/reference.

## Catalog and validator simplification

Delete the duplicated 51-row model-routing table from `skills/README.md`. Keep the alphabetical skill-description table and add only a short link to `MODEL_ROUTING.md`.

Change `scripts/validate-skills.py` to:

- require `model-tier` and `effort`, but not the removed policy fields;
- accept only `economy`, `standard`, or `premium` for skills;
- accept only `low`, `medium`, `high`, or `xhigh` as shared skill defaults;
- if `model:` exists, accept only floating aliases `haiku`, `sonnet`, or `opus`;
- stop parsing and checking routing-table parity;
- continue checking skill names, required metadata, description-catalog parity, local references, and archived skills.

Update `tests/test_validate_skills.py` fixtures and assertions to prove invalid tiers, invalid effort, and invalid Claude aliases fail. Remove tests whose only purpose was routing-table duplication.

## Active documentation updates

Update these active sources:

- `MODEL_ROUTING.md` — replace with the shorter policy above.
- `README.md` — simplify add-a-skill steps and example frontmatter.
- `CLAUDE.md` and root `AGENTS.md` source — require only tier plus effort; remove the second-table authoring rule.
- `skills/README.md` — remove the routing table and footnotes.
- All 51 `skills/*/SKILL.md` frontmatters — migrate tier and remove policy fields.
- Premium skill bodies — rename their declared tier to `premium` and retain the advisory guard.
- `skills/architect/SKILL.md` — change implementation-tier recommendations to `standard` or `premium`; planning tiers such as `second-opinion` remain a separate user-facing concept.
- `skills/second-opinion/SKILL.md` — remove the pseudo-tier claim while preserving independence and consent.
- `skills/orchestrate/SKILL.md`, `skills/orchestrate/references/child-routing-policy.md`, and active orchestrate README — describe work shape as economy/standard/premium plus effort; keep child consent locally.
- `agents/tracking-auditor.md` — migrate as described above.
- `skills/model-update-check/tests/test-model-update-check.sh` — rename example tier fixtures; the implementation already treats tier names generically.

Do not rewrite `docs/plans/orchestrate-skill.md` or `docs/plans/orchestrate-dogfood-evidence.md`; they are historical evidence. Add a short historical-taxonomy note only if readers could otherwise mistake them for current policy.

## Cross-repository/runtime prerequisite

The installed Pi router accepts arbitrary tier names, so no routing algorithm change is required. The rollout must nevertheless update its configuration and documentation before shared skills switch names.

In `flurdy/ai-tools`:

1. Add `economy`, `standard`, and `premium` entries to the example and active user configuration while retaining old tier entries temporarily.
2. Copy candidate ordering as follows:
   - `economy` from `cheap-bulk`;
   - `standard` from `standard-workflow`/`focused-coding` (same capability class; skill effort supplies medium/high);
   - `premium` from `advanced-coding`/`premium-reasoning`.
3. Give the three routes strictly increasing ranks.
4. Update router README examples and tests to use the new taxonomy.
5. Stop parsing/displaying the removed cost/metered policy strings, or retain parser compatibility temporarily without documenting them.
6. Keep candidate `metered` mandatory and keep all confirmation tests.

Unknown tiers currently fail safely by retaining the active model, but preloading both old and new config names avoids a temporary routing no-op.

## Implementation slices

| # | Slice | Observable outcome | Acceptance evidence |
|---|-------|--------------------|---------------------|
| 1 | Add three-tier compatibility in `ai-tools` config/docs/tests while keeping old entries. | Pi can route both old and new skill metadata during migration; metered confirmation and restoration are unchanged. | In `ai-tools/pi/model-tier-router`: `fnm exec --using=.nvmrc npm test` and `fnm exec --using=.nvmrc npm run typecheck`; inspect example config for both taxonomies. |
| 2 | Replace shared policy, metadata, validator, authoring docs, and catalog duplication. | Every active skill declares exactly one of three tiers plus a valid effort; no active skill/agent declares removed policy fields. | `make validate-skills`; `make test-validate-skills`; targeted `rg` returns no removed fields or old tier names outside explicitly exempt historical files. |
| 3 | Update active skill-body terminology and exceptional consent ownership. | Premium guards name `premium`; `/second-opinion` and `/orchestrate` retain enforceable consent without pseudo-tier metadata. | Source inspection plus existing skill-specific tests; `make validate-skills` confirms references. |
| 4 | Dogfood and clean compatibility entries. | Economy, standard, and premium skills each produce the expected Pi route/effort; rollback remains possible until evidence is accepted. | `/model-tier status` during one explicit skill from each tier; confirm a metered candidate still prompts; confirm settlement restores the prior model. Remove old local tiers only after this passes. |

## Test strategy

### Shared repository

- Happy path: all 51 skills map exactly once to the three allowed tiers and validate.
- Sad path: fixtures with an old tier, removed required field assumptions, invalid effort, or invalid Claude alias fail with a useful message.
- Edge cases: unpinned `watch-prs`, unpinned guarded premium skills, pinned former advanced skills, and agent metadata remain valid.
- Regression: description catalog parity and Markdown/local-tool reference checks still run.

### Pi router

- Happy path: all three new tiers select configured candidates and apply skill effort.
- Sad path: unknown tier retains the current model; unavailable candidate retains the current model; metered route without UI fails closed.
- Edge cases: nested standard/high under premium does not downshift; nested premium upgrades; lower-tier skill can still raise effort; manual model changes cancel restoration as today.
- Spend safety: every `metered: true` explicit route prompts, implicit reads never prompt, and removed policy strings cannot waive confirmation.

### Claude Code and Codex

- Claude: sample pinned economy, standard, and premium skills honor their floating alias; an unpinned premium guard still executes.
- Codex: shared metadata remains advisory and exact routing stays in Codex configuration.

## Rollout and rollback

1. Update `ai-tools` and local Pi configuration first, keeping old and new route names.
2. Merge the shared-skill migration as one coherent change so documentation, validation, and metadata cannot drift.
3. Existing skill-file edits are live through symlinks; no `make apply` is required unless a skill/agent directory is added, renamed, or removed.
4. Run `make dry-run` and `make doctor` after validation to confirm assembly health.
5. Dogfood one skill per tier and verify metered behavior/restoration.
6. Remove obsolete tier entries from local Pi configuration only after the shared migration is deployed everywhere that consumes it.

Rollback by reverting the shared-skill migration. The temporary old Pi tier entries make rollback immediate. Do not remove old config entries until the dogfood gate has passed.

## Risks and mitigations

- **Risk: one premium route loses Claude-first review preference in Pi.** → Accept as the main simplification; use explicit runtime selection or `/second-opinion` for provider-specific review. Keep four tiers only if evidence shows this materially harms review quality.
- **Risk: shared skills switch before local Pi config.** → Add new config entries first and retain old entries through dogfood.
- **Risk: collapsing focused coding into standard makes bounded implementation appear equivalent to routine workflow.** → Preserve `effort: high`, one-writer rules, objective validation, and escalation in the implementing/orchestration skills; model capability was already the same.
- **Risk: collapsing broad audit into standard underpowers long context.** → Keep explicit effort and permit runtime candidate context capacity to satisfy standard. Escalate a specific audit to premium when evidence shows substantial judgment or context pressure.
- **Risk: removing policy strings weakens spend safety.** → Pi's mandatory local `metered` boolean remains the actual gate; external launchers keep direct consent rules.
- **Risk: historical documents retain old names.** → Treat them as historical evidence and add a note rather than rewriting records.

## Tracking recommendation

**Filed 2026-07-18** as two beads across the two repos (cross-DB, so the dependency is textual): `ai-tools-8vx` (Pi router three-tier compatibility, the prerequisite) blocks `skills-1hp` (this repo's metadata/docs/validator migration). The closed `skills-88v` epic documents the earlier taxonomy but does not track this reversal.

## External review record

- **Codex:** recommended three tiers, retaining `effort`, removing both generic policy fields, moving child rules to `/orchestrate`, and deleting the independent-reasoning pseudo-tier.
- **Claude:** agreed the policy is overbuilt; recommended three model classes plus optional `premium-review`, removing `model-cost-policy`, and retaining only enforceable metered control.
- **Gemini:** unavailable because the local CLI failed with `SyntaxError: Invalid regular expression flags`; no Gemini opinion was inferred.
- **Resolution:** choose three tiers. The only material disagreement is whether Claude-first premium review deserves a fourth portable tier; this draft recommends no.

## Approval decisions before implementation

1. Accept one portable `premium` route and the loss of Pi's automatic Claude-first review ordering. **Recommended: yes.**
2. Move former `long-context-audit` skills to `standard`, escalating exceptional audits explicitly. **Recommended: yes.**
3. Remove the duplicated routing table rather than merely shortening its columns. **Recommended: yes.**
4. Preserve existing Claude pins during migration and review them separately. **Recommended: yes.**
5. Create a new bead for the cross-repository implementation after approving this draft. **Recommended: yes, through `/triage`.**

## Next concrete action

Review the four approval decisions; if accepted, implement the `ai-tools` compatibility/config slice before changing shared skill metadata.
