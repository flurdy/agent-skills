# Project workspace scaffold

`project-workspace` creates a lightweight workspace around one or more software
repositories. The workspace owns cross-project context and Beads tracking; linked
repositories retain their implementation, history, and local instructions.

The first release intentionally provides only `init`. Add-service, refresh, and audit
commands should follow only when real workspace use demonstrates a need.

## Run the CLI

From this repository:

```bash
./scripts/project-workspace init "Example Project"
```

To make the command available on `PATH`, create a user-owned symlink:

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/scripts/project-workspace" ~/.local/bin/project-workspace
```

The command fails if that destination already exists, avoiding replacement of an
unrelated executable. The symlink keeps the templates alongside the checked-out script;
updating this repository updates the command without copying generated code elsewhere.

## Initialise a workspace

For a new project name:

```bash
project-workspace init "Example Project"
```

This creates `./example-project` with an empty repository index by default. Link the
first repository under `repos/` and add its relative path to `workspace.json` when it
exists; after customization, `init` will refuse to overwrite those changes rather than
trying to manage them. Override the destination with `--output`:

```bash
project-workspace init "Example Project" --output ~/Code/example-workspace
```

For an existing Git repository:

```bash
project-workspace init --repo ~/Code/example
```

The default is a sibling directory named `example-workspace`. The source repository is
not moved or modified; the workspace links it as `repos/example`. Use `--output` to
choose another separate directory.

Preview either form without writing:

```bash
project-workspace init --repo ~/Code/example --dry-run
```

## Generated structure

```text
example-workspace/
├── .beads/
├── .git/
├── AGENTS.md
├── Makefile
├── README.md
├── workspace.json
├── docs/
│   ├── adrs/
│   ├── architecture/
│   ├── prds/
│   └── runbooks/
├── infrastructure/
└── repos/
    └── example -> /path/to/example
```

`workspace.json` is the concise machine-readable topology index. Cross-project PRDs,
ADRs, architecture, runbooks, and durable work belong in the workspace. Service- and
infrastructure-specific material remains authoritative in its own repository.

The generated Makefile provides:

```bash
make status
make doctor
```

Configure multi-repository Git behavior separately with `/setup-multirepo-git`; the
scaffold does not create `.mgit.conf` or duplicate that workflow.

## Safety and reruns

- `--dry-run` performs no writes and does not require `git` or `bd`.
- A normal run preflights every managed file and link before creating anything.
- Existing matching output is left unchanged, so the same command is safe to rerun.
- Conflicting files or links stop the command rather than being overwritten.
- Existing Git repositories cannot be reused as workspace output accidentally.
- The workspace root and managed directories cannot be symlinks, preventing writes
  through them into unrelated locations.
- Existing repositories must remain separate from the workspace root.
- Normal initialisation requires Git 2.28 or newer and `bd`. It validates or creates the
  workspace Git repository and always runs idempotent, non-interactive Beads
  initialisation so an interrupted setup can recover safely.
- Beads creates its normal initial tracking commit. The generated workspace files remain
  untracked so they can be reviewed before their first project commit.
