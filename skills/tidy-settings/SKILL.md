---
name: tidy-settings
description: Sort, dedupe, and audit Claude settings.json / settings.local.json files at user and project level. Flags risky permissions, broken references, glob-subsumed entries, syntax errors, and cross-file duplicates that could be promoted up the hierarchy. Mechanical fixes auto-apply, judgment calls are presented as a triage list.
allowed-tools: "Read, Edit, Write, Bash(python3:*), Bash(test:*), Bash(ls:*), AskUserQuestion"
model: sonnet
effort: medium
version: "1.0.0"
author: "flurdy"
---

# Tidy Settings

Occasional housekeeping on your Claude permissions. Settings files accumulate cruft: the same permission added narrowly five times, references to skills/scripts that no longer exist, redundant entries that one user-level rule already covers, and the occasional risky `Bash(curl:*)` you wish you hadn't accepted.

This skill cleans the mechanical noise itself and surfaces the judgment-heavy items for your review.

## When to use

- Periodically (every few weeks), when settings files feel cluttered.
- After a long stretch where you've been clicking "Yes" to permission prompts and want to see what stuck.
- Before sharing or committing a project-level `settings.json` — to make sure it's tidy and free of personal/local lines.

Complementary to `fewer-permission-prompts` (which adds permissions); this *cleans* them.

## What it does

**Auto-applied (mechanical, safe):**

- Canonical sort: arrays grouped by tool prefix (`Bash`, `Edit`, `Read`, `Write`, `WebFetch`, `WebSearch`, `Skill`, `Task`, `mcp__*`), alphabetical within group.
- Exact dedupe.
- Backup files (`.bak`) written alongside each modified file.

**Reported for your judgment (never auto-removed):**

- **Risk flags** — entries matching known-risky patterns (`Bash(rm:*)`, `Bash(curl:*)`, `WebFetch(*)`, `Read(//...)`, unrestricted Edit/Write, etc.).
- **Broken refs** — `Bash(~/path/...)` or `Bash(/abs/path/...)` pointing at missing files; `Skill(name)` for skills not installed.
- **Subsumed entries** — narrow entry covered by a broader `:*` entry in the **same section of the same file** (allow vs allow, deny vs deny, ask vs ask). The narrow one is technically redundant, but see "Subsumption trade-off" below before recommending which to remove.
- **Syntax errors** — entries that don't parse as a known permission shape.
- **Cross-section conflicts** — an entry in `allow` shadowed by a wider `:*` entry in `deny` (deny wins, so the allow is dead code).
- **Cross-file duplicates** — same entry in multiple files. Often means an item should be promoted to user level (and removed from project locals), or vice versa if it references a project-specific path.

### Permission precedence

Claude Code evaluates in this order. **Always state this when explaining a subsumption or conflict finding:**

1. **deny** — hard block, no prompt.
2. **allow** — auto-permit.
3. **ask** — prompt the user.
4. **default** — falls through to `--permission-mode` behavior (`default` = ask, `acceptEdits` = auto-edit, `auto`/`bypassPermissions` = auto-allow).

### Subsumption trade-off (important)

When a narrow entry is subsumed by a wider `:*` entry in the same section, removing one vs the other is **not** equivalent:

- **Remove the narrow** → behavior unchanged. The wide rule continues to govern that command family.
- **Remove the wide** → only exact-listed narrow variants remain governed. Anything else in the family falls through to the next tier (or default).

That second case is what bit the user in early testing — removing `Bash(gh api:*)` from `ask` left a handful of narrow `gh api …` entries, but every *other* `gh api` invocation now hits the default rather than always-prompting.

Section by section:

- **In `allow`**: the broad pattern is usually intentional (you trust the command family). Suggest removing **the narrows** — the broad already covers them and the narrows just clutter.
- **In `deny`**: the broad pattern is a safety wall (you never want this command family). Suggest removing **the narrows** — the broad blocks everything, narrows are redundant.
- **In `ask`**: the broad pattern is a catch-all to ensure prompting. Removing it is the riskier choice. Default to suggesting **remove narrows**, and only suggest removing the broad if every plausible variant is explicitly listed.

When presenting subsumption findings, name the section, name the trade-off, and give a default recommendation rather than asking the user to guess.

## Usage

```
/tidy-settings           # Audit + auto-apply mechanical fixes + interactive triage
/tidy-settings --report  # Report only, no writes (even for sort/dedupe)
```

## Instructions

### 1. Resolve which files to operate on

Build the file list:

```bash
test -e ~/.claude/settings.json && echo ~/.claude/settings.json
test -e ~/.claude/settings.local.json && echo ~/.claude/settings.local.json
```

If currently inside a git repo (use `git rev-parse --show-toplevel` resolved via the shared symlink if `.claude` is one), also include:

