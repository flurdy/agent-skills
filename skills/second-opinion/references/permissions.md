# Permissions and portability

`allowed-tools` in [SKILL.md](../SKILL.md) is Claude Code metadata. Claude Code pre-approves these
rules only for the turn that invokes the skill; every other tool use still follows the user's own
permission settings. The field restricts nothing and is not a sandbox.

## Grants and their uses

| Grant | Workflow use |
|---|---|
| `Read`, `Grep`, `Glob` | Context gathering (§2) and repository-grounded assessment (§6) |
| `AskUserQuestion` | Missing mode, current-run billing confirmation and OpenRouter consent |
| `Edit(//tmp/**/second-opinion.*/**)` | Caller-file panel artifacts in the `review-panel.sh scratch` directory, written with `Write` or a stdout redirect |
| `Bash(claude -p * --tools Read,Grep,Glob)` | Direct Claude route, limited to the panel route's read-only tools |
| `Bash(codex exec --sandbox read-only *)` | Direct Codex route |
| `Bash(gemini --sandbox -o text *)` | Direct Gemini route |
| `Bash(git ls-files:*)` | `validate-plan` file listing |
| `Bash(~/.agents/skills/second-opinion/scripts/disabled-models.py:*)` | `check-direct` policy gate |
| `Bash(~/.agents/skills/second-opinion/scripts/subscription-route-check.py:*)` | Subscription billing check |
| `Bash(~/.agents/skills/second-opinion/scripts/review-panel.sh:*)` | Panel `check`, `run-*`, `decline-openrouter` and `evaluate`, plus `scratch` and `cleanup` |
| `Bash(~/.agents/skills/review-pr/scripts/gh-pr-snapshot.py:*)` | PR evidence collection and revalidation |

Helper-internal commands need no outer grant: the coordinator launches panel reviewers itself, and
`subscription-route-check.py` runs `claude auth status --json` or `codex login status`. `pwd -P` and
read-only `git` forms are in Claude Code's built-in read-only command set.

## Deliberately not granted

- **Unscoped `Write` or `Edit`:** would pre-approve writes anywhere. Claude Code accepts but never
  matches `Write(path)` rules; the scoped `Edit` rule also covers the `Write` tool and redirects.
- **`rm`, `chmod`, `mktemp`:** replaced by `review-panel.sh scratch` and `cleanup`. The helper creates
  a mode-700 directory, so files inside need no `chmod`. Cleanup removes only a directly nested
  `second-opinion.XXXXXXXXXX` directory owned by the user, never a symlink or other path.
- **`git status`, `git diff`, `git log`, `git rev-parse`:** no workflow uses them, and
  `git diff`/`git log --output=<file>` writes a file.
- **Bare `claude`, `codex` or `gemini` prefixes:** would pre-approve commands such as `claude mcp add`,
  `--dangerously-skip-permissions`, `codex exec --sandbox danger-full-access` or `gemini --yolo`.
- **The guarded stdin pipe:** Claude Code splits pipelines before matching, so a rule containing `|`
  never matches. The [transport](panel-stdin.md) serves guarded Pi sessions, whose guard applies its
  own fixed command shape.

## Limits

- Claude Code matches command text, not program behavior, and `*` spans spaces. Appended flags, such
  as a second `--tools`, can still match. These grants reduce routine prompts for the documented
  shapes; they are not a security boundary. Use Claude Code's sandbox or deny rules for enforcement.
- The `Edit` grant covers scratch directories under `/tmp`, including a nested `$TMPDIR` there. Where
  `$TMPDIR` lives elsewhere, such as the default on macOS, scratch writes prompt rather than fail open.
- Rule semantics were checked against the Claude Code permissions and skills documentation on
  2026-11-05 and with offline tests. Live Claude Code permission matching was not verified.

## Portability

Workflow portability and permission-syntax portability are separate:

- The workflow (modes, routes, helpers, consent and PR checks) is the same in Claude Code, Pi and Codex.
- Pi 1.4.0 lists `allowed-tools` as experimental metadata; its skill loader does not turn it into
  tool authorization. Guarded Pi sessions follow pi-session-mode's own policy ([guarded-plan.md](guarded-plan.md)).
- Codex enforcement of this field is not verified; treat it as unenforced.
- There is no automatic translation into Pi or Codex permission settings. Configure each runtime's own
  permissions separately.

## Why caller files remain outside guarded sessions

The path-free transport carries each request inside the Bash command. Linux limits one argument to
128 KiB (measured on 2026-11-05: 120,000 bytes passed and 140,000 failed with `E2BIG` through
`bash -c`), and Pi 1.4.0 passes the command as one `bash -c` argument (Claude Code's transport is
not verified). An `evaluate` request carries every result: up to 64 KiB per local route and 1 MiB per
OpenRouter response. Full panels can therefore exceed it; guarded sessions disclose that as
unavailable transport.
Avoiding it would need persistent helper state, which the transport excludes, so unguarded panel
runs keep caller files confined to one helper-created private directory.
