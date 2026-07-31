#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTHORITY="$SKILL_DIR/scripts/release-order"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[ -x "$AUTHORITY" ] || fail "missing executable release-order authority"
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
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/SKILL.md" || \
    fail "release-manager does not define manifest-free defaults"
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/../release-status/SKILL.md" || \
    fail "release-status does not define manifest-free defaults"
grep -Fq 'If `docs/release-manifest.yaml` is absent' "$SKILL_DIR/../ready-to-release/SKILL.md" || \
    fail "ready-to-release does not define manifest-free defaults"

printf '%s\n' 'release-order skill contract tests passed'
