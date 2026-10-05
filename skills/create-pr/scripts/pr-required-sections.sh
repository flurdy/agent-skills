#!/usr/bin/env bash
# Usage: pr-required-sections.sh
# Prints the path of the nearest .agents/create-pr/required-sections.md, or nothing.
# Searches upward from the logical cwd, then from the repository's physical root,
# stopping below $HOME so user-level ~/.agents never applies to every repository.
set -euo pipefail

RELATIVE=".agents/create-pr/required-sections.md"
HOME_DIR=$(cd -- "${HOME:?}" 2>/dev/null && pwd -P || printf '%s' "$HOME")

search_upward() {
    local directory=$1
    while [[ -n $directory && $directory != "/" && $directory != "$HOME" && $directory != "$HOME_DIR" ]]; do
        case "$HOME_DIR/" in
            "$directory"/*) return 1 ;;
        esac
        if [[ -f "$directory/$RELATIVE" ]]; then
            printf '%s\n' "$directory/$RELATIVE"
            return 0
        fi
        directory=$(dirname -- "$directory")
    done
    return 1
}

search_upward "${PWD:-$(pwd)}" && exit 0
repository_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
search_upward "$repository_root" || true
