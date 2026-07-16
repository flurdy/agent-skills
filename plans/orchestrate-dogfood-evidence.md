# Orchestrate dogfood evidence

## Scope

- Bead: `skills-88v.2`
- Started: 2026-07-15
- Implementation under test: commit `77bef1f`
- Repository workflow: direct commits on `main`
- Evidence policy: prefer observed runtime evidence; label synthetic decision-table checks and unavailable scenarios explicitly.

This log tests the portable `/orchestrate` policy without parsing model-tier-router
configuration, changing runtime agent settings, persisting ad hoc consent, or creating
tracker items for individual children/reviews/retries.

## Baseline runtime facts

| Fact | Evidence | Result |
|---|---|---|
| Runtime versions | Local CLI capability check | Pi `0.80.6`; Claude Code `2.1.207`; Codex CLI `0.144.3`. Versions are evidence, not behavior gates. |
| Pi parent model | `subagent({ action: "models" })` | `openai-codex/gpt-5.6-sol` |
| Pi builtin routing | Same model report | All eight executable builtin roles inherit the parent model; no downshift is configured or claimed. |
| Pi executable roles | `subagent({ action: "list" })` | `context-builder`, `delegate`, `oracle`, `planner`, `researcher`, `reviewer`, `scout`, `worker` |
| Trusted Pi policy | User instruction-channel check | `~/.pi/agent/AGENTS.md` absent; no trusted Pi child cost declaration supplied. |
| Trusted Claude policy | User instruction-channel check | `~/.claude/CLAUDE.md` contains no `orchestrate-child-policy` or metered declaration. |
| Trusted Codex policy | User instruction-channel check | `$CODEX_HOME/AGENTS.md` and `AGENTS.override.md` absent. |
| Repository text | `CLAUDE.local.md` inspection | Contains workflow preferences only. Even a repository claim would not independently establish child billing classification. |
| Control-plane index | Targeted filename search | None present. Orchestration remains usable without one. |
| Claude native capability | Local CLI help | Current CLI exposes agent definitions plus model and effort controls; no child launch yet. |
| Codex native capability | `codex features list` and agent-directory check | `multi_agent` reports stable/enabled; no user or project custom agent mapping is present. Capability is detected, not version-gated. |
| Tracker context | `bd show skills-88v.2` | One relevant durable bead is in progress; no per-child tracker items were created. |

## Scenario evidence

