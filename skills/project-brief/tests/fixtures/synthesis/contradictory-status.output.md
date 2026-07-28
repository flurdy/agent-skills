## Project Brief — Flagged Rollout — 2026-07-28 12:00 UTC

**Verdict:** AT RISK
**Scope:** workspace root + 1 repository
**Sources:** intent, Beads, Jira, and GitHub are current; release is not assessed.

### Outcomes and requirement coverage
| Outcome / requirement | Owning source | Explicit delivery links | State | Confidence |
|---|---|---|---|---|
| Enable FT_EXPORT after deployment | `docs/prds/flagged-rollout.md` | `workspace-303`, `ABC-303`, PR #30 | Contradictory | High |

### Coordination actions
- `RECONCILE` — reconcile `ABC-303` Done with open `workspace-303`; PR #30 being merged does not resolve the FT_EXPORT rollout requirement.

### Delivery and release confidence
| Dimension | State | Current evidence |
|---|---|---|
| Delivery | MERGED / CI PASS | PR #30 merged with matching CI evidence. |
| Release | NOT ASSESSED | Flag and deployment evidence were not supplied. |

**Next:** `RECONCILE` — align `ABC-303` with the remaining FT_EXPORT work in `workspace-303`.
