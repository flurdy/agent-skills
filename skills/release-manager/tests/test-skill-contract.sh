#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTHORITY="$SKILL_DIR/scripts/release-order"
CI_AUTHORITY="$SKILL_DIR/scripts/release-ci"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[ -x "$AUTHORITY" ] || fail "missing executable release-order authority"
[ -x "$CI_AUTHORITY" ] || fail "missing executable release-ci authority"
[ -x "$SKILL_DIR/scripts/pact-graph" ] || fail "missing executable pact provider"

grep -Fq 'pact-graph' "$AUTHORITY" || fail "release-order does not compose the pact provider"

for consumer in release-manager release-status ready-to-release; do
    skill="$SKILL_DIR/../$consumer/SKILL.md"
    grep -Fq './scripts/release-order' "$skill" || fail "$consumer does not use release-order"
    if grep -Fq './scripts/pact-graph' "$skill"; then
        fail "$consumer still invokes pact-graph directly"
    fi
done

grep -Fq './scripts/release-order --write' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not reconcile through the ordering authority"
grep -Fq './scripts/release-ci' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not document the CI authority"
grep -Fq 'ciRevision' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not consume normalized CI revision evidence"
grep -Fq 'ciExpectedRevision' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not consume the exact upstream revision"

gate_section="$(awk '/^6\. \*\*Evaluate ready-to-push/{capture=1} /^6b\. \*\*Contract coverage beads/{capture=0} capture' "$SKILL_DIR/SKILL.md")"
for provider_term in CircleCI 'GitHub Actions' 'Cloud Build' ci-status.sh; do
    if grep -Fq "$provider_term" <<<"$gate_section"; then
        fail "release-manager CI gate contains provider-specific term: $provider_term"
    fi
done
if grep -Fq "confirmed the service's tests pass locally" <<<"$gate_section"; then
    fail "release-manager lets local tests override unavailable CI evidence"
fi
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not define manifest-free defaults"
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/../release-status/SKILL.md" || \
    fail "release-status does not define manifest-free defaults"
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/../ready-to-release/SKILL.md" || \
    fail "ready-to-release does not define manifest-free defaults"

printf '%s\n' 'release authority skill contract tests passed'
