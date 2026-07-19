---
description: Draft a squash-merge commit message for an approved pull request
argument-hint: "[PR-number]"
---
Suggest a concise squash-merge commit message for PR ${1:-the current branch's pull request}. Follow the repository's commit-message convention. Include a linked ticket reference only when one is present in the branch name or pull-request title, and keep the summary line to roughly 72 characters. Show the draft for approval; do not merge or modify Git history.