| Scenario | Evidence type | Route/classification | Outcome | Metrics / notes |
|---|---|---|---|---|
| Pi discovery before execution | Observed | Inherited parent route | Used only executable, non-disabled builtin roles. | Discovery and model report completed before launch. |
| Unknown inherited child disclosure | Observed | Effective identity visible as `openai-codex/gpt-5.6-sol`; `metered` unknown | Disclosed inherited/no-downshift behavior and requested separate current-run consent. | No model override supplied. |
| Bounded unknown-classification panel | Observed | Two inherited Pi children; unknown metered status | User approved one current-run-only panel: fresh `reviewer` + fresh `context-builder`, both read-only. Both completed without model override. | Async run `30fe92bb-06f6-4c16-825b-cc1b3d8a26f4`; concurrency 2; panel wall time 243.3s. Reviewer: high effort, 4 turns, 17 tool calls, 47,396 input / 9,191 output tokens. Context-builder: medium effort, 11 turns, 34 tool calls, 51,360 input / 6,407 output tokens. Runtime-reported estimated costs were 0.545478 and 0.583154, but do not establish trusted metered classification. Both runtime acceptance gates rejected because the required structured acceptance report was omitted. |
| Parent/panel consent not reused | Observed | Proposed inherited `worker`; unknown metered status | Asked separately despite panel approval. User declined. | Confirms panel approval did not authorize a writer or broader fanout. |
| Declined child / serial fallback | Observed | Proposed inherited `worker`; unknown metered status | No worker launched. Parent writes this evidence log serially. | Disclosed fallback; validation is self-validation until the approved independent panel returns. |
| Ad hoc consent persistence | Observed | Panel-only consent | No settings, instruction, agent, or policy file was written. | Consent remains scoped to the named panel/run ID. |
| Tracker portability | Observed | Active Beads repository with relevant bead | Used `skills-88v.2` as durable context only. | No `/triage`; no ephemeral child/review/retry beads. |
| Optional control-plane context | Observed unavailable | No index present | Continued without creating or requiring one. | Expected portable fallback. |
| Verified unmetered decision path | Static policy check | Fixture: verified identity + `metered: false` | Expected action is launch inside approved task scope without an additional cost prompt. | Not launched: no trusted real mapping was supplied. |
| Verified metered decision path | Static policy check | Fixture: verified identity + `metered: true` | Expected action is a current-run child/panel confirmation. | Not launched: no trusted real metered mapping was supplied. |
| Conditional mapped Pi route | Environment unavailable | Requires effective identity + trusted metered declaration | Correctly not attempted; no resolver config was parsed and no override was invented. | Gap remains until the user/runtime supplies trusted mapping evidence. |
| Bounded cheaper writer exception | Environment unavailable | Requires a verified cheaper writer mapping plus full packet | Correctly not attempted. The only proposed writer inherited the premium parent and was declined. | No claim that the exception was exercised. |
| Fresh independent review | Observed | Initial fresh reviewer inherited Sol; focused follow-up inherited Luna after the parent was routed to Luna; metered status unknown | The initial reviewer found one high temporal identity gap, one medium project-scope ambiguity, and two low portability/staleness notes. Parent fixed them serially. Codex and Claude native child reviews added portability findings. The focused post-fix Pi reviewer returned PASS for all five requested checks and no blocker. Session evidence shows the parent changed from Sol to Luna at `09:34:46Z` immediately after reading the cheap-bulk migration skill, and the reviewer correctly inherited Luna at `09:41:19Z`; the parent restored Sol at `09:43:22Z`. | The earlier Sol model report was stale, not a Pi reporting defect. The user had approved a Sol-inherited follow-up, so the intervening route change should have triggered fresh disclosure/consent before the Luna launch. No later child launch reused that stale preflight. The wrapper rejection was separately traced to string `acceptance: "none"`, which cannot lower inferred reviewed acceptance without an explicit reason object. |
| Pi model restoration | Observed | Parent began on `openai-codex/gpt-5.6-sol`; a later cheap-bulk skill read routed it to `gpt-5.6-luna` at medium effort | The initial panel restored/remained Sol. Session lifecycle records show the later Luna route restored to Sol at `09:43:22Z` after the focused review settled; a later Terra route also restored to Sol. | Restoration worked. The important failure was orchestration using stale pre-route disclosure, not failure to restore. |
| Cheap-bulk medium baseline | Observed | Explicit Pi process with `beads-check-dolt-migration`, medium thinking; route identity not exposed in output | Completed read-only in 96.864s; correctly reported Dolt backend, `bd 0.62.0`, no sync branch/worktree, and no migration needed. | Tool-call count and quota were not observable from the one-shot output. This is one successful baseline, insufficient to recommend low effort. |
| Claude native delegation | Observed after correcting test invocation | No trusted child classification available; child inherited parent with no claimed downshift | The first attempt incorrectly used `--bare`, which intentionally skips normal OAuth/keychain auth and therefore reported `Not logged in`; normal `claude -p ping` proved the stored login was healthy. Retrying without `--bare` launched exactly one bounded read-only `reviewer` child and completed without edits/network use. | 157.792s wall time; parent and child reported `claude-fable-5`; child used 3 tools and about 27k tokens; effort was not observable. Initial auth failure was harness misuse, not missing user authentication. |
| Codex native delegation | Observed | Native multi-agent; parent/child model and effort not observable; billing classification unknown | Exactly one native `explorer` child launched and completed under read-only sandbox. Child reported no high-severity findings; it found two medium and two low findings. | Codex parent output reported `gpt-5.5`, medium effort, 75.963s wall time, 36,676 tokens. Child effective model/effort was not observable. |
| No-subagent serial fallback | Policy/static plus declined-child observation | Delegation unavailable or declined | Parent continues and labels self-validation honestly. | Actual declined-child path observed; unavailable-runtime simulation still optional. |

