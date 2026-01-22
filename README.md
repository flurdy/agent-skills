# Agent Skills

AI agent skills shared across clients and machines. These are the common building
blocks that get assembled into active AI agent skill sets for Claude or Codex, and other AI agents.

## Using the skills

1. Clone this repo.

   `git clone https://github.com/flurdy/agent-skills.git`

2. Apply the changes from the `agent-skills/` folder.
   
   `make apply`

3. Verify skills are in `~/.claude/skills` (symlinked to `~/.claude/skills.active`).

## Layout

- `skills/`: each skill lives in its own folder with a `SKILL.md`
- Optional: `assets/`, `scripts/`, or `references/` inside a skill folder if needed

```plaintext
agent-skills/
  skills/
    common-skill/
      SKILL.md
  assemble.sh
  Makefile
```

## Private skills 

If you have machine- or client-specific skills or overrides, you can create a
__sibling__ repo named `agent-skills-private/` alongside this `agent-skills/` repo.

(You are free to name it something else, but you'll need to set the `PRIVATE_REPO` environment variable, see below).

This `agent-skills-private/` repo is optional, and can be kept private and secure. With both repos the layout is this:

```plaintext
agent-skills/
  skills/
    common-skill/
      SKILL.md
  assemble.sh
  Makefile
agent-skills-private/
  clients/
    my-client/
      skills/
         my-private-skill/
           SKILL.md
   machines/
     my-machine/
       skills/
         my-machine-skill/
           SKILL.md
   profiles/
     my-machine-profile.env
```

You can then specify machine or clients specific skills to use:

`make apply MACHINE=my-machine CLIENTS="my-client my-other-client"`

Or instead configure `private/profiles/my-machine-profile.env` with:

```properties
MACHINE=my-machine
CLIENTS="my-client my-other-client"
```

`make apply PROFILE=my-machine-profile` to do the same

### Layering order

When applying skills, if a skill exists in multiple places, the layering order is:

1. Shared skills from `agent-skills/skills/`
2. Private machine skills from `agent-skills-private/machines/<machine>/skills/`
3. Private client skills from `agent-skills-private/clients/<client>/skills/`

## Common vars

Set these in as environment variables, or accept the defaults.

Path to shared repo (this repo):

- `SHARED_REPO=/path/to/agent-skills`

Path to optional private repo:

- `PRIVATE_REPO=/path/to/agent-skills-private`

Path to active skills and target skills directory, can be Codex or Claude:

- `ACTIVE_DIR=$HOME/.claude/skills.active`
- `SKILLS_DIR=$HOME/.claude/skills`

There is example in `.env.example` you can use,
and an example `.envrc.example` file if you use [direnv](https://direnv.net/).

## Adding a new skill

1. Create a folder under `skills/`
2. Add a `SKILL.md` with the skill's instructions and triggers
3. Keep it focused and general-purpose
4. If you need supporting material, add it inside the skill folder
5. Test by running `make apply` and verifying it appears in `~/.claude/skills`

## Known Issues

- Caveat: this assumes the target skills folder is empty or not there.

  Workaround: Move skills to the private repo 
  and run `make clean` first to remove any existing skills.

> [!WARNING]
> Running `make clean` will delete all existing skills in the target skills folder.


## Bugs and pull requests

- Please report bugs and issues at [github.com/flurdy/agent-skills/issues](https://github.com/flurdy/agent-skills/issues).
- Pull requests are welcome at [github.com/flurdy/agent-skills/pulls](https://github.com/flurdy/agent-skills/pulls).


## Creator

Created by flurdy (https://flurdy.com).

## License

MIT License. See LICENSE file.
