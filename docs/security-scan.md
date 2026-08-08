# Baseline security scan

How to re-run the repository's security scan and how to read its output.

```bash
make security-scan
```

## Scope

Skills (`skills/*/SKILL.md` and their `scripts/`), repository tooling
(`scripts/`, `assemble.sh`, `Makefile`), templates, and the validation tooling
itself.

## Exclusions

- **`skills/*/tests/` and `tests/`.** Test harnesses use deliberate credential
  sentinels (`OPENROUTER_API_KEY=test-key`), fixed paths, and permissive
  `chmod` on stub executables. Scanning them yields noise, not signal.
- **`.beads/`.** Local runtime state, gitignored. Its vendor documentation
  contains a `curl | bash` install line that is not part of this repo's build.
- **MCP server internals.** `mcp__jira__*`, `mcp__recraft__*` and the browser
  servers are implemented outside this repository. The scan covers how skills
  *use* them, not their transport security.
- **The private overlay.** `agent-skills-private` is referenced by
  `.env.example` but is a separate repository.
- **`skills/browser-screenshot/scripts/screenshot.mjs`.** JavaScript; no
  automated check covers it. Review by hand.

## Severity

| Level | Meaning |
|---|---|
| `HIGH` | Confirmed defect with a concrete local attacker or data-exposure path. |
| `MEDIUM` | Confirmed defect requiring a precondition, or silent-wrong-answer bug. |
| `LOW` | Real but narrow: hardening gap, or requires an unusual local config. |
| `ADVISORY` | Candidate list from a heuristic. Requires human triage — expect legitimate entries. |

`ADVISORY` findings are **not** assertions of a defect. The two heuristic
checks flag every skill matching a coarse pattern; most entries will be fine.
They exist so a reviewer can scan a bounded list rather than 63 skills.

## Mechanical checks

The script detects the classes below. Each was derived from a confirmed finding
in the 2026-08-08 baseline scan.

| Check | Detects |
|---|---|
| `credentials-in-argv` | Secrets in `curl -H` argv (same-UID readable; cross-user depends on `/proc` policy) |
| `curl-honours-user-config` | Auth-bearing `curl` without `--disable` (a `~/.curlrc` with `trace-ascii` writes the header to disk) |
| `git-format-injection` | Untrusted text interpolated into `git log --format`; `%` placeholders in branch names expand into the parsed stream |
| `worktree-field-split` | `git worktree list --porcelain` parsed by `$2`, truncating paths containing spaces |
| `fixed-temp-path` | Predictable `/tmp` paths another local user can pre-claim |
| `shell-execution-sink` | `eval`, `bash -c "$VAR"`, `curl \| sh` |
| `python-execution-sink` | `shell=True`, `os.system`, `eval`/`exec`, `pickle.loads`, unsafe `yaml.load` |
| `unattended-shell-agent` | Agent CLI spawned non-interactively with a shell tool enabled |
| `missing-injection-guard` | *(advisory)* Skill ingests remote text without untrusted-data framing |
| `readonly-claim-vs-grant` | *(advisory)* Skill claims read-only while holding a wildcard grant permitting the forbidden action |

## Manual pass

These dimensions need judgment and are not automated. Work through them when
doing a full baseline rather than a regression check.

1. **Destructive-operation gates.** For every skill that pushes, force-pushes,
   merges, retargets a PR, or mutates an external tracker: is the action gated
   by an explicit `AskUserQuestion`, or only by prose an agent could rationalise
   past? Prose is not a gate.
2. **Read-only claims.** For each skill asserting read-only or passive
   behaviour, verify the claim against both its scripts *and* its
   `allowed-tools`. Withholding `Edit`/`Write` while granting `Bash(git:*)`
   does not make a skill read-only.
3. **Untrusted-content handling.** Skills reading PR bodies, review comments,
   Jira/Confluence/Trello text, or fetched logs should frame that content as
   data. Four skills carry the guard — `diagnose-bug`, `outstanding-work`,
   `project-brief`, `watch-admin` — and their wording is the reference.
4. **Content laundering.** Text imported from an external tracker into a bead
   loses its untrusted provenance; downstream skills then read it as internal.
5. **Third-party egress.** Does the skill send repository contents to an
   external service, and is consent keyed to *data disclosure* rather than to
   billing?
6. **Unattended loops.** `watch-*` skills run with no human present. Any
   mutation reachable from a tick needs a permission-layer constraint, not a
   prose one.

## Known gaps

- No CI. Nothing runs `clean-code`, `validate-skills`, the `test-*` targets, or
  this scan automatically; every gate is opt-in and manual.
- No Python static analysis. `make clean-code` covers shell only (`bash -n`,
  `shellcheck`). There is no ruff/bandit target.
- `scripts/validate-skills.py` enforces no safety property — it does not
  inspect what `allowed-tools` actually grants.
- The scan is static. It reads source; it does not observe runtime behaviour.
