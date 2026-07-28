## Project Brief — Migration Workspace — 2026-07-28 12:00 UTC

**Verdict:** BLOCKED
**Scope:** workspace root + 3 repositories
**Sources:** intent, Beads, decisions, Jira, and the recorded status channel are current.

### Outcomes and requirement coverage
| Outcome / requirement | Owning source | Explicit delivery links | State | Confidence |
|---|---|---|---|---|
| Migrate customer records by 2026-08-01 | `docs/prds/migration.md` | `workspace-401`, `DEC-9` | Blocked | High |

### Coordination actions
- `BLOCK` — resolve `DEC-9`; `workspace-401` states that migration cannot start without it.
- `RECONCILE` — review the Done status of `ABC-402` against the remaining repository task.
- `COMMUNICATE` — update the recorded `#migration-status` channel after the decision outcome is known.

### Delivery and release confidence
| Dimension | State | Current evidence |
|---|---|---|
| Delivery | BLOCKED | `workspace-401` cannot start before `DEC-9`. |
| Release | NOT ASSESSED | No release evidence was supplied. |

**Next:** `BLOCK` — obtain the Data Council decision for `DEC-9` so `workspace-401` can start.
