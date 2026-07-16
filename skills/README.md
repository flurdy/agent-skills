# Shared Skills

| Skill | Description |
|-------|-------------|
| architect | Architecture and implementation planning gate for complex or high-blast-radius work; chooses a planning tier/model, evaluates alternatives and risks, and outputs an implementation-ready plan without editing code |
| backlog-groom | Per-bead quality audit over the open backlog — flags vague descriptions, missing acceptance criteria, label drift, stale YAGNIs, mis-prioritised nice-to-haves, obvious splits/epics, and duplicates. Read-only sweep; mutations apply only on approval, destructive ones confirmed one at a time. Delegates splitting to /triage and cross-system linking to /tracking-sweep (Jira) or /trello-beads (Trello) |
| beads-check-dolt-migration | Detect whether a beads installation needs migration from classic format (SQLite/JSONL) to Dolt |
| beads-migrate-to-dolt | Migrate a beads installation from classic format (SQLite/JSONL) to the new Dolt-based format |
| browser-screenshot | Take a screenshot of the running web application for visual verification of UI/CSS changes |
| circleci-status | Check CircleCI build status and failed job logs for the current GitHub repository |
| clean-code | Format, lint, and fix all warnings across the entire codebase |
| complete-task | Complete an in-progress task by running clean-code, staging, and committing; closes the bead in trunk repos or hands off to /create-pr in PR repos |
| confluence | Read Confluence pages and comments for design docs, ADRs, and runbooks |
| contract-check | Audit health of contract tests across services — staleness, sync gaps, uncommitted pacts, missing tests |
| contract-test | Run consumer-driven contract tests (pact-lite, no broker). Supports single-service and multi-service project-wide runs |
| create-pr | Create a pull request from the current branch following project conventions, and close the associated bead |
| eas-build-error | Show the status and errors from the latest EAS build |
| handoffs | Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full, summarises other repos by count. Companion to /wrap-up |
| handoffs-tidy | Prune handoffs that no longer point at live work — superseded (a newer handoff continues the thread), done (PR merged, all beads closed, branch landed, or Jira ticket Done), or stale (branch gone / PR closed) — so the /handoffs picker stays focused. Standalone twin of /handoffs's archive step; read-only until you confirm; archives, never deletes |
| jira-ticket | Look up Jira ticket details including summary, type, and description |
| landscape | Morning catch-up view — assigned Jira tickets, open PRs, in-progress/ready beads, and working-copy state in one glance |
| name-session | Derive a conventional Claude Code session name from the branch ticket, active bead, open PR, and what the session is doing — prints a paste-ready `/rename` line |
| next | Pick the next bead to work on. Modes: `safe` (skip busy services), `sprint` (sort by Jira sprint), `task`/`bug`/`quick` (auto-pick) |
| orchestrate | Safely coordinate bounded subagent delegation through explicit ownership, child-route consent, one-writer execution, independent review, and parent-owned validation; explicit invocation only |
| outstanding-work | Ticket-scoped, read-only blocker-first dashboard for unmet requirements, check evidence, working-copy state, tracking drift, and concrete untracked follow-ups |
| pedantic-review | Opinionated craft review of your own changes — flags rushed code, missed reuse, misplaced symbols, weak test deltas, and drift from project consensus |
| pr-status | Show enriched status of your open PRs — CI checks, approvals, and unresolved review threads |
| ready-to-merge | Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it |
| ready-to-release | Deep release-readiness gate for a single letterbox service — CI green, contracts in sync, deploy-order prereqs, feature toggle present, unpushed work vs the live deploy. Emits a gate table and a verdict |
| rebase-main | Rebase the current branch onto an updated main branch |
| rebase-merged-parent | Rebase after a parent PR has been merged to main |
| rebase-parent | Rebase the current branch onto an updated parent PR branch |
| release-manager | Interactive release gatekeeper for letterbox — prompts to push/defer/cancel each ready service, auto-files a bead on CI failure, enforces deploy order, watches rollouts, nudges toggles. Advisory: only pushes on explicit choice |
| release-status | Read-only release dashboard for letterbox — built-but-unpushed, pushed-but-not-rolled-out, deployed-but-toggle-off, and deploy-order blocks. Passive: never prompts or pushes |
| reply-comments | Reply to PR review comments after addressing them |
| review-comments | Address PR review comments from reviewers |
| review-pr | Review a pull request against the linked Jira ticket requirements |
| second-opinion | Query independent AI CLIs for reviews, plans, bugs, or code; supports an explicitly approved, bounded OpenRouter consensus panel for high-stakes decisions |
| setup-multirepo-git | Multi-repo git workflow rules and setup with mgit wrapper |
| stack-branch | Create a new branch stacked on another PR |
| start-ticket | Initialize work on a Jira ticket with a conventionally-named branch |
| tidy-settings | Sort, dedupe, and audit Claude `settings.json` / `settings.local.json` files at user and project level — flags risky permissions, broken refs, subsumed entries, and cross-section conflicts |
| total-review | Full pre-PR quality gauntlet — chains clean-code, verify-task, code-review, pedantic-review, /review, /security-review, and tiered /second-opinion. Halts on critical findings, emits beads for the rest |
| tracking-sweep | Portfolio-wide drift sweep across Jira, beads, and GitHub PRs — flags status drift, orphan work, parent-moved beads, and stale items. Read-only |
| trello-beads | Integrate Trello boards with Beads for project management bridging |
| triage | Create bead(s) from a user prompt or Jira ticket |
| verify-task | Verify that a task's implementation meets requirements and has adequate test coverage |
| watch-flux-rollout | After a push, watch a CircleCI + FluxCD deploy until it lands — CircleCI green for the commit, then the k8s Deployment's image tag moves off its pre-push baseline and pods go ready — then run a read-only smoke test. Goal-terminating; kubectl/CircleCI sister of /watch-rollout |
| watch-prs | Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence (fast ~3m when CI is in flight, backing off 10→30m when settled) until end of day, with transition-driven suggested next actions. Unattended; pass `\d+m` for a fixed interval |
| watch-release | Start a recurring release-gatekeeper loop — runs /release-manager on an adaptive cadence (fast ~3m when a push is mid-rollout or CI is running, backing off 10→30m when settled) until end of day. Pass `\d+m` for a fixed interval instead |
| watch-rollout | After a merge, watch the GitHub Actions deploy run until the gating job lands, then run a smoke test scoped to the change (browser for UI, GET for read-only API) against staging. Goal-terminating; staging by default, prod read-only opt-in. Generic GitHub-Actions cousin of /watch-release |
| wrap-up | End-of-session handoff — today's commits/PRs/beads, working-copy hygiene warnings (esp. for worktrees, incl. worktree-only settings drift), and a paste-ready resume block for the next session |

