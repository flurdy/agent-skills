# Shared Skills

Skills are grouped by primary use. A skill that genuinely serves two use cases also appears
under a second topic with the same description. Rows are alphabetical within each topic.

## Orientation and daily planning

| Skill | Description |
|-------|-------------|
| landscape | Read-only full/quick orientation or compact local `resume` mode; suggests resume-or-next without loading handoffs or claiming work |
| outstanding-work | Ticket-scoped, read-only blocker-first dashboard for unmet requirements, check evidence, working-copy state, tracking drift, and concrete untracked follow-ups |
| pickup | Read-only shortlist of unassigned, ready Jira tickets for the team (active sprint, next sprint, top of backlog) with flagged or blocked tickets listed separately; scoped by a workspace `pickup.toml` |
| plan-day | Render today's plan from a My PA workspace: ranked Jira, Trello, Beads and Thoughtbox items assigned to work, project-session, evening or skip blocks, flagged when delegable to an unattended session, written to a dated ephemeral plan file |
| project-brief | Read-only workspace-level synthesis of project outcomes, requirement linkage, delivery evidence, coordination risks, and the single most important next coordination action |
| today | Read-only same-day or previous-workday activity recap; owns shared rendering, with current-session context in same-day mode |

## Backlog and Beads

| Skill | Description |
|-------|-------------|
| backlog-groom | Audit unfinished beads across workspace stores (or local open beads) for unclear descriptions, labels, lifecycle, structure and duplicates; report-only, with approved and individually confirmed mutations |
| beads | Shared Beads workflow baseline for resolving the owning store, separating ephemeral checklists from durable tracking, routing focused operations, and confirming remote Dolt actions |
| beads-check-dolt-migration | Detect whether beads needs classic-to-Dolt migration or an in-place Dolt schema upgrade |
| beads-migrate-to-dolt | Back up and verify classic conversion or Dolt schema upgrades; preserve remote history and keep repository aftercare separately opt-in |
| beads-setup | Preview and separately confirm a fresh repository Beads store with a private GitHub Dolt remote; refuse existing state and verify each initialization/publication boundary |
| next | Rank ready beads across validated stores; listing is read-only; selection claims one bead, shows details and continues into its appropriate work workflow without a redundant start prompt |
| plan-to-backlog | Dynamically materialize an explicitly approved plan into proposal-first Beads tracking when durable ownership is requested, with no-item/single-item/epic outcomes and explicit confirmation before writes |
| refine | Read-only sizing assessment of one existing bead — keep whole, clarify, or split into independently valuable outcomes, possibly under an epic; hands approved changes to /triage, never writes |
| thoughtbox | Retrieve repository-scoped Thoughtbox Inbox captures, prepare a hostile-text-safe handoff to `/triage`, and render separately confirmed scoped resolution commands without executing either workflow |
| tracking-sweep | Portfolio-wide drift sweep across Jira, beads, and GitHub PRs — flags status drift, orphan work, parent-moved beads, and stale items. Read-only |
| trello-beads | Integrate Trello boards with Beads for project management bridging |
| triage | Create/refine beads from raw requests or Jira, or own explicitly requested blocked human decisions; approved implementation plans go to plan-to-backlog |

## Jira, Confluence and Trello

| Skill | Description |
|-------|-------------|
| breakdown | Lightweight read-only Jira overview grounded in relevant code: Problem, Solution, Steps, and Open questions; hands complex planning and tracking to their owners |
| confluence | Read Confluence pages and comments for design docs, ADRs, and runbooks |
| jira-comment | Draft and post a terse house-style comment on a Jira ticket after confirmation |
| jira-ticket | Look up Jira ticket details including summary, type, and description |
| pickup | Read-only shortlist of unassigned, ready Jira tickets for the team (active sprint, next sprint, top of backlog) with flagged or blocked tickets listed separately; scoped by a workspace `pickup.toml` |
| trello-beads | Integrate Trello boards with Beads for project management bridging |

## Planning and decisions

| Skill | Description |
|-------|-------------|
| architect | Read-only architecture and implementation planning with evidence-backed research, acceptance slices, and explicit tracking handoffs; never writes code or tracker records |
| breakdown | Lightweight read-only Jira overview grounded in relevant code: Problem, Solution, Steps, and Open questions; hands complex planning and tracking to their owners |
| do-i-need-this | Explicit read-only necessity check for one idea or task; weighs doing nothing and smaller alternatives, labels insufficient evidence, and stops after advice |
| reassess | Explicit read-only project reassessment comparing intent, implementation, unfinished work, interrupted artifacts and revision-qualified checks; proposes keep/update/add/retire without acting |
| sanity-check | Explicit read-only mid-session direction checkpoint with bounded evidence, labelled self-assessment and optional one-shot peer review; never acts on its recommendation |
| second-opinion | Independent advisory claims from one peer or a configured panel; PR evidence uses pinned snapshots and explicit stale-safety checks |

