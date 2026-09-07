### Multi-Repo Git Commands

Each service folder is its own **independent git repository** — they are NOT submodules, NOT part of the root repo. The root `.gitignore` excludes all service folders.

**Rule: Always use `./scripts/mgit <subcommand> <service>` for service git operations.** This wrapper runs `git -C` under the hood but puts the subcommand before the service, giving harness-specific permission policies a stable prefix. `Bash(...)` patterns are Claude Code syntax; Codex and Pi require their own controls. The wrapper does not enforce approvals.

Use `root` or `.` as the service name for the root repo.

Never use `cd <service> && git ...` (bypasses the documented wrapper prefix). Never run bare `git add/status/commit` expecting it to pick up service files — that targets the root repo.

```bash
# CORRECT — invoke from the project root using the configured wrapper prefix
./scripts/mgit status my-service --short
./scripts/mgit diff my-service
./scripts/mgit add my-service src/main/MyFile.scala
./scripts/mgit commit my-service -m "fix: something"
./scripts/mgit log my-service --oneline -5

# CORRECT — root repo operations
./scripts/mgit status root --short
./scripts/mgit add . AGENTS.md
./scripts/mgit commit root -m "docs: update agents"

# WRONG for this workflow — bypasses the configured mgit prefix
git -C my-service status --short

# WRONG for this workflow — changes directory and bypasses mgit
cd my-service && git status --short

# WRONG — targets root repo, service folders are gitignored
git add my-service/src/main/MyFile.scala
git status  # only shows root repo changes
```

**Which repo does a file belong to?** Check the first path component after the project root:
- If it matches a service name listed in `.mgit.conf` → use `./scripts/mgit <subcommand> <service>`
- If it's a root-level file (AGENTS.md, docs/, scripts/, etc.) → use `./scripts/mgit <subcommand> root` (or `.`)

**Multiple services in one session:** When committing changes across multiple services, run separate `./scripts/mgit` commands for each service. Each service gets its own commit.
