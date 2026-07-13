---
name: tidy-settings
description: Sort, dedupe, and audit Claude settings.json / settings.local.json files at user and project level. Flags risky permissions, broken references, glob-subsumed entries, syntax errors, and cross-file duplicates that could be promoted up the hierarchy. Mechanical fixes auto-apply, judgment calls are presented as a triage list.
allowed-tools: "Read, Edit, Write, Bash(~/.claude/skills/tidy-settings/scripts/resolve-files.sh:*), Bash(python3:*), Bash(test:*), Bash(ls:*), Bash(git:*), Bash(readlink:*), Bash(realpath:*), AskUserQuestion"
model-tier: standard-coding
model-cost-policy: prefer-subscription-oauth
model-metered-policy: ask-above-standard
model: sonnet
effort: medium
version: "1.2.0"
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

Settings come in three roles. Resolve all of them with the helper script — **never** inline ad-hoc
shell for this (variable assignments and `while read` loops bypass the permission allowlist and
trigger noisy prompts):

```bash
~/.claude/skills/tidy-settings/scripts/resolve-files.sh
```

Output is `---<ROLE>---` sections, one existing file path per line:

- `---USER---` — `~/.claude/settings.json` / `settings.local.json` (always checked).
- `---CANONICAL---` — the settings the **main worktree** uses. The script avoids
  `git rev-parse --show-toplevel` (inside a worktree it points at the worktree's own checkout) and
  instead resolves the first `git worktree list` entry's `.claude` through any symlink.
- `---WORKTREE---` — every *other* worktree's own real `.claude/settings.local.json` (and tracked
  `settings.json`). These accumulate permissions that are **lost when the worktree is pruned**.

#### Worktree topology (why canonical ≠ pwd)

In the multi-repo setup, the main worktree's `.claude` is a **symlink** to a sibling state dir
(e.g. `myrepo/.claude` → `claude-myrepo/`), and worktrees live *inside* that state dir at
`claude-myrepo/worktrees/<name>/` — each a real checkout with its **own real** `.claude/`. So:

- The canonical `settings.local.json` (the one that survives) is reached through the **main
  worktree's** symlinked `.claude` — the script's `---CANONICAL---` section.
- A worktree's `settings.local.json` is a *separate, gitignored* file that vanishes on prune.
  Permissions you accepted while working there are promotion candidates (step 4).
- `settings.json` is git-tracked, so worktree copies converge on commit — drift there is reported
  but lower-stakes than the local file.

If there are no sibling worktrees, this degrades to exactly the old user + project behavior.

### 2. Run the script

```bash
python3 ~/.claude/skills/tidy-settings/scripts/tidy_settings.py --apply \
  --canonical "<canon>/settings.json" --canonical "<canon>/settings.local.json" \
  --worktree  "<wt>/.claude/settings.local.json" --worktree "<wt>/.claude/settings.json" \
  <all files including the canonical and worktree ones...>
```

Substitute the **literal paths** from step 1's output (don't reference shell variables — state
doesn't persist between Bash calls). Every path is still passed positionally (so it's
sorted/deduped/audited once); `--canonical` and `--worktree` just *tag* which positional paths
participate in the promotion diff. Pass each `---CANONICAL---` line under `--canonical` and each
`---WORKTREE---` line under `--worktree`. Omit both flags (and `--apply`) for plain `--report` mode;
with no sibling worktrees, omit them entirely.

Parse the JSON output. The shape is:

```
{
  "files": [
    {
      "path": "...",
      "exists": true,
      "error": "read error: ... | JSON parse error: ...",   // present only on failure
      "applied": {
        "changed": bool, "deduped": {...}, "backup": "..." | null,
        "realpath": "...",        // where the bytes actually went (symlink resolved)
        "verified": bool,         // re-read confirmed the write landed
        "write_error": "..."      // present only if the write itself failed
      },
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
  "cross_file": {"duplicates": [{"entry": "...", "in": ["...", "..."]}]},
  "worktree_promotions": [
    {"from": "<wt>/.claude/settings.local.json", "into": "<canon>/settings.local.json",
     "section": "allow", "entries": ["Bash(gh run watch *)"]}
  ]
}
```

`worktree_promotions` lists entries present in a worktree file but absent from the canonical file of
the same basename — these are exactly the permissions that disappear when the worktree is pruned.

### 3. Summarize the mechanical pass