## Metrics schema

For each real launch, record when observable:

- Wall-clock duration and concurrency
- Effective child model and effort, distinguishing reported identity from assumed mapping
- Trusted metered classification or `unknown`
- Consent prompts and whether consent was bounded, expanded, or declined
- First-pass completion against the packet
- Retries/corrections and validation reruns
- Tool-call count or closest runtime evidence
- Observable quota/cost signal, otherwise `not observable`
- Independent-review result and residual risks

Do not recommend `low` effort merely because a task succeeded. Require repeated,
comparable evidence of meaningful latency/quota savings without reliability,
correction, or validation regression.

## Review-driven corrections

The first fresh reviewer exposed four policy/documentation issues. The parent fixed
them serially because the separately proposed writer was declined. A second native
Codex child review exposed two additional portability clarifications, also fixed
serially:

1. **Temporal identity gap:** an alias or route whose effective identity is available
   only after launch is now classified unknown and consented before exposure. Launch
   mismatch stops further fanout and requires re-gating.
2. **Project scope ambiguity:** a durable project-scoped policy must include a stable
   project identity or absolute root; `scope: project` alone is insufficient.
3. **Portable prompting:** the tier guard now asks through the runtime's native
   question mechanism rather than treating Claude's tool name as universal.
4. **Stale plan action:** the plan now points to the active dogfood bead rather than
   the completed implementation bead.
5. **Unknown model guard:** the tier guard now discloses inability to verify the
   current model and asks through the native runtime mechanism instead of claiming a
   premium guard result.
6. **Claude policy loading:** project-scoped local policy must be verified as loaded
   in the active Claude session before it is trusted.

7. **Immediate Pi preflight:** discovery/model reporting must be repeated immediately
   before every launch and after any skill read/router event. The stale Sol report was
   superseded when reading a cheap-bulk skill routed the parent to Luna; the follow-up
   correctly inherited Luna, but the changed route required fresh disclosure/consent.
8. **Pi acceptance disable form:** current `pi-subagents` intentionally refuses to
   let string `acceptance: "none"` lower an inferred stronger gate. A prose-only review
   must pass an explicit object with a non-empty reason; otherwise satisfy the inferred
   structured evidence contract.
9. **Additional portability:** the adapter now defines an other-runtime serial
   fallback and a cheap/balanced/strong semantic bridge. The main skill no longer
   relies on a repository-relative policy link that may break when copied alone, and
   parent-route cost policy is explicitly separate from child billing classification.

The panel's outputs were useful, but the runtime acceptance wrappers reported
`rejected` because the children did not emit generic structured evidence. The focused
post-fix reviewer substantively passed all five checks and found no blocker; source
inspection showed that the string `"none"` is not an explicit disable. Record this as
an invocation/documentation mismatch, not an acceptance-engine defect; future
prose-only review packets must use `{ level: "none", reason: "..." }` or satisfy the
runtime's inferred acceptance schema.

## Interim conclusions

1. Pi v1 honestly inherits the current parent model when no verified child mapping is
   supplied; model reporting made that visible before launch.
2. Unknown billing classification triggered separate consent even though the child
   identity was observable.
3. Bounded panel consent was not reused for a writer. The declined writer produced a
   real serial-fallback case without persisting policy.
4. Trusted-policy absence and arbitrary repository context were handled conservatively.
5. Tracker and control-plane behavior stayed portable and low-noise.
6. The first review caught a real pre-launch identity/cost defect, demonstrating why
   fresh review is required. The follow-up exposed two orchestration mistakes rather
   than Pi execution defects: stale model preflight after a parent route change, and
   use of the non-disabling string `acceptance: "none"` shorthand.
7. Verified mapped and cheaper-writer evidence remains unavailable. Cheap-bulk,
   Claude, and Codex runs produced useful but incomplete evidence and do not justify a
   new low-effort exception yet.
