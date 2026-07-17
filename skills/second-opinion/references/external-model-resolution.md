# External Opinion Model Resolution

Decision recorded for `skills-aan` (2026-07-17).

## Decision

`~/.agents/second-opinion/config.json` resolves **only** OpenRouter consensus profiles.
It must not resolve the ordinary `claude`, `codex`, or `gemini` routes.

Those routes retain each CLI's native configuration and authentication. This keeps subscription/OAuth
selection, organisation policy, model availability, aliases, and provider-specific reasoning controls
with the runtime that can actually validate them. A second resolver would duplicate mutable defaults,
make the displayed choice less reliable, and risk silently changing a subscription route into a
metered one.

No implementation bead is warranted: the current resolver would add configuration surface without
improving reproducibility or safety.

## Resolution order

1. **Explicit `--model <id>` wins.** The skill passes the literal ID to the selected CLI using its
   documented model option. The user explicitly chose that identity; the skill does not remap it.
2. **`--model fast` is intent, not a shared alias.** Use a verified cheap/fast alias in that CLI's
   native configuration when one exists; otherwise omit a model flag and report that the native
   default was retained.
3. **`smart` (and no `--model`) uses the CLI-native default.** Do not add a second-opinion config
   entry or infer a model from the parent session.
4. **`--agent consensus` is separate.** It resolves the explicitly selected named OpenRouter profile,
   whose exact IDs and bounds are shown by `check` before fresh metered consent.

The existing provider-independence rule still selects which ordinary CLI to ask; it does not select a
model inside that CLI.

## Effort

Effort is not portable across these external routes, so this skill does not introduce an external
`--effort` option or an effort field in shared consensus config:

- Claude Code currently exposes `--effort` (`low`, `medium`, `high`, `xhigh`, `max`) alongside
  `--model`; Claude-specific callers may use its native configuration or flag deliberately.
- Codex supports `model` and `model_reasoning_effort` in its native TOML configuration and per-run
  config overrides; retain that ownership in Codex.
- The installed Gemini CLI exposes `--model` but no documented effort flag in its command help.
- The OpenRouter helper deliberately sends no `reasoning` request object. Reasoning parameters and
  accepted values vary by provider/model; a generic translation could silently downgrade, reject, or
  change cost.

If a future interface requests effort, resolve it only through a verified provider/CLI mapping. If the
selected model does not support it, say so and either retain that runtime's default after user approval
or reject the requested override. Never silently translate one provider's effort level to another.

## Cost disclosure

Ordinary routes remain subscription/OAuth-first under the parent skill policy. Do not infer billing
from a provider name, model name, parent route, or presence of an API key. When a route is known or
unknown to be metered, disclose its effective model and effort when available and obtain the required
current-run approval before launch.

Consensus is always metered: `check` reveals its exact profile identities and limits, and the helper
pins the consented profile digest before allowing a request.

## Evidence

- The installed Codex CLI documents `-m/--model`, `-c/--config` overrides, and profile layering;
  its local native config uses `model` and `model_reasoning_effort`.
- The installed Claude Code CLI documents `--model` and `--effort`; its CLI reference is at
  <https://docs.anthropic.com/en/docs/claude-code/cli-usage>.
- The installed Gemini CLI documents `-m/--model` but no effort option; its configuration guide is
  at <https://geminicli.com/docs/cli/configuration/>.
- Codex configuration documentation: <https://developers.openai.com/codex/config-file/config-basic>.
- Repository policy: [`MODEL_ROUTING.md`](../../../MODEL_ROUTING.md), especially its parent/child
  routing and thinking-effort rules.
