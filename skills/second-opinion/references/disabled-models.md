# Disabled-model policy

An optional, user-owned deny list keeps particular models or local agents out of second-opinion
routes for chosen directories, for example for licence or client reasons. The Pi skill model router
reads the same file for its tier candidates.

## File

The path is fixed: `~/.agents/disabled-models.json`. No request field, argument or environment
variable selects another file, and the guarded stdin transport rejects any attempt to supply one.

```json
{
  "version": 1,
  "rules": [
    {
      "id": "client-work",
      "roots": ["/home/me/Code/client", "/home/me/Code/client-api"],
      "models": ["openrouter/vendor/model-id"],
      "agents": ["gemini"],
      "reason": "Not approved for client code"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Unique rule name, shown in every report |
| `roots` | Absolute directories; each also covers its descendants |
| `models` | Exact `provider/model` identities, such as an OpenRouter route's `model` |
| `agents` | Whole local CLI routes: `claude`, `codex`, `gemini` (any model or alias) |
| `reason` | Optional text shown with the rule ID |

Local routes are matched only by `agents`, because their models are CLI-native aliases rather than
provider identities. Each rule needs at least one model or agent.

## Matching

- The scope is the directory the helper runs in (the invoking session's cwd), compared with each root
  on path-component boundaries, both as written and after resolving symlinks. A symlinked member
  repository stored elsewhere needs its own root; workspaces are not discovered.
- Matching rules accumulate. Nothing re-enables a denied model or agent.
- A root that does not exist on this machine stays valid and simply does not match.

## Failure behaviour

| Policy state | Effect |
|---|---|
| File absent | Existing behaviour; no route is affected |
| No rule matches | Existing behaviour |
| Malformed, unreadable, unsupported version or unknown field | Nothing runs: direct checks exit 2 and panel `check`/`run-*` abort |

## Effects

- **Direct routes:** `disabled-models.py check-direct AGENT` exits 3 with `reasons` when denied.
  An explicitly requested agent stops; `peer` resolution skips denied agents and says so.
- **Panels:** matching enabled routes keep counting towards `quorum` and `consensusQuorum`, so a
  denial can only make a threshold harder to meet. `check` lists them as `policyDeniedRoutes` with
  availability `disabled-by-policy`; `run-local` and the OpenRouter subset never invoke them; and
  `evaluate` reports them as `disabled-by-policy` unavailable routes. The policy revision, matched
  rules and denials are part of `panelSha256`, and denials change `openrouterSha256`, so any policy
  edit after `check` requires a fresh check and consent.
- Consent, billing classification and subscription checks are unchanged. The policy only removes
  routes; it is route selection for this skill, not universal model enforcement.
