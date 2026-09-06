# Shared Skills

| Skill | Description |
|-------|-------------|
| architect | Read-only architecture and implementation planning with evidence-backed research, acceptance slices, and explicit tracking handoffs; never writes code or tracker records |
| artifact-hygiene | Run a local-only, read-only advisory audit of publishable files and unpublished branch history with isolated Gitleaks and redaction-safe findings |
| backlog-groom | Per-bead quality audit over the open backlog — flags vague descriptions, missing acceptance criteria, label drift, stale YAGNIs, mis-prioritised nice-to-haves, obvious splits/epics, and duplicates. Read-only sweep; mutations apply only on approval, destructive ones confirmed one at a time. Delegates splitting to /triage and cross-system linking to /tracking-sweep (Jira) or /trello-beads (Trello) |
| beads | Shared Beads workflow baseline for resolving the owning store, separating ephemeral checklists from durable tracking, routing focused operations, and confirming remote Dolt actions |
| beads-check-dolt-migration | Detect whether beads needs classic-to-Dolt migration or an in-place Dolt schema upgrade |
| beads-migrate-to-dolt | Migrate classic beads data to Dolt or safely upgrade an existing Dolt schema |
| browser-screenshot | Take a screenshot of the running web application for visual verification of UI/CSS changes |
| circleci-status | Check CircleCI build status and failed job logs for the current GitHub repository |
| clean-code | Format, lint, and fix all warnings across the entire codebase |
| complete-task | Complete an in-progress task by running clean-code, staging, and committing; closes on trunk, hands off to /create-pr in PR workflows, and protects detached commits |
| confluence | Read Confluence pages and comments for design docs, ADRs, and runbooks |
| contract-check | Audit health of contract tests across services — staleness, sync gaps, uncommitted pacts, missing tests |
| contract-test | Run consumer-driven contract tests (pact-lite, no broker). Supports single-service and multi-service project-wide runs |
| create-pr | Create a pull request from the current branch following project conventions, and close the associated bead |
| delegate-work | Dynamically coordinate bounded delegation for non-trivial work when independent investigation, separated implementation and review, or genuinely separable workstreams materially improve delivery |
| develop | Lightweight standard/high entry before authorized code changes, with one-way diagnosis, architecture, and premium implementation handoffs; best-effort routing, not a capability floor |
| diagnose-bug | Evidence-led, read-only bug diagnosis using minimal reproduction, boundary isolation, ranked hypotheses, and explicit falsification tests before proposing a fix |
| eas-build-error | Show the status and errors from the latest EAS build |
| handoffs | Browse handoff files saved by /wrap-up and pick one to resume. Lists this repo's handoffs in full, summarises other repos by count. Companion to /wrap-up |
| handoffs-tidy | Prune handoffs that no longer point at live work — superseded, done, stale, or old and wholly unclassified — and archive only what you confirm so the /handoffs picker stays focused. Archives, never deletes. |
| image-studio | Generate, compare, refine, and export image assets from one creative brief; Recraft-first with explicit, provider-neutral alternatives |
| implement-solution | Load before implementation-ready coding with interacting behavior, state/error paths, or local design trade-offs, including when ongoing work becomes complex; premium judgment and proportional TDD, not mechanical-edit ceremony |
| jira-comment | Draft and post a terse house-style comment on a Jira ticket after confirmation |
| jira-ticket | Look up Jira ticket details including summary, type, and description |
| landscape | Morning catch-up view — assigned Jira tickets and recent discussion, open PRs, in-progress/ready beads, and working-copy state in one glance |
| model-update-check | Read-only audit of Pi routing and configured second-opinion panel model IDs against the active Pi catalog and public live metadata; reports evidence-backed update candidates without editing config |
| name-session | Derive a conventional session name from the branch ticket, active bead, open PR, and current work — prints the active client's paste-ready rename command |
| next | Globally rank ready beads across validated workspace stores, isolating failed sources with local fallback. Modes: `safe`, `sprint`, `task`, `bug`, `quick` |
| outstanding-work | Ticket-scoped, read-only blocker-first dashboard for unmet requirements, check evidence, working-copy state, tracking drift, and concrete untracked follow-ups |
| pedantic-review | Read-only craft and test-design review; requirements, coverage sufficiency, execution, and fixes stay with their separate owners |
| pi-spend | Read-only estimate of Pi model cost by provider and model for today, this week, this month, and all recorded history, separating metered credit usage from flat-rate subscription usage |
| plan-to-backlog | Dynamically materialize an explicitly approved plan into proposal-first Beads tracking when durable ownership is requested, with no-item/single-item/epic outcomes and explicit confirmation before writes |
| pr-status | Show enriched status of your open PRs — CI checks, approvals, unresolved review threads, and linked Jira discussion |
| project-brief | Read-only workspace-level synthesis of project outcomes, requirement linkage, delivery evidence, coordination risks, and the single most important next coordination action |
| ready-to-merge | Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it |
| ready-to-release | Shared read-only release authority — collects evidence, evaluates gates, and renders one service's verdict |
| rebase | Rebase onto updated main, an updated stacked parent, or main after the parent merged — proves the child-only range before rewriting; explicit dirty-tree, test, force-push, and retarget gates |
| rebase-main | Alias for `/rebase main` |
| rebase-merged-parent | Alias for `/rebase merged {old-parent}` |
| rebase-parent | Alias for `/rebase parent {parent-branch}` |
| release-maintenance | Explicitly invoked, separately confirmed manifest reconciliation, config synchronization, restart, or rollout acknowledgement; never runs inside a watch tick |
| release-manager | Attended push gatekeeper consuming shared readiness verdicts; current-command confirmation, CI tracking, rollout observation, and cadence |
| release-status | Read-only dashboard consuming the shared release authority, including blockers and separate activation follow-ups |
| reply-comments | Publish prepared PR-feedback outcomes through separate confirmed push, reply, and inline-thread resolution gates with race and duplicate protection |
| review-comments | Select and independently validate PR feedback, make focused verified local fixes, reopen its bead after a committed fix, and commit locally without publishing remote actions |
| review-pr | Review a pull request against the linked Jira ticket requirements |
| second-opinion | Independent advisory claims from one peer or a configured panel; PR evidence uses pinned snapshots and explicit stale-safety checks |
| setup-multirepo-git | Multi-repo git workflow rules and setup with mgit wrapper |
| stack-branch | Create a new branch stacked on another PR |
| start-ticket | Initialize work on a Jira ticket with a conventionally-named branch |
| thoughtbox | Retrieve repository-scoped Thoughtbox Inbox captures, prepare a hostile-text-safe handoff to `/triage`, and render separately confirmed scoped resolution commands without executing either workflow |
| tidy-settings | Sort, dedupe, and audit Claude `settings.json` / `settings.local.json` files at user and project level — flags risky permissions, broken refs, subsumed entries, and cross-section conflicts |
| today | Read-only same-day or previous-workday activity recap; owns shared rendering, with current-session context in same-day mode |
| token-dashboard | Read-only current-session and UTC-week token telemetry for Pi, Claude Code, Codex, and optional OpenRouter management analytics; normalized JSON and terminal views without transcript or credential output |
| total-review | Portable pre-PR gauntlet with revision-bound evidence, explicit manual/missing review coverage, optional independent reviewers, and at most two fix/review passes |
| tracking-sweep | Portfolio-wide drift sweep across Jira, beads, and GitHub PRs — flags status drift, orphan work, parent-moved beads, and stale items. Read-only |
| trello-beads | Integrate Trello boards with Beads for project management bridging |
| triage | Create/refine beads from raw requests or Jira, or own explicitly requested blocked human decisions; approved implementation plans go to plan-to-backlog |
| verify-task | Verify explicit requirements and coverage against a fixed scope using discovered repository-native gates; report missing, failed, or stale evidence without repairs |
| watch-actions-rollout | After a merge, watch the GitHub Actions deploy run until the gating job lands, then run a confirmed read-only smoke test scoped to the change. Goal-terminating; staging by default, production read-only opt-in |
| watch-flux-rollout | After a push, watch CircleCI and FluxCD until the exact commit is built, the Kubernetes image changes, and pods are ready, then run a confirmed read-only smoke test. Goal-terminating |
| watch-pr-feedback | Watch open PRs for normalized feedback, independently validate each new or edited actionable item once, and render a bounded decision queue. Read-only by default; attended mode pauses only for acknowledgment |
| watch-prs | Start a recurring PR status dashboard — runs /pr-status on an adaptive cadence (fast ~3m when CI is in flight, backing off 10→30m when settled) until end of day, with transition-driven suggested next actions. Unattended; pass `\d+m` for a fixed interval |
| watch-release | Start a recurring release-gatekeeper loop — runs /release-manager on an adaptive cadence (fast ~3m when a push is mid-rollout or CI is running, backing off 10→30m when settled) until end of day. Pass `\d+m` for a fixed interval instead |
| watch-review-requests | Watch direct inbound GitHub review requests, run one bounded repository-qualified review at a time, and pause for private, draft-only, deferred, or separately confirmed external dispositions |
| watch-rollout | Choose between implemented rollout stacks, then delegate unchanged arguments to the GitHub Actions or CircleCI/Flux specialist without weakening stack-specific safety |
| wrap-up | End-of-session handoff — today's commits/PRs/beads, working-copy hygiene warnings (esp. for worktrees, incl. worktree-only settings drift), and a paste-ready resume block for the next session |
| yesterday | Alias for `/today --previous-workday`: objective previous-workday recap; selects Friday when run on Monday |

## Model routing

Shared skills declare a portable capability tier and reasoning effort. See
[`MODEL_ROUTING.md`](../MODEL_ROUTING.md) for the allowed values, runtime
ownership boundaries, and authoring guidance.
