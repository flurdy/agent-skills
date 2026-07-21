# External opinion model and effort resolution

Decision recorded for `skills-aan` (2026-07-17), extended by `skills-qg4` (2026-07-21).

## Single-agent routes

Ordinary `claude`, `codex`, and `gemini` commands retain each CLI's native configuration and
authentication. The second-opinion config does not replace their mutable defaults.

Resolution order:

1. Explicit `--model <id>` wins and is passed through using the selected command's native control.
   Claude, Gemini, and `codex exec` accept a model flag; `codex review` instead requires
   `-c 'model="<id>"'` because it has no `--model` option.
2. `--model fast` uses a verified CLI-native cheap/fast alias when available; otherwise the skill
   retains and reports the native default.
3. `smart` or no `--model` retains the CLI-native default.

Report provenance from the control actually applied. A literal model override is `override`; an
omitted control is `native-default`. Do not infer or report Codex reasoning effort unless an explicit
native `model_reasoning_effort` override was supplied.

`peer` is the explicit name for the default one-call independent route. Claude sessions prefer Codex;
GPT/Codex sessions prefer Claude; other sessions choose the best available independent Claude or
Codex route. The provider-independence rule chooses a CLI, not its model.

## Panel routes

Named `quorum` and `consensus` panels may now configure local and OpenRouter routes under
`~/.agents/second-opinion/config.json`. This is an explicit panel contract, not a second resolver for
ordinary commands:

- omitted local model/effort means `native-default` and is reported as such;
- `--route-model ID=VALUE` and `--route-effort ID=VALUE` are explicit per-route overrides;
- generic `--model` is invalid for panel execution;
- OpenRouter model identities come only from the selected profile and cannot be overridden at run
  time.

The configured `extreme` OpenRouter-only profile remains valid. Mixed profiles add explicit local
choices without changing single-agent defaults.

## Effort

Effort is validated only where the selected CLI exposes a verified native control:

- Claude: `low`, `medium`, `high`, `xhigh`, `max` via `--effort`;
- Codex: `minimal`, `low`, `medium`, `high`, `xhigh` via `model_reasoning_effort`;
- Gemini: no supported effort override;
- OpenRouter: no generic reasoning translation.

Unsupported values are rejected. Omitted values preserve the native default; the skill never invents
a universal effort mapping or claims to know an unreported effective default.

## Cost and consent

Single routes remain subscription/OAuth-first under the parent skill's policy, while known or unknown
metered single routes require current-run disclosure. Panel configuration does not infer billing from
a provider or model name.

Every OpenRouter subset is metered. The panel coordinator binds its exact identities and prompt before
fresh consent, then executes only the approved subset once. Declining can still run approved local
routes with honest quorum/consensus degradation.

## Evidence

- Claude Code CLI documents `--model` and `--effort`: <https://docs.anthropic.com/en/docs/claude-code/cli-usage>.
- Codex documents `--model`, `--config`, and `model_reasoning_effort`:
  <https://developers.openai.com/codex/config-file/config-basic>.
- Gemini CLI documents `--model` but no portable effort option:
  <https://geminicli.com/docs/cli/configuration/>.
- Repository routing policy: [`MODEL_ROUTING.md`](../../../MODEL_ROUTING.md).
- Panel schema and execution: [review-panels.md](review-panels.md).
