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
