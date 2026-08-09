#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SKILL="$ROOT/SKILL.md"
UAT="$ROOT/references/uat.md"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[[ -f "$SKILL" ]] || fail 'missing SKILL.md'
[[ -f "$UAT" ]] || fail 'missing UAT guide'

grep -Fq 'thoughtbox context resolve --repo' "$SKILL" || fail 'missing context resolution'
grep -Fq 'thoughtbox list --repo' "$SKILL" || fail 'missing scoped Inbox retrieval'
grep -Fq 'thoughtbox list --unassigned' "$SKILL" || fail 'missing explicit unassigned count'
grep -Fq 'never invoke `/triage`' "$SKILL" || fail 'missing triage boundary'
grep -Fq 'never run' "$SKILL" || fail 'missing resolution boundary'
grep -Fq '`thoughtbox resolve`' "$SKILL" || fail 'missing resolution command boundary'
grep -Fq 'interrupted' "$SKILL" || fail 'missing interrupted-triage behavior'
grep -Fq 'scripts/render.py handoff' "$SKILL" || fail 'missing byte-safe renderer'
grep -Fq 'scripts/render.py resolution' "$SKILL" || fail 'missing resolution renderer'
grep -Fiq 'hostile-text' "$UAT" || fail 'missing hostile-text UAT'
grep -Fq 'malformed' "$UAT" || fail 'missing malformed-item UAT'
grep -Fq 'unassigned' "$UAT" || fail 'missing unassigned-item UAT'

printf 'thoughtbox skill contract: ok\n'
