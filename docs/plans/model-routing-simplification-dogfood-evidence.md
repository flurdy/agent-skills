# Model-routing simplification dogfood evidence

## Scope

- Date: 2026-07-18
- Shared migration: `skills-1hp` in this repository
- Router prerequisite: local `ai-tools` commit `48c5aff` (`feat(pi): add three-tier router compatibility`)
- Router configuration: active user configuration contains `economy`, `standard`, and `premium` alongside the temporary legacy entries

The live skill directories symlink into this repository, so the dogfood exercised the migrated active skill files without running `make apply`.

## Three-tier route and restoration dogfood

Each check launched a fresh non-interactive Pi process with the router source from `48c5aff` and a read-only probe extension loaded after the router. The probe recorded the model and thinking level at session start, after explicit skill routing, after the assistant response, and after `agent_settled`. Tools were disabled because these checks validate routing rather than skill behavior.

| Tier | Active skill | Initial route | Routed response | After settlement | Result |
|------|--------------|---------------|-----------------|------------------|--------|
| `economy` | `next` (`effort: medium`) | `gpt-5.6-sol` / `low` | `gpt-5.6-luna` / `medium` | `gpt-5.6-sol` / `low` | PASS |
| `standard` | `simplify-solution` (`effort: high`) | `gpt-5.6-luna` / `low` | `gpt-5.6-terra` / `high` | `gpt-5.6-luna` / `low` | PASS |
| `premium` | `architect` (`effort: xhigh`) | `gpt-5.6-luna` / `low` | `gpt-5.6-sol` / `xhigh` | `gpt-5.6-luna` / `low` | PASS |

All three explicit skill commands selected the configured unmetered primary, honored the skill's declared effort, completed a response on that route, and restored both the original model and thinking level when the run settled.

## Metered confirmation gate

The focused router suite passed all 42 tests:

```text
cd /home/ivar/Code/flurdy/ai-tools/pi/model-tier-router
fnm exec --using=.nvmrc npm test
fnm exec --using=.nvmrc npm run typecheck
```

The lifecycle suite includes these observed gates:

- `requires and captures explicit metered confirmation without skill policy metadata` — the extension emits one confirmation request for a metered candidate even though the skill has no removed policy fields;
- `simulates declined and unavailable metered confirmation` — declining or running without confirmation UI retains the original model;
- `stages explicit routing until the expanded skill starts, then restores after settlement` — the original model and thinking level return after settlement.

No metered provider was invoked during live dogfood; the active three-tier primaries are locally classified `metered: false`.

## Shared-repository checks

These checks passed after the migration:

```text
make clean-code
make validate-skills
make test-validate-skills
skills/model-update-check/tests/test-model-update-check.sh
skills/second-opinion/tests/test-openrouter-panel.sh
make dry-run
make doctor
git diff --check
```

A deterministic comparison against `HEAD` also confirmed that all 51 skills mapped exactly once, retained their existing `effort` and Claude `model:` values, and removed the three retired policy fields. A targeted search found no retired tier names or removed fields outside the explicitly historical plans.

## Rollout state

Local implementation and dogfood pass. Both repositories still have local, unpushed work: the router prerequisite commit is one commit ahead of `origin/main`, and this shared migration remains uncommitted. Remote deployment is intentionally outside this evidence run and requires explicit push permission.
