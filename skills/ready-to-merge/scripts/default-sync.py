#!/usr/bin/env python3
"""Read-only post-merge default-branch sync planner; never executes its previews."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
READS = {"rev-parse", "symbolic-ref", "status", "config", "remote", "for-each-ref",
         "merge-base", "rev-list", "worktree", "check-ref-format", "ls-files"}
OPERATIONS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "BISECT_LOG",
              "rebase-merge", "rebase-apply", "sequencer", "index.lock", "HEAD.lock", "packed-refs.lock")


class Skip(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Skip(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def github_identity(url):
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
    return match[1].lower() if match else None


class Git:
    def __init__(self, args):
        self.repo = Path(args.repo).resolve()
        self.wrapper = str(Path(args.mgit).absolute()) if args.mgit else None
        self.service = args.service
        self.cwd = str(Path.cwd().resolve())
        require(bool(self.wrapper) == bool(self.service), "mgit and service must be supplied together")
        require(not any(os.environ.get(k) for k in (
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE", "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_COUNT", "GIT_NAMESPACE")), "Git environment overrides are unsupported")
        for start in (Path.cwd().resolve(), self.repo):
            if any((p / ".mgit.conf").exists() for p in (start, *start.parents)):
                require(self.wrapper, "configured workspace requires its trusted mgit route")
        self.env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
                    "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}

    def argv(self, command, *args, repo=None):
        if self.wrapper:
            return [self.wrapper, command, str(repo) if repo else self.service, *args]
        return ["git", "-C", str(repo or self.repo), command, *args]

    def run(self, command, *args, repo=None, codes=(0,)):
        require(command in READS, "not a read-only query")
        modes = {"config": {"--get-all"}, "remote": {"get-url"}, "worktree": {"list"},
                 "symbolic-ref": {"--quiet"}}
        if command in modes and not (command == "remote" and not args):
            require(args and args[0] in modes[command], "not a read-only query")
        try:
            result = subprocess.run(self.argv(command, *args, repo=repo), cwd=self.cwd,
                                    env=self.env, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Skip(f"Git {command} unavailable or timed out") from error
        require(result.returncode in codes, f"Git {command} evidence unavailable (exit {result.returncode})")
        return result

    def text(self, command, *args, repo=None):
        return self.run(command, *args, repo=repo).stdout.strip()

    def config(self, key):
        return self.run("config", "--get-all", key, codes=(0, 1)).stdout.splitlines()

    def oid(self, ref):
        oid = self.text("rev-parse", "--verify", f"{ref}^{{commit}}")
        require(OID.fullmatch(oid), "missing full commit identity")
        return oid

    def path(self, name, repo=None):
        return Path(self.text("rev-parse", "--path-format=absolute", "--git-path", name, repo=repo))

    def ancestor(self, first, second):
        return self.run("merge-base", "--is-ancestor", first, second, codes=(0, 1)).returncode == 0


def inspect(git, args):
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.github), "invalid GitHub repository identity")
    require(OID.fullmatch(args.merge_commit), "merge commit must be a full object ID")
    require(args.default and not args.default.startswith("-") and not any(c.isspace() for c in args.default), "invalid default branch")
    ref = f"refs/heads/{args.default}"
    git.run("check-ref-format", ref)
    require(Path(git.text("rev-parse", "--show-toplevel")).resolve() == git.repo, "route selects another checkout")
    require(git.text("rev-parse", "--is-shallow-repository") == "false", "shallow history is unsupported")
    require(not git.text("for-each-ref", "--format=%(refname)", "refs/replace"), "replacement history is unsupported")
    grafts = git.path("info/grafts")
    require(not grafts.exists() or grafts.stat().st_size == 0, "grafted history is unsupported")
    require(not git.config("submodule.recurse") or git.config("submodule.recurse") == ["false"], "submodule recursion configuration is unsupported")
    require(git.run("symbolic-ref", "--quiet", ref, codes=(0, 1)).returncode == 1,
            "symbolic default-branch ref is unsupported")
    local = git.oid(ref)
    remotes, merges = git.config(f"branch.{args.default}.remote"), git.config(f"branch.{args.default}.merge")
    require(len(remotes) == 1 and merges == [ref], "missing or ambiguous configured upstream")
    remote = remotes[0]
    require(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", remote), "unsupported remote name")
    matches = []
    for name in git.text("remote").splitlines():
        urls = git.text("remote", "get-url", "--all", name).splitlines()
        if len(urls) == 1 and github_identity(urls[0]) == args.github.lower():
            matches.append(name)
    require(matches == [remote], "no unique upstream remote matching the merged GitHub repository")
    tracking = f"refs/remotes/{remote}/{args.default}"
    upstream = git.text("for-each-ref", "--format=%(upstream)", ref)
    require(upstream == tracking, "unexpected remote-tracking mapping")
    config = {key: git.config(key) for key in (
        f"remote.{remote}.url", f"remote.{remote}.fetch", f"remote.{remote}.mirror",
        "fetch.pruneTags", "fetch.prune", "merge.autoStash", "submodule.recurse")}
    config["effective_urls"] = git.text("remote", "get-url", "--all", remote).splitlines()
    common = git.text("rev-parse", "--path-format=absolute", "--git-common-dir")
    raw = git.run("worktree", "list", "--porcelain", "-z").stdout
    worktrees = []
    for block in raw.strip("\0").split("\0\0"):
        fields = dict((line.split(" ", 1) + [""])[:2] for line in block.split("\0"))
        require(fields.get("worktree"), "malformed worktree inventory")
        worktrees.append(fields)
    targets = [w for w in worktrees if w.get("branch") == ref]
    require(len(targets) <= 1, "default branch checked out in multiple worktrees")
    target = None
    if targets:
        wt = targets[0]
        require(not any(k in wt for k in ("locked", "prunable", "bare")), "default worktree locked, prunable or bare")
        target = str(Path(wt["worktree"]).resolve())
        require(Path(target).is_dir(), "default worktree unavailable")
        require(git.text("rev-parse", "--path-format=absolute", "--git-common-dir", repo=target) == common,
                "default worktree belongs to another repository")
        require(git.text("symbolic-ref", "--quiet", "HEAD", repo=target) == ref, "default worktree changed branch")
        require(not git.text("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none", repo=target),
                "default worktree or index is dirty")
        require(not any(line.startswith("160000 ") for line in git.text("ls-files", "--stage", repo=target).splitlines()),
                "submodule worktrees require separate handling")
    for checkout in {str(git.repo), target} - {None}:
        for name in (*OPERATIONS, f"{ref}.lock"):
            require(not git.path(name, repo=checkout).exists(), f"in-progress operation or lock: {name}")
    source_branch = git.run("symbolic-ref", "--quiet", "HEAD", codes=(0, 1)).stdout.strip()
    return {"version": 1, "status": "inspected", "github": args.github, "default": args.default,
            "merge_commit": args.merge_commit, "repo": str(git.repo), "common": common,
            "route": {"mgit": git.wrapper, "service": git.service, "cwd": git.cwd},
            "config_digest": digest(config), "worktrees": worktrees, "source_branch": source_branch,
            "source_head": git.oid("HEAD"), "local": local, "tracking": tracking,
            "tracking_oid": git.oid(tracking), "worktree": target,
            "fetch_command": git.argv("fetch", "--no-tags", "--no-recurse-submodules", "--no-prune",
                                      "--no-prune-tags", "--refmap=", remote, f"{ref}:{tracking}")}


def plan(git, args, before):
    require(isinstance(before, dict) and before.get("status") == "inspected" and before.get("version") == 1,
            "invalid pre-fetch inspection")
    current = inspect(git, args)
    require({k: v for k, v in before.items() if k != "tracking_oid"} ==
            {k: v for k, v in current.items() if k != "tracking_oid"}, "local state, route or configuration changed")
    old, target = current["local"], current["tracking_oid"]
    require(git.ancestor(before["tracking_oid"], target), "remote history rewound or rewritten")
    require(git.ancestor(args.merge_commit, target), "merge commit is not contained in fetched default branch")
    command = []
    if old == target:
        status = "noop"
    elif git.ancestor(target, old):
        raise Skip("local default branch is ahead; leave it unchanged")
    elif not git.ancestor(old, target):
        raise Skip("local default branch diverged; leave it unchanged")
    elif current["worktree"]:
        status = "ff-worktree"
        command = git.argv("merge", "--ff-only", "--no-autostash", target, repo=current["worktree"])
    else:
        status = "ff-ref"
        command = git.argv("fetch", "--no-tags", "--no-recurse-submodules", "--no-prune", "--no-prune-tags",
                           "--no-write-fetch-head", "--refmap=", ".", f"{target}:refs/heads/{args.default}")
    return {"version": 1, "status": status, "before": before, "current": current,
            "target": target, "command": command,
            "extra_commits": int(git.text("rev-list", "--count", f"{args.merge_commit}..{target}")),
            "limits": "Caller must observe a fresh approved fetch; this read-only plan is not authorization or an atomic lock."}


def check(git, args, record):
    require(isinstance(record, dict) and record.get("version") == 1, "invalid plan")
    require(plan(git, args, record["before"]) == record, "stale or altered plan")
    return {"status": "current", "command": record["command"]}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("inspect", "plan", "check"))
    p.add_argument("--repo", required=True)
    p.add_argument("--github", required=True)
    p.add_argument("--default", required=True)
    p.add_argument("--merge-commit", required=True)
    p.add_argument("--mgit")
    p.add_argument("--service")
    return p


def main():
    args = parser().parse_args()
    try:
        git = Git(args)
        if args.action == "inspect":
            result = inspect(git, args)
        else:
            data = sys.stdin.read(1024 * 1024 + 1)
            require(len(data) <= 1024 * 1024, "evidence exceeds 1 MiB")
            record = json.loads(data)
            result = plan(git, args, record) if args.action == "plan" else check(git, args, record)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Skip, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"version": 1, "status": "skip", "reason": str(error) if isinstance(error, Skip) else "invalid or unavailable evidence"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
