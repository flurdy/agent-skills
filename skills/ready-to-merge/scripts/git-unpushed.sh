#!/usr/bin/env bash
# List commits on HEAD not yet pushed to upstream.
# Wrapper exists so Claude Code sandbox doesn't flag @{u}..HEAD as brace expansion.
set -euo pipefail
git log '@{u}..HEAD' --oneline