Print a single short block per modified file, e.g.:

```
✓ ~/.claude/settings.json — sorted, dedupe removed 0, backup at settings.json.bak
✓ <canon>/settings.local.json — sorted, dedupe removed 2, verified, backup at settings.local.json.bak
✗ <canon>/settings.json — write FAILED (permission denied) — see remediation in step 5
- ~/.claude/settings.local.json — absent, skipped
```

When `applied.changed` is true, append `verified` (or a `write FAILED` callout) from
`applied.verified` / `applied.write_error` — never report a write as done without it.

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
7. **Worktree-only entries (promotion candidates)** — each `worktree_promotions` entry is a
   permission living *only* in a worktree's settings; it's lost when that worktree is pruned. Default
   recommendation: **promote into the canonical `into` file** so it survives. Apply judgment though —
   a one-off `Bash(...)` you accepted for a throwaway experiment may be better left to die with the
   worktree. Batch with `AskUserQuestion` when several share an obvious intent (e.g. "Promote these 3
   `gh`-related permissions from worktree `zazzy` into canonical settings?"). For tracked
   `settings.json` drift, note that committing the worktree's change is usually the cleaner fix than
   promoting — call it out rather than copying bytes.
8. **Medium-severity risk_flags** last — most are intentional (`Bash(curl:*)` if you do a lot of web work).

For each finding, present:

- The entry, the file(s) it's in, and *why* it's flagged.
- A specific suggested action.
- Whether to apply.

Group similar findings and use `AskUserQuestion` to batch decisions where it helps (e.g., "All 6 narrow `Skill(<name>)` entries are subsumed by `Skill(<name>:*)` variants — remove all narrow ones?").

### 5. Apply chosen changes

For removals: use `Edit` on the target JSON file to delete the line, including the trailing comma when not last, or the preceding comma when last in the array.

For cross-file promotion (move entry from file A to file B):

1. Remove from file A using `Edit`.
2. Append to file B's `allow` array (insert before the closing `]`).
3. Re-run the script with `--apply --no-backup` on file B to re-sort.

For **worktree → canonical promotion** (a `worktree_promotions` entry the user approved): the entry
stays in the worktree (it may still be in use there) and is *added* to the canonical file. Append it
to the canonical file's matching section array, then re-run the script with `--apply --no-backup` on
the canonical file to re-sort.

#### Verify persistence (required when any canonical/worktree file was written)

The canonical file is reached through a `.claude` symlink and is often mode `600`, so a write can
silently fail or land on the wrong inode. After all mutations, **re-run the script with `--report`
on every file you touched** and confirm:

- No file grew an `error` (read error / JSON parse error).
- For each written file, `applied.write_error` is absent and `applied.verified` is `true`. Use
  `applied.realpath` to confirm the bytes went where you intended (through the symlink, not beside it).
- Every promoted entry now appears in the canonical file's `report.current.<section>`.

If a write **failed** (`write_error` set or `verified` false), emit a loud `✗ FAILED` line and do
**not** claim success. Remediate:

- `readlink -f <main_wt>/.claude` — confirm the symlink resolves to a real directory.
- `ls -l <realpath>` — check the file mode; a `600` file the agent can't write is the usual cause.
- Fallback: write directly to the resolved `applied.realpath` rather than the symlinked path, then
  re-verify.

### 6. Final summary

End with a short summary:

```
Applied:
  - sorted/deduped 2 files
  - removed 6 subsumed Skill(<name>) entries from ~/.claude/settings.json
  - removed Bash(~/.claude/skills/landscape/scripts/pr-status.sh) (missing file)
  - promoted Skill(landscape) and Skill(next) to user level
  - promoted Bash(gh run watch *) from worktree zazzy → canonical (verified persisted)

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
- Worktree promotion always targets the **canonical** main-worktree file (the `into` path), never the reverse — the worktree copy is the ephemeral one. Promoting *adds* to canonical and leaves the worktree entry in place (it may still be in active use).
- Only `settings.local.json` drift is high-stakes: it's gitignored and per-worktree, so it's gone on prune. `settings.json` is git-tracked — worktree drift there is reported, but committing the worktree's change is usually the right fix, not byte-copying it into canonical.
- Never report a canonical write as done on the strength of having *issued* the write. The symlink hop and `600` mode mean writes can silently fail; only `applied.verified == true` (a successful re-read) counts as persisted.