## Coding and verification

| Skill | Description |
|-------|-------------|
| clean-code | Format, lint, and fix all warnings across the entire codebase |
| contract-check | Read-only Pact-lite health authority: content drift, uncommitted pacts, sync gaps, static CI evidence and semantic test gaps |
| contract-test | Execute existing scoped Pact-lite generation, local sync and provider verification; status delegates to contract-check |
| delegate-work | Dynamically coordinate bounded delegation for non-trivial work when independent investigation, separated implementation and review, or genuinely separable workstreams materially improve delivery |
| dependabot-remediation | Plan Dependabot security fixes for one repository into a few beads (dedicated urgent fixes, small compatible batches, one dated follow-up), then fix one bead with native verification and one confirmed push |
| develop | Lightweight standard/high entry before authorized code changes, with one-way diagnosis, architecture, and premium implementation handoffs; best-effort routing, not a capability floor |
| diagnose-bug | Evidence-led, read-only bug diagnosis using minimal reproduction, boundary isolation, ranked hypotheses, and explicit falsification tests before proposing a fix |
| implement-solution | Load before implementation-ready coding with interacting behavior, state/error paths, or local design trade-offs, including when ongoing work becomes complex; premium judgment and proportional TDD, not mechanical-edit ceremony |
| pair-programming | Opt-in conversational pairing with agent-written code: discuss small agreed steps and their evidence, allow redirection, and preserve normal workflow and safety gates |
| pedantic-review | Read-only craft and test-design review; requirements, coverage sufficiency, execution, and fixes stay with their separate owners |
| total-review | Portable pre-PR gauntlet with revision-bound artifact hygiene and review evidence, explicit missing coverage, optional independent reviewers, and at most two fix/review passes |
| verify-task | Verify explicit requirements and coverage against a fixed scope using discovered repository-native gates; report missing, failed, or stale evidence without repairs |

## Git and publication

| Skill | Description |
|-------|-------------|
| artifact-hygiene | Run a local-only, read-only advisory audit of publishable files and unpublished branch history with isolated Gitleaks and redaction-safe findings |
| complete-task | Complete an in-progress task by running clean-code, staging, and committing; closes on trunk, hands off to /create-pr in PR workflows, and protects detached commits; can offer an opt-in, approved Jira review move |
| create-pr | Audit publication artifacts, then create a separately confirmed pull request following project conventions and close the associated bead; can offer an opt-in, approved Jira review move |
| rebase | Rebase feature/stacked branches, or explicitly integrate upstream into local main/master; isolated trunk mode preserves remote history and never enters force-push or PR flows |
| setup-multirepo-git | Multi-repo git workflow rules and setup with mgit wrapper |
| stack-branch | Create a new branch stacked on another PR |
| start-ticket | Initialize work on a Jira ticket with a conventionally-named branch |
| workspace-sync | Explicit attended Git and Beads synchronization using validated workspace targets, accurate previews and separate fresh approvals; no automatic sync, retries or recovery |

## Pull requests

| Skill | Description |
|-------|-------------|
| pr-review-requests | Read-only inbound PR dashboard with request/update times, exact-head CI, merge state, reviews, feedback, and manual next steps |
| pr-reviewers | Recommend reviewers from your previous PRs in one repository, adding labelled sibling-workspace evidence filtered to people with target access; read-only, never requests reviews |
| pr-status | Show enriched status of your open PRs — CI checks, approvals, unresolved review threads, and linked Jira discussion |
| ready-to-merge | Pre-merge gate — verify a PR is green, approved, in sync, and free of obvious risk, then (on explicit approval) squash-merge it |
| reply-comments | Publish prepared PR-feedback outcomes through separate confirmed push, reply, and inline-thread resolution gates with race and duplicate protection |
| review-comments | Select and independently validate PR feedback, make focused verified local fixes, reopen its bead after a committed fix, and commit locally without publishing remote actions |
| review-pr | Review a pull request against the linked Jira ticket requirements |
| watch-pr-feedback | Watch open PRs for normalized feedback, independently validate each new or edited actionable item once, and render a bounded decision queue. Read-only by default; attended mode pauses only for acknowledgment |
| watch-prs | Recurring unattended /pr-status dashboard until end of day: adaptive cadence (faster while CI runs, backing off when settled) or a fixed `\d+m` interval, with transition-driven suggested actions |
| watch-review-requests | Schedule the read-only inbound PR request dashboard; adaptive/fixed cadence, unattended, manual review only |

