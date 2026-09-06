---
name: release-maintenance
description: >
  Separately confirmed manifest reconciliation, scoped config synchronization, workload
  restart, or evidence-backed rollout acknowledgement. Requires explicit invocation;
  never runs inside a release watch tick.
allowed-tools: "Read,Write,AskUserQuestion,Bash(./scripts/release-order:*),Bash(./scripts/mgit status:*),Bash(./scripts/mgit diff:*),Bash(./scripts/mgit log:*),Bash(./scripts/mgit show:*),Bash(kubectl get:*),Bash(~/.agents/skills/ready-to-release/scripts/release-gates:*)"
model-tier: premium
model: opus
effort: high
version: "1.0.0"
author: "flurdy"
---

# Release Maintenance

Own production-affecting maintenance separately from shipping decisions.
This skill is **never invoked by** `/release-manager` or `/watch-release`; those workflows may suggest a fresh explicit
invocation but cannot dispatch it. A push answer is not maintenance authorization.

## Usage

```text
/release-maintenance reconcile-order
/release-maintenance config-sync <repository>
/release-maintenance restart <service>
/release-maintenance acknowledge-rollout <service>
```

Require an explicit operation and target. A missing/ambiguous argument is a clarification, not a
license to scan for actions. Load the verified project's guidance and relevant runbook first.
Do not invent repository names, cluster context, namespaces, startup-only config behavior, or
consumer sets. Unsupported project capabilities require a handoff, not generic fallback commands.

## Shared action boundary

1. Identify the exact repository/worktree or Kubernetes context/namespace/resource and current
   evidence. Preserve unrelated edits and state. One writer per state file; pause the attended
   manager before any shared-state update. Malformed or concurrently changed state stops writes.
2. Show the diff or operation, target, production consequence, and **one visible command**. Ask
   immediately before each remote or destructive action; this skill also confirms local manifest
   rewrites and state acknowledgements. Dismissal/no answer means do nothing. Every subsequent
   command needs its own approval; no cached tick answer or bundled `&&` chain.
3. Recheck target identity and relevant evidence after the answer. A changed target/evidence voids
   approval. Never switch the active Kubernetes context; pass `--context` explicitly every time.
4. Mutating Git/Kubernetes commands are deliberately not preapproved by this skill's tool list.
   Obtain any required runtime permission as well as the current action answer; denial stops the
   operation, never triggers a broader shell grant. For read-only Kubernetes evidence use
   `kubectl get --context <context> --namespace <namespace> ...` with explicit safe fields.
5. Verify the actual outcome before recording it. Stop on failure or uncertainty; no automatic
   retry, rollback, push, tag, history rewrite, or deletion. Credentials remain in the keyring;
   never print Secret data or config values.

## Reconcile dependency order

Run `./scripts/release-order` read-only and show its accepted graph and new/removed drift. The
existing Pact adapter owns generated content; humans own `order.manual` and `order.suppress`.
An absent manifest, unavailable adapter, or non-Pact provider cannot be repaired implicitly.

Preview the generated-block change and ask for the exact local rewrite:

```bash
./scripts/release-order --write
```

After approval, execute only that command. Inspect the named manifest diff; verify manual/suppress
entries and unrelated content are unchanged, then rerun the read-only order adapter. An unexpected
diff stops the operation for owner review; do not reset/discard it. Commit only named paths if
requested by local workflow. A commit does not authorize publishing it.

## Configuration synchronization

The project runbook/recipe, not this skill, defines source-to-GitOps transformation and ownership.
Inspect it before proposing commands. Do not execute `make k8s-sync` as a shortcut: legacy recipes
may hide a pull/rebase and push. Enumerate the necessary scoped operations and confirm each remote
or destructive command separately. Use `./scripts/mgit` for the registered Git repository.

- Require known source changes, destination worktree/branch, target environment, and clean or
  explicitly owned destination changes. Show the redaction-safe diff before any publish decision.
- If the operation needs history rewriting, merge conflict resolution, or a transformation without
  a verified project command, stop with a specific handoff. This invocation is not blanket approval
  to repair history or modify linked repositories outside the named operation.
- Publish only the exact reviewed commit after a fresh command confirmation. A successful Git push
  is **not** proof that Flux/the deployment controller applied desired configuration.
- Read-only apply verification must bind the controller's observed source revision and desired
  resource identity to that commit. resourceVersion movement alone is insufficient.
- Never infer that a workload reads config only at startup, auto-derive a restart queue from a
  source grep, or restart in the sync operation. A restart requires a separate explicit invocation.

## Restart one workload

Require explicit context, namespace, kind/name, reason, and verified project evidence that the
workload requires a restart and the intended configuration revision is applied. Mount presence,
a Secret/ConfigMap change, or young pods alone does not establish that requirement. CronJobs and
unsupported workload types require their own project runbook, not a Deployment fallback.

For a verified Deployment, show and freshly confirm this fully scoped command:

```text
kubectl --context <context> --namespace <namespace> rollout restart deployment/<name>
```

Before execution, read the current UID/generation and deployment status without secret contents.
Afterwards bind verification to that same UID and the newly observed desired **generation**:
`observedGeneration` has caught up, updated/ready/available replicas match desired replicas, and
no old replicas remain. Use bounded read-only observation; report incomplete evidence rather than
waiting forever. Pod age reset, unchanged image tag, or a successful restart command is not proof
of completion. Do not claim application-level health without a scoped read-only check.

## Acknowledge a rollout with missing baseline

Collect the shared readiness result. `rollout=unknown` from a null `fromTag` must not be converted
to success using age or elapsed time. Require independent project deployment evidence linking the
saved pushed revision to the currently settled workload (for example immutable image provenance
and the controller's observed revision), including explicit context/resource identity.

Show that evidence and the exact `rolloutWatch[service]` entry proposed for removal. Ask for a
current acknowledgement, re-read state, and remove **only that unchanged entry** after confirmation.
If provenance is unavailable, keep it and report HOLD; do not add an expiry that fabricates readiness.
Re-run the read-only authority afterwards. This is a local tracking update, not a deployment.

## Legacy maintenance state

`configApply`, `restartPending`, and `restartWatch` from older managers are preserved, not migrated
or advanced automatically. They are hints to investigate, not proof of application or startup
requirements. For the explicitly selected operation, inspect current project evidence and propose
only a separately confirmed update to the relevant unchanged entry. Preserve every unrelated key;
never clear the whole state file or resurrect the old resourceVersion/pod-age heuristics.