## Model routing

Semantic tiers and cost policies per skill; see [../MODEL_ROUTING.md](../MODEL_ROUTING.md)
for what each tier and policy value means. Sorted by tier, cheapest first.

| Skill | Tier | Cost policy | Metered policy | `model:` pin ¹ | Effort | Tier guard ² |
|-------|------|-------------|----------------|----------------|--------|--------------|
| beads-check-dolt-migration | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| browser-screenshot | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| circleci-status | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| confluence | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| jira-ticket | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| next | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| start-ticket | cheap-bulk | cheapest-adequate | cap-or-ask | haiku | medium |  |
| complete-task | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| contract-check | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| create-pr | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| eas-build-error | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| handoffs | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| handoffs-tidy | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | low |  |
| landscape | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| name-session | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | low |  |
| outstanding-work | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| pr-status | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| ready-to-merge | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| ready-to-release | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| release-manager | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| reply-comments | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| second-opinion ³ | standard-workflow | prefer-subscription-oauth | ask-before-metered-panel | sonnet | medium |  |
| stack-branch | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| trello-beads | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| triage | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| watch-flux-rollout | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| watch-prs ⁴ | standard-workflow | prefer-subscription-oauth | ask-above-standard | — | medium |  |
| watch-release | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| watch-rollout | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| wrap-up | standard-workflow | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| beads-migrate-to-dolt | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| clean-code | standard-coding | cheapest-adequate | cap-or-ask | opus | medium |  |
| contract-test | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| rebase-main | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| rebase-merged-parent | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| rebase-parent | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| review-comments | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| setup-multirepo-git | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | high |  |
| tidy-settings | standard-coding | prefer-subscription-oauth | ask-above-standard | opus | medium |  |
| backlog-groom | long-context-audit | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| release-status | long-context-audit | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| tracking-sweep | long-context-audit | prefer-subscription-oauth | ask-above-standard | sonnet | medium |  |
| architect | premium-reasoning | prefer-subscription-oauth | ask-above-standard | — | xhigh | ✅ |
| orchestrate ⁵ | premium-reasoning | prefer-subscription-oauth | ask-above-standard | — | high | ✅ |
| verify-task | premium-reasoning | prefer-subscription-oauth | ask-above-standard | — | xhigh | ✅ |
| pedantic-review | premium-review | deliberate-premium | ask-above-standard | — | xhigh | ✅ |
| review-pr | premium-review | deliberate-premium | ask-above-standard | — | xhigh | ✅ |
| total-review | premium-review | deliberate-premium | ask-above-standard | — | xhigh | ✅ |

¹ Claude Code-only enforcement hint (floating alias). Premium skills are deliberately
unpinned so they ride the best session model. Agent files never set it — pi honors
`model:` in agents, which would route pi to metered Claude.
² Premium skills open with a tier-guard prompt: on a sub-premium session model they
ask whether to continue at reduced depth or stop and switch.
³ Also declares `model-second-opinion-tier: independent-reasoning` for the external
CLI it invokes.
⁴ No pin: dynamic-loop ticks run on the session model regardless (`ScheduleWakeup`
wakeups ignore skill pins), so a pin there is unenforceable.
⁵ `orchestrate` deliberately uses `high` for routine parent coordination; `xhigh`
remains reserved for harder architecture, planning, and final review judgment.
