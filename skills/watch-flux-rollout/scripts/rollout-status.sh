#!/usr/bin/env bash
# Usage: rollout-status.sh <deployment> [<namespace>]   (default namespace: apps)
# Emits one JSON object describing a k8s Deployment's live rollout state — image
# tag, ready/desired replicas, newest pod creation time. The jq shaping lives
# here so the call site stays a clean, allowlistable prefix for the
# /watch-flux-rollout poll loop. Extracted from letterbox's deploy-status.sh
# (the per-service kubectl leg), generalised: no name prefix/suffix conventions.
set -uo pipefail

DEPLOYMENT="$1"
NAMESPACE="${2:-apps}"

CONTEXT="$(kubectl config current-context 2>/dev/null || echo unknown)"
INFO="$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o json 2>/dev/null || true)"

if [ -z "$INFO" ]; then
    jq -n --arg context "$CONTEXT" --arg ns "$NAMESPACE" --arg name "$DEPLOYMENT" \
        '{context: $context, namespace: $ns, deployment: $name, found: false}'
    exit 0
fi

# Newest pod for this deployment — the rollout signal alongside tag movement.
NEWEST_POD_CREATED="$(kubectl get pods -n "$NAMESPACE" -o json 2>/dev/null \
    | jq -r --arg name "$DEPLOYMENT" \
        '[.items[] | select(.metadata.name | startswith($name)) | .metadata.creationTimestamp] | max // empty')"

jq -n \
    --arg context "$CONTEXT" \
    --arg ns "$NAMESPACE" \
    --arg name "$DEPLOYMENT" \
    --arg podCreated "$NEWEST_POD_CREATED" \
    --argjson info "$INFO" \
    '{
        context: $context,
        namespace: $ns,
        deployment: $name,
        found: true,
        ready: ($info.status.readyReplicas // 0),
        desired: ($info.spec.replicas // 0),
        image: $info.spec.template.spec.containers[0].image,
        tag: ($info.spec.template.spec.containers[0].image | sub(".*:"; "")),
        newestPodCreated: (if $podCreated == "" then null else $podCreated end)
    }'
