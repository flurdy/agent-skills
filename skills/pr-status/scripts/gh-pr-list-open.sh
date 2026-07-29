#!/usr/bin/env bash
# List all open PRs by the current user across a GitHub org.
# Org resolution: see resolve-org.sh
set -euo pipefail

# shellcheck source=resolve-org.sh
source "$(dirname "${BASH_SOURCE[0]}")/resolve-org.sh"
ORG="$(resolve_org "${1:-}")"

gh search prs --author @me --state open --owner "$ORG" --limit 50 \
  --json repository,number,title \
  --jq '.[] | {number, title, owner: "'"$ORG"'", repo: .repository.name}'
