### Multi-Repo Git Commands

Each service folder is its own **independent git repository** — they are NOT submodules, NOT part of the root repo. The root `.gitignore` excludes all service folders.

**Rule: Always use `./scripts/gitc <subcommand> <service>` for service git operations.** This wrapper runs `git -C` under the hood but puts the subcommand first and service last, enabling permission patterns to distinguish safe vs dangerous operations.

Never use `cd <service> && git ...` (breaks auto-approval). Never run bare `git add/status/commit` expecting it to pick up service files — that targets the root repo.

```bash
# CORRECT — works from anywhere, auto-approvable for safe operations
./scripts/gitc status my-service --short
./scripts/gitc diff my-service
./scripts/gitc add my-service src/main/MyFile.scala
./scripts/gitc commit my-service -m "fix: something"
./scripts/gitc log my-service --oneline -5

# WRONG — requires manual approval (permission wildcards don't match mid-string)
git -C my-service status --short

# WRONG — requires manual approval
cd my-service && git status --short

# WRONG — targets root repo, service folders are gitignored
git add my-service/src/main/MyFile.scala
git status  # only shows root repo changes
```

**Which repo does a file belong to?** Check the first path component after the project root:
- If it matches a service name listed in `.gitc.conf` → use `./scripts/gitc <subcommand> <service>`
- If it's a root-level file (AGENTS.md, docs/, scripts/, etc.) → use the root repo directly

**Multiple services in one session:** When committing changes across multiple services, run separate `./scripts/gitc` commands for each service. Each service gets its own commit.
