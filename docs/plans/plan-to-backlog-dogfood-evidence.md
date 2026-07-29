# Plan-to-backlog decision and dogfood evidence

## Scope

- Work item: `agents-vqy.3`
- Date: 2026-07-29
- Implementation under test: local `agent-skills` commit `15ca359` plus the fixture and portability changes in this work item
- Installed path: `~/.agents/skills/plan-to-backlog`
- Evidence policy: frozen scenarios exercise a deterministic policy oracle; the epic conversion is observed against the workspace Beads store

## Frozen decision scenarios

`skills/plan-to-backlog/tests/fixtures/decision-scenarios.json` and
`decision-boundary-scenarios.json` freeze fourteen inputs, expected proposals, and
lifecycle results. `test_decision_fixtures.py` derives readiness and disposition from the
fixture evidence, verifies exact write/ledger/recovery correlation, traceability, and epic
boundaries, and rejects unsafe mutations or duplicate-producing recovery.

| Scenario | Expected decision | Mutation evidence |
|---|---|---|
| Existing complete owner | `ready / no-item` | Empty write set; owner reused |
| Mechanical five-step plan with one outcome | `ready / single-item` | One item; no step children |
| Three independently closable outcomes | `ready / epic` | Bounded owner conversion, three children, acceptance-backed blocker |
| Two tightly coupled outcomes | `ready / single-item` | Coupled work collapses to one owner |
| Two cross-repository shippable outcomes | `ready / epic` | Two children only with distinct repositories and evidenced aggregate ownership |
| Flat authoritative owner plus duplicate | `ready / no-item` | Authoritative owner reused; duplicate skipped |
| Existing authoritative and duplicate trees | `ready / no-item` | Every authoritative tree node reused; duplicate tree skipped |
| Partially materialized tree | `ready / epic` | Existing refs reused; only missing child and blocker proposed |
| Ambiguous ownership boundary | `needs-clarification` | Confirmation unavailable; empty write set |
| Unapproved plan | `needs-clarification` | Confirmation unavailable; empty write set |
| Declined single-item proposal | `ready / single-item` | Proposal retained; observed writes empty; ledger says declined |
| Synthetic mid-apply failure and rerun | `ready / epic` | Exact ledger; successful IDs preserved; failed/skipped operations only are retried |
| Mechanical plan sequence | `ready / epic` | Parent edges only; no blocking edge |
| More than six candidates | `needs-clarification` | No unbounded proposal or writes |

Negative checks mutate the evidence to remove a skipped recovery edge, change a recovered
parent or blocker endpoint, omit an observed successful call, add an unproposed action or
ledger row, duplicate or forge read-only ledger refs, attach an ID to a failed result,
remove authoritative-tree topology/reuse evidence, retarget a blocker away from the source
acceptance dependency, or recreate a successful ref. Each mutation invalidates the fixture.

## Real dogfood source

The user explicitly selected the approved `agents-t9a` plan in the current run.
The consumed logical text was the Bead description and acceptance criteria under stable
headings, normalized as UTF-8/LF with one trailing newline.

| Field | Value |
|---|---|
| Source | `agents-t9a` |
| Source SHA-256 | `5a7690dcde61de04b020a23f7feccebe7e9d8e148bf1c21fb86d747764d4c9b9` |
| Initial owner type | `feature` |
| Initial children | none |
| Proposal | `ab2c0a4d0e3b8b06f110733bb81863ad488cd9c86f853bdabf28e6ec4700a62a` |
| Disposition | `epic` |
| Confirmation | Explicit **Apply exact proposal** selection in the current run |

Targeted title, source, and outcome searches found `agents-t9a` as the only complete owner.
`agents-6mz` was related workspace-status UX, not a duplicate. No item carried the source
fingerprint before apply.

## Proposed versus created mapping

| Proposal ref | Proposed action | Actual ID | Result |
|---|---|---|---|
| `owner` | Convert existing owner to epic | `agents-t9a` | Updated |
| `child-1` | Create globally ranked cross-store listing outcome | `agents-t9a.1` | Created with parent and source metadata |
| `child-2` | Create owner-routed selection outcome | `agents-t9a.2` | Created with parent and source metadata |
| `child-3` | Create fallback/source-isolation outcome | `agents-t9a.3` | Created with parent and source metadata |
| blocker 1 | `child-2` blocked by `child-1` | `agents-t9a.2 → agents-t9a.1` | Added |
| blocker 2 | `child-3` blocked by `child-1` | `agents-t9a.3 → agents-t9a.1` | Added |

Each create was preceded immediately by a matching guarded dry-run. Every mutation went
through `confirmed-bd.sh` with the same proposal and confirmation fingerprints. The two
blocking edges encode acceptance dependencies: selection needs owning-store identity, and
partial-source isolation needs aggregate collection that can retain healthy stores. They
do not encode implementation order.

Post-apply reads confirmed:

- `agents-t9a` is an epic with exactly three children;
- every child has `plan_source`, `plan_source_sha256`, and a unique
  `plan_proposal_ref`;
- parent and blocking relationships match the proposal; and
- the source-fingerprint query returns exactly those three created children.

A complete read-only rerun repeated the source hash, metadata, locator, outcome, and graph
queries. It mapped `owner`, `child-1`, `child-2`, and `child-3` to the existing IDs and
rendered `ready / no-item` with an empty logical write set. The rerun proposal fingerprint
was `8ed297e2a7679ae62b0b3e0e85f86ea090d9e40447f2e092d03790875b25297e`;
no confirmation was offered and no mutation helper was invoked.

## Portability observations

1. Beads 1.1.2 (Homebrew) rejects queryless `bd search --metadata-field ...`, even
   though metadata filters are accepted flags. The dogfood used the supported query-free
   `bd list --metadata-field ... --status open,in_progress,blocked,deferred,closed --json`
   form, and the skill now documents that form.
2. `bd create --dry-run --json` validates fields but returns an empty ID. Runtime-created
   IDs must therefore come from successful create results and be resolved through the
   apply ledger; they cannot be predicted during preview.
3. Bead-source hashing still requires an explicit, repeatable choice of consumed fields.
   This run used description plus acceptance criteria under fixed headings. Different
   clients or connectors must preserve the same logical text and recorded normalization
   to reproduce the source fingerprint.
4. The confirmed helper depends on Beads support for JSON metadata, dry-run creates,
   parent assignment, type updates, and `blocks` dependencies. Unsupported capabilities
   block the affected operation rather than widening the mutation surface.
5. Beads writes are not transactional. Partial-failure behavior is fixture-backed rather
   than induced against the real backlog; recovery must preserve successful IDs and
   require a new duplicate-aware proposal.

## Validation

The focused target includes shell helper tests, static skill-contract checks, and twenty
Python fixture tests:

```text
make test-plan-to-backlog
```

Repository completion also requires:

```text
make clean-code
make validate-skills
make test-validate-skills
make test-assemble
make dry-run
make doctor
git diff --check
```
