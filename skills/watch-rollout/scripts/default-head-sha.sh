#!/usr/bin/env bash
# Usage: default-head-sha.sh [<branch>]   (default: main)
# Fetches the remote branch and prints its HEAD sha. Wraps the fetch + rev-parse so
# the call site is one allowlistable prefix instead of an `&&` compound.
set -euo pipefail

BRANCH="${1:-main}"
git fetch origin "$BRANCH" -q
git rev-parse "origin/${BRANCH}"
