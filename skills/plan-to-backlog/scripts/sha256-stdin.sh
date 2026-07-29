#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    '')
        if command -v sha256sum >/dev/null 2>&1; then
            sha256sum | awk '{print $1}'
        elif command -v shasum >/dev/null 2>&1; then
            shasum -a 256 | awk '{print $1}'
        else
            printf '%s\n' 'sha256-stdin: sha256sum or shasum is required' >&2
            exit 127
        fi
        ;;
    --canonical-text)
        [[ $# -eq 1 ]] || {
            printf '%s\n' 'usage: sha256-stdin.sh [--canonical-text]' >&2
            exit 2
        }
        python3 -c 'import hashlib, sys
text = sys.stdin.buffer.read().decode("utf-8")
normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
print(hashlib.sha256(normalized.encode("utf-8")).hexdigest())'
        ;;
    *)
        printf '%s\n' 'usage: sha256-stdin.sh [--canonical-text]' >&2
        exit 2
        ;;
esac
