#!/usr/bin/env bash
# Compatibility entry point for existing permission rules.
exec "$(dirname -- "${BASH_SOURCE[0]}")/../../pr-status/scripts/gh-pr-inline-comments.sh" "$@"