## Builds, releases and rollouts

| Skill | Description |
|-------|-------------|
| circleci-status | Check CircleCI build status and failed job logs for the current GitHub repository |
| eas-build-error | Show the status and errors from the latest EAS build |
| ready-to-release | Shared read-only release authority — collects evidence, evaluates gates, and renders one service's verdict |
| release-maintenance | Explicitly invoked, separately confirmed manifest reconciliation, config synchronization, restart, or rollout acknowledgement; never runs inside a watch tick |
| release-manager | Attended push gatekeeper consuming shared readiness verdicts; current-command confirmation, CI tracking, rollout observation, and cadence |
| release-status | Read-only dashboard consuming the shared release authority, including blockers and separate activation follow-ups |
| watch-actions-rollout | After a merge, watch the GitHub Actions deploy run until the gating job lands, then run a confirmed read-only smoke test scoped to the change. Goal-terminating; staging by default, production read-only opt-in |
| watch-flux-rollout | After a push, watch CircleCI and FluxCD until the exact commit is built, the Kubernetes image changes, and pods are ready, then run a confirmed read-only smoke test. Goal-terminating |
| watch-release | Recurring attended /release-manager gatekeeper until end of day: adaptive cadence (faster during rollouts or CI, backing off when settled) or a fixed `\d+m` interval |
| watch-rollout | Choose between implemented rollout stacks, then delegate unchanged arguments to the GitHub Actions or CircleCI/Flux specialist without weakening stack-specific safety |

## Sessions and handoffs

| Skill | Description |
|-------|-------------|
| handoffs | Browse/load current-repo and workspace-member handoffs, with optional confirmed archiving and checkout recovery; never executes saved work merely by loading |
| handoffs-tidy | Review completion/staleness candidates and separate uncertain/aged groups; archive explicit selections, never delete or resume work |
| name-session | Derive a conventional session name from the branch ticket, active bead, open PR, and current work — prints the active client's paste-ready rename command |
| peer-session | Send one human-approved live ask or instruction to a peer via native Claude Code messaging for local sessions or Orca otherwise; verify correlated evidence without automatic retries, transport switching, spawning or offline queueing |
| wrap-up | Report session activity, artifact hygiene and working-copy/tracker/settings risks, then save a resume handoff; no unrelated repairs or archive sweep |

## Agent configuration and usage

| Skill | Description |
|-------|-------------|
| model-update-check | Audit Pi startup defaults, routing and coordinated model migration previews across second-opinion and pi-spend; read-only by default, with separate attended refresh and apply paths |
| pi-spend | Read-only estimate of Pi model cost by provider and model for today, this week, this month, and all recorded history, separating metered credit usage from flat-rate subscription usage |
| prompt-patterns | Find recurring substantial prompts in local Pi and Claude Code history and suggest reusable prompt-template drafts; metadata-first, redacted, bounded and read-only |
| skills-review | Explicit read-only collection review with bounded content sampling, conservative evidence-backed recommendations and selected-pattern handoff to triage |
| tidy-settings | Sort, dedupe, and audit Claude `settings.json` / `settings.local.json` files at user and project level — flags risky permissions, broken refs, subsumed entries, and cross-section conflicts |
| token-dashboard | Read-only current-session and UTC-week token telemetry for Pi, Claude Code, Codex, and optional OpenRouter management analytics; normalized JSON and terminal views without transcript or credential output |
| watch-telemetry | Query opt-in local watcher-execution counters with partial coverage, fixed privacy-safe fields, and bounded active retention; explicitly enable, disable, or prune collection |

## Visual and media

| Skill | Description |
|-------|-------------|
| browser-screenshot | Take a screenshot of the running web application for visual verification of UI/CSS changes |
| image-studio | Generate, compare, refine, and export image assets from one creative brief; Recraft-first with explicit, provider-neutral alternatives |

## Model routing

Shared skills declare a portable capability tier and reasoning effort. See
[`MODEL_ROUTING.md`](../MODEL_ROUTING.md) for the allowed values, runtime
ownership boundaries, and authoring guidance.
