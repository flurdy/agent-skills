---
description: Remove redundant inline comments and docblocks from a diff, file, or pull request
argument-hint: "[file-or-PR]"
---
Review ${1:-the current diff} for inline code comments and docblocks. Remove comments that only restate what the code does. Keep only concise comments that explain why the code exists or a genuinely non-obvious decision. Prefer self-documenting names over comments. If edits are in scope, make only the safe comment/docblock changes; otherwise report the recommended removals.