```bash
test -e <repo>/.claude/settings.json && echo <repo>/.claude/settings.json
test -e <repo>/.claude/settings.local.json && echo <repo>/.claude/settings.local.json
```

If `.claude` is a symlink, resolve through it — the underlying file is what matters.

### 2. Run the script

```bash
python3 ~/.claude/skills/tidy-settings/scripts/tidy_settings.py --apply <files...>
```

(Omit `--apply` for `--report` mode.)

Parse the JSON output. The shape is:

```
{
  "files": [
    {
      "path": "...",
      "exists": true,
      "applied": {"changed": bool, "deduped": {...}, "backup": "..." | null},
      "report": {
        "current": {"allow": [...], "deny": [...], "ask": [...]},
        "allow_audit": {
          "subsumed_candidates": [{"narrow": "...", "broad": "..."}],
          "broken_refs": [{"entry": "...", "kind": "missing_file|missing_skill", "resolved": "..."}],
          "risk_flags": [{"entry": "...", "severity": "high|medium", "reason": "..."}],
          "syntax_errors": [{"entry": "...", "reason": "..."}]
        },
        "deny_audit": {...},
        "ask_audit": {...}
      }
    }
  ],
  "cross_file": {"duplicates": [{"entry": "...", "in": ["...", "..."]}]}
}
```

### 3. Summarize the mechanical pass

Print a single short block per modified file, e.g.:

```
✓ ~/.claude/settings.json — sorted, dedupe removed 0, backup at settings.json.bak
✓ <project>/.claude/settings.local.json — sorted, dedupe removed 2, backup at settings.local.json.bak
- ~/.claude/settings.local.json — absent, skipped
```

### 4. Triage the findings

Order findings by severity:

1. **High-severity risk_flags** first (`Bash(rm:*)`, `Bash(*)`, `WebFetch(*)`, root-level Read/Edit/Write).
2. **Cross-section conflicts** (`allow_shadowed_by_deny`) — these are dead code; the allow entry will never fire.
3. **Syntax errors** next (these silently don't work).
4. **Broken refs** — likely cleanup wins.
5. **Subsumed candidates** — apply the "Subsumption trade-off" guidance above. For `Skill(name:*)` vs `Skill(name)` in particular, the `:*` variant is typically meaningless (Skills don't take args) — recommend removing the `:*` form regardless of section.
6. **Cross-file duplicates** — these need judgment. Apply this heuristic:
   - Entry references a path inside `~/.claude/...` or `~/Code/<not-current-repo>/...` → suggest promoting to user-level (`~/.claude/settings.json`) and removing from project files.
   - Entry references a path inside the current repo → suggest keeping at project level only.
   - Entry already exists at user level AND project level → suggest removing from project (redundant).
   - Entry has no path scope (e.g. `Skill(landscape)`, `mcp__playwright__*`) → suggest user level.
7. **Medium-severity risk_flags** last — most are intentional (`Bash(curl:*)` if you do a lot of web work).

For each finding, present:

- The entry, the file(s) it's in, and *why* it's flagged.
- A specific suggested action.
- Whether to apply.

Group similar findings and use `AskUserQuestion` to batch decisions where it helps (e.g., "All 6 narrow `Skill(<name>)` entries are subsumed by `Skill(<name>:*)` variants — remove all narrow ones?").

### 5. Apply chosen changes

For removals: use `Edit` on the target JSON file to delete the line, including the trailing comma when not last, or the preceding comma when last in the array.

For promotion (move entry from file A to file B):

1. Remove from file A using `Edit`.
2. Append to file B's `allow` array (insert before the closing `]`).
3. Re-run the script with `--apply --no-backup` on file B to re-sort.

After all chosen mutations, run the script once more with `--report` on all files to verify nothing went wrong (no new syntax errors, file still valid JSON).

### 6. Final summary

End with a short summary:

```
Applied:
  - sorted/deduped 2 files
  - removed 6 subsumed Skill(<name>) entries from ~/.claude/settings.json
  - removed Bash(~/.claude/skills/landscape/scripts/pr-status.sh) (missing file)
  - promoted Skill(landscape) and Skill(next) to user level

Still on your radar:
  - Bash(curl:*) in <project> — flagged medium-risk, you said keep
  - WebSearch in user file — syntax check passes, but verify intent

Backups: 2 .bak files written; delete when you've verified.
```

## Notes

- The script never auto-removes from the `deny` or `ask` arrays beyond exact dedupe. Promote/remove from those only on explicit user request.
- `mcp__server__tool` entries can't be verified for existence without a live MCP probe — leave them alone unless the user flags one.
- `WebSearch` and other bare tool names (no parens) are valid permissions — they sort with their tool prefix.
- If a project's `.claude/` is a symlink to another git repo (e.g. `claude-myrepo/`), the underlying real path is what gets edited.
