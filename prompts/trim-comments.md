---
description: Remove redundant inline comments and docblocks from a diff, file, or pull request
argument-hint: "[file-or-PR]"
---
Review $ARGUMENTS for inline code comments and docblocks. If no argument was provided, review the current diff. Remove comments that only restate what the code does. Keep only concise comments that explain why the code exists or a genuinely non-obvious decision. Prefer self-documenting names over comments. If edits are in scope, make only the safe comment/docblock changes; otherwise report the recommended removals.
