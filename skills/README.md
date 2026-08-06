# Shared Skills

| Skill | Description |
|-------|-------------|
| architect | Architecture and implementation planning gate for complex or high-blast-radius work; adds conditional, evidence-backed Adopt/Extend/Compose/Build research to reviewable slices, acceptance evidence, and tracking recommendations without editing code |
| artifact-hygiene | Run a local-only, read-only advisory audit of publishable files and unpublished branch history with isolated Gitleaks and redaction-safe findings |
| backlog-groom | Per-bead quality audit over the open backlog — flags vague descriptions, missing acceptance criteria, label drift, stale YAGNIs, mis-prioritised nice-to-haves, obvious splits/epics, and duplicates. Read-only sweep; mutations apply only on approval, destructive ones confirmed one at a time. Delegates splitting to /triage and cross-system linking to /tracking-sweep (Jira) or /trello-beads (Trello) |
| beads | Shared Beads workflow baseline for resolving the owning store, separating ephemeral checklists from durable tracking, routing focused operations, and confirming remote Dolt actions |
| beads-check-dolt-migration | Detect whether beads needs classic-to-Dolt migration or an in-place Dolt schema upgrade |
| beads-migrate-to-dolt | Migrate classic beads data to Dolt or safely upgrade an existing Dolt schema |
| browser-screenshot | Take a screenshot of the running web application for visual verification of UI/CSS changes |
| circleci-status | Check CircleCI build status and failed job logs for the current GitHub repository |
| clean-code | Format, lint, and fix all warnings across the entire codebase |
| complete-task | Complete an in-progress task by running clean-code, staging, and committing; closes the bead in trunk repos or hands off to /create-pr in PR repos |
| confluence | Read Confluence pages and comments for design docs, ADRs, and runbooks |
| contract-check | Audit health of contract tests across services — staleness, sync gaps, uncommitted pacts, missing tests |
| contract-test | Run consumer-driven contract tests (pact-lite, no broker). Supports single-service and multi-service project-wide runs |
| create-pr | Create a pull request from the current branch following project conventions, and close the associated bead |
| delegate-work | Dynamically coordinate bounded delegation for non-trivial work when independent investigation, separated implementation and review, or genuinely separable workstreams materially improve delivery |
| diagnose-bug | Evidence-led, read-only bug diagnosis using minimal reproduction, boundary isolation, ranked hypotheses, and explicit falsification tests before proposing a fix |
| eas-build-error | Show the status and errors from the latest EAS build |
| handoffs | Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full, summarises other repos by count. Companion to /wrap-up |
| handoffs-tidy | Prune handoffs that no longer point at live work — superseded, done, stale, or old and wholly unclassified — and archive only what you confirm so the /handoffs picker stays focused. Archives, never deletes. |
| image-studio | Generate, compare, refine, and export image assets from one creative brief; Recraft-first with explicit, provider-neutral alternatives |
| implement-solution | Premium workflow for non-trivial, implementation-ready coding where material local trade-offs justify repository-pattern discovery, proportional TDD, and explicit KISS/YAGNI judgment |
| jira-ticket | Look up Jira ticket details including summary, type, and description |
| landscape | Morning catch-up view — assigned Jira tickets and recent discussion, open PRs, in-progress/ready beads, and working-copy state in one glance |
| model-update-check | Read-only audit of Pi routing and configured second-opinion panel model IDs against the active Pi catalog and public live metadata; reports evidence-backed update candidates without editing config |
| name-session | Derive a conventional session name from the branch ticket, active bead, open PR, and current work — prints the active client's paste-ready rename command |
| next | Globally rank ready beads across validated workspace stores, isolating failed sources with local fallback. Modes: `safe`, `sprint`, `task`, `bug`, `quick` |
| outstanding-work | Ticket-scoped, read-only blocker-first dashboard for unmet requirements, check evidence, working-copy state, tracking drift, and concrete untracked follow-ups |
| pedantic-review | Opinionated craft review of your own changes — flags rushed code, missed reuse, misplaced symbols, weak test deltas, and drift from project consensus |
| pi-spend | Read-only estimate of Pi model cost by provider and model for today, this week, this month, and all recorded history, separating metered credit usage from flat-rate subscription usage |
| plan-to-backlog | Dynamically materialize an explicitly approved plan into proposal-first Beads tracking when durable ownership is requested, with no-item/single-item/epic outcomes and explicit confirmation before writes |
| pr-status | Show enriched status of your open PRs — CI checks, approvals, unresolved review threads, and linked Jira discussion |
| project-brief | Read-only workspace-level synthesis of project outcomes, requirement linkage, delivery evidence, coordination risks, and the single most important next coordination action |
| ready-to-merge | Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it |
| ready-to-release | Deep release-readiness gate for a single letterbox service — CI green, contracts in sync, deploy-order prereqs, feature toggle present, unpushed work vs the live deploy. Emits a gate table and a verdict |
| rebase-main | Rebase the current branch onto an updated main branch |
| rebase-merged-parent | Rebase after a parent PR has been merged to main |
| rebase-parent | Rebase the current branch onto an updated parent PR branch |
| release-manager | Interactive release gatekeeper for letterbox — prompts to push/defer/cancel each ready service, auto-files a bead on CI failure, enforces deploy order, watches rollouts, nudges toggles. Advisory: only pushes on explicit choice |
| release-status | Read-only release dashboard for letterbox — built-but-unpushed, pushed-but-not-rolled-out, deployed-but-toggle-off, and deploy-order blocks. Passive: never prompts or pushes |
| reply-comments | Publish prepared PR-feedback outcomes through separate confirmed push, reply, and inline-thread resolution gates with race and duplicate protection |
| review-comments | Select and independently validate PR feedback, make focused verified local fixes, and commit locally without publishing remote actions |
| review-pr | Review a pull request against the linked Jira ticket requirements |
| second-opinion | Query one independent peer or configurable local/OpenRouter panels with distinct quorum and evidence-backed consensus policies |
| setup-multirepo-git | Multi-repo git workflow rules and setup with mgit wrapper |
| stack-branch | Create a new branch stacked on another PR |
| start-ticket | Initialize work on a Jira ticket with a conventionally-named branch |
| tidy-settings | Sort, dedupe, and audit Claude `settings.json` / `settings.local.json` files at user and project level — flags risky permissions, broken refs, subsumed entries, and cross-section conflicts |
| today | Read-only same-day catch-up across the current conversation and objective commits, PRs, Jira touches, and Beads activity in validated workspace repositories |
| token-dashboard | Read-only current-session and UTC-week token telemetry for Pi, Claude Code, Codex, and optional OpenRouter management analytics; normalized JSON and terminal views without transcript or credential output |
| total-review | Full pre-PR quality gauntlet — chains clean-code, verify-task, code-review, pedantic-review, /review, /security-review, and tiered /second-opinion. Halts on critical findings, emits beads for the rest |
| tracking-sweep | Portfolio-wide drift sweep across Jira, beads, and GitHub PRs — flags status drift, orphan work, parent-moved beads, and stale items. Read-only |
| trello-beads | Integrate Trello boards with Beads for project management bridging |
| triage | Create bead(s) from a user prompt or Jira ticket |
| verify-task | Verify that a task's implementation meets requirements and has adequate test coverage |
| watch-admin | Retained no-go implementation of a bounded Pi workspace/Jira watcher; its rollout guard stops before scheduling after the fresh-session input-token gate failed |
| watch-flux-rollout | After a push, watch a CircleCI + FluxCD deploy until it lands — CircleCI green for the commit, then the k8s Deployment's image tag moves off its pre-push baseline and pods go ready — then run a read-only smoke test. Goal-terminating; kubectl/CircleCI sister of /watch-rollout |
| watch-pr-feedback | Watch open PRs for normalized feedback, independently validate each new or edited actionable item once, and render a bounded decision queue. Read-only by default; attended mode pauses only for acknowledgment |
| watch-prs | Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence (fast ~3m when CI is in flight, backing off 10→30m when settled) until end of day, with transition-driven suggested next actions. Unattended; pass `\d+m` for a fixed interval |
| watch-release | Start a recurring release-gatekeeper loop — runs /release-manager on an adaptive cadence (fast ~3m when a push is mid-rollout or CI is running, backing off 10→30m when settled) until end of day. Pass `\d+m` for a fixed interval instead |
| watch-review-requests | Watch direct inbound GitHub review requests, run one bounded repository-qualified review at a time, and pause for private, draft-only, deferred, or separately confirmed external dispositions |
| watch-rollout | After a merge, watch the GitHub Actions deploy run until the gating job lands, then run a smoke test scoped to the change (browser for UI, GET for read-only API) against staging. Goal-terminating; staging by default, prod read-only opt-in. Generic GitHub-Actions cousin of /watch-release |
| wrap-up | End-of-session handoff — today's commits/PRs/beads, working-copy hygiene warnings (esp. for worktrees, incl. worktree-only settings drift), and a paste-ready resume block for the next session |
| yesterday | Read-only previous-workday stand-up recap across objective commits, PRs, Jira touches, and Beads activity; selects Friday when run on Monday |

## Model routing

Shared skills declare a portable capability tier and reasoning effort. See
[`MODEL_ROUTING.md`](../MODEL_ROUTING.md) for the allowed values, runtime
ownership boundaries, and authoring guidance.
