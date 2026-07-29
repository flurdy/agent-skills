#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 0 ]]; then
    printf '%s\n' 'usage: utc-now.sh' >&2
    exit 2
fi

date -u '+%Y-%m-%dT%H:%M:%SZ'
