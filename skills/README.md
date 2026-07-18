# Shared Skills

| Skill | Description |
|-------|-------------|
| architect | Architecture and implementation planning gate for complex or high-blast-radius work; adds conditional, evidence-backed Adopt/Extend/Compose/Build research to reviewable slices, acceptance evidence, and tracking recommendations without editing code |
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
| diagnose-bug | Evidence-led, read-only bug diagnosis using minimal reproduction, boundary isolation, ranked hypotheses, and explicit falsification tests before proposing a fix |
| eas-build-error | Show the status and errors from the latest EAS build |
| handoffs | Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full, summarises other repos by count. Companion to /wrap-up |
| handoffs-tidy | Prune handoffs that no longer point at live work — superseded (a newer handoff continues the thread), done (PR merged, all beads closed, branch landed, or Jira ticket Done), or stale (branch gone / PR closed) — so the /handoffs picker stays focused. Standalone twin of /handoffs's archive step; read-only until you confirm; archives, never deletes |
| jira-ticket | Look up Jira ticket details including summary, type, and description |
| landscape | Morning catch-up view — assigned Jira tickets, open PRs, in-progress/ready beads, and working-copy state in one glance |
| model-update-check | Read-only audit of Pi routing and second-opinion consensus model IDs against the active Pi catalog and public live metadata; reports evidence-backed update candidates without editing config |
| name-session | Derive a conventional Claude Code session name from the branch ticket, active bead, open PR, and what the session is doing — prints a paste-ready `/rename` line |
| next | Pick the next bead to work on. Modes: `safe` (skip busy services), `sprint` (sort by Jira sprint), `task`/`bug`/`quick` (auto-pick) |
| orchestrate | Safely coordinate bounded delegation while preserving observable outcome → acceptance-evidence pairs through writer, reviewer, and parent validation; explicit invocation only |
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
| simplify-solution | Apply a lightweight common-sense YAGNI/KISS lens to find the smallest maintainable implementation before or during ordinary coding |
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

Shared skills declare a portable capability tier and reasoning effort. See
[`MODEL_ROUTING.md`](../MODEL_ROUTING.md) for the allowed values, runtime
ownership boundaries, and authoring guidance.
