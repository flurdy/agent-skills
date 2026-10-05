#!/usr/bin/env python3
"""Read-only evidence and previews for explicit main/master upstream integration."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MAX_COMMITS = 200
MAX_REFS = 5000
OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
READS = {"rev-parse", "symbolic-ref", "status", "config", "for-each-ref", "merge-base",
         "rev-list", "show", "diff", "patch-id", "cherry", "reflog", "rebase", "remote"}
REBASE_FLAGS = ["--merge", "--no-autostash", "--no-autosquash", "--no-update-refs",
                "--no-rebase-merges", "--no-fork-point", "--no-rerere-autoupdate",
                "--reapply-cherry-picks", "--empty=stop"]


class Refusal(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


class Git:
    def __init__(self, args):
        self.repo = Path(args.repo).resolve()
        require(bool(args.mgit) == bool(args.service), "mgit and service must be supplied together")
        self.wrapper = str(Path(args.mgit).absolute()) if args.mgit else None
        self.service = args.service
        self.cwd = Path.cwd().resolve()
        self.route = {"repo": str(self.repo), "mgit": self.wrapper,
                      "service": self.service, "cwd": str(self.cwd)}
        overrides = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE")
        require(not any(os.environ.get(key) for key in overrides), "repository environment overrides are not supported")
        self.env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
                    "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}

    def argv(self, command, *args):
        if self.wrapper:
            return [self.wrapper, command, self.service, *args]
        return ["git", "-C", str(self.repo), command, *args]

    def run(self, command, *args, input=None, codes=(0,)):
        require(command in READS, "not a read-only Git query")
        modes = {"config": {"--get-all"}, "reflog": {"show", "exists"}, "remote": {"get-url"}}
        if command in modes:
            require(args and args[0] in modes[command], "not a read-only Git query")
        if command == "rebase":
            require(args == ("-h",), "not a read-only Git query")
        if command == "symbolic-ref":
            require(args == ("--quiet", "--short", "HEAD"), "not a read-only Git query")
        try:
            result = subprocess.run(self.argv(command, *args), cwd=self.cwd, env=self.env,
                                    input=input, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refusal(f"Git {command} unavailable or timed out") from error
        require(result.returncode in codes, f"Git {command} failed (exit {result.returncode}); evidence unavailable")
        return result

    def text(self, command, *args):
        return self.run(command, *args).stdout.strip()

    def config(self, key):
        return self.run("config", "--get-all", key, codes=(0, 1)).stdout.splitlines()

    def oid(self, ref):
        value = self.text("rev-parse", "--verify", f"{ref}^{{commit}}")
        require(OID.fullmatch(value), "expected a full commit object ID")
        return value

    def ancestor(self, first, second):
        return self.run("merge-base", "--is-ancestor", first, second, codes=(0, 1)).returncode == 0

    def path(self, name):
        value = self.text("rev-parse", "--path-format=absolute", "--git-path", name)
        require(Path(value).is_absolute() and "\n" not in value, "Git must support absolute --git-path output")
        return Path(value)


def inspect(git):
    top = Path(git.text("rev-parse", "--show-toplevel")).resolve()
    require(top == git.repo, "Git route selected a different repository")
    branch = git.run("symbolic-ref", "--quiet", "--short", "HEAD", codes=(0, 1)).stdout.strip()
    require(branch in ("main", "master"), "upstream mode requires attached main or master")
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "BISECT_LOG",
                 "rebase-merge", "rebase-apply", "sequencer", "index.lock"):
        require(not git.path(name).exists(), f"in-progress Git operation or lock: {name}")
    require(not git.text("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none"),
            "dirty working tree or index; stop before integration")
    require(git.text("rev-parse", "--is-shallow-repository") == "false", "shallow history is insufficient")
    require(not git.text("for-each-ref", "--format=%(refname)", "refs/replace"), "replacement history is unsupported")
    grafts = git.path("info/grafts")
    require(not grafts.exists() or grafts.stat().st_size == 0, "grafted history is unsupported")
    git.run("reflog", "exists", f"refs/heads/{branch}")
    remotes = git.config(f"branch.{branch}.remote")
    merges = git.config(f"branch.{branch}.merge")
    require(len(remotes) == len(merges) == 1, "missing or ambiguous configured upstream")
    remote, merge = remotes[0], merges[0]
    require(remote and remote != "." and not remote.startswith("-"), "expected a named remote upstream")
    require(merge == f"refs/heads/{branch}", "unexpected upstream branch; matching trunk name required")
    upstream = git.text("rev-parse", "--symbolic-full-name", "@{upstream}")
    require(upstream.startswith("refs/remotes/"), "upstream must resolve to a remote-tracking ref")
    actual = git.text("for-each-ref", "--format=%(upstream:remotename)%00%(upstream:remoteref)", f"refs/heads/{branch}")
    require(actual.split("\0") == [remote, merge], "ambiguous upstream mapping")
    config = {key: git.config(f"remote.{remote}.{key}") for key in ("url", "pushurl", "fetch", "mirror")}
    require(config["url"] and config["fetch"], "missing upstream remote configuration")
    config["effective_fetch_urls"] = git.text("remote", "get-url", "--all", remote).splitlines()
    config["effective_push_urls"] = git.text("remote", "get-url", "--push", "--all", remote).splitlines()
    config_digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    refs = git.text("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes", "refs/tags").splitlines()
    require(len(refs) <= MAX_REFS, "too many refs for bounded analysis")
    other_refs = [line for line in refs if not line.startswith(f"refs/heads/{branch} ")]
    identity = {"repository": str(top), "git_dir": str(git.path(".")),
                "common_dir": git.text("rev-parse", "--path-format=absolute", "--git-common-dir"),
                "branch": branch, "upstream": upstream, "remote": remote, "merge_ref": merge,
                "remote_config_digest": config_digest, "route": git.route}
    return {"version": 1, "kind": "upstream-inspection", "identity": identity,
            "head": git.oid("HEAD"), "target": git.oid(upstream), "other_refs": other_refs,
            "fetch_command": git.argv("fetch", "--no-tags", "--no-recurse-submodules", remote, f"{merge}:{upstream}")}


def validate_record(record, kind):
    require(isinstance(record, dict) and record.get("version") == 1 and record.get("kind") == kind,
            "invalid or unsupported evidence record")
    return record


def commits(git, base, head):
    values = git.text("rev-list", "--reverse", "--topo-order", f"{base}..{head}").splitlines()
    require(len(values) <= MAX_COMMITS, "too many commits for bounded analysis")
    return values


def patch_id(git, oid):
    patch = git.run("diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--binary", f"{oid}^", oid, "--").stdout
    require(patch, "empty local commits require a separate disposition")
    fields = git.run("patch-id", "--stable", input=patch).stdout.split()
    require(fields and OID.fullmatch(fields[0]), "patch identity unavailable")
    return fields[0]


def replay(git, base, head):
    require(not git.text("rev-list", "--min-parents=2", f"{base}..{head}"), "local merge commits require a separate disposition")
    return [{"oid": oid, "subject": git.text("show", "-s", "--format=%s", oid), "patch_id": patch_id(git, oid)}
            for oid in commits(git, base, head)]


def plan(git, before, current):
    validate_record(before, "upstream-inspection")
    validate_record(current, "upstream-inspection")
    require(before["identity"] == current["identity"], "repository, route or upstream configuration changed")
    require(before["head"] == current["head"], "source HEAD changed since inspection")
    for oid in (before["head"], before["target"], current["target"]):
        require(isinstance(oid, str) and OID.fullmatch(oid), "invalid pinned commit identity")
    head, target = current["head"], current["target"]
    require(git.ancestor(before["target"], target), "upstream rewound or was rewritten; stop")
    local = []
    command = []
    if head == target:
        classification, base = "unchanged", head
    elif git.ancestor(target, head):
        classification, base = "local-ahead", target
    elif git.ancestor(head, target):
        classification, base = "fast-forward", head
        command = git.argv("merge", "--ff-only", target)
    else:
        bases = git.run("merge-base", "--all", head, target, codes=(0, 1)).stdout.splitlines()
        require(len(bases) == 1, "unrelated or ambiguous common history")
        classification, base = "replay", bases[0]
        local = replay(git, base, head)
        private = set(git.text("rev-list", f"{base}..{head}", "--not", "--remotes", "--tags",
                               f"--exclude={current['identity']['branch']}", "--branches").splitlines())
        require(private == {item["oid"] for item in local}, "replay range is reachable from another branch, tag or remote ref")
        cherries = git.text("cherry", target, head, base).splitlines()
        require(all(line.startswith("+ ") for line in cherries), "upstream-equivalent patches require a separate disposition")
        help_result = git.run("rebase", "-h", codes=(0, 129))
        help_text = help_result.stdout + help_result.stderr
        require(all(word in help_text for word in ("update-refs", "autostash", "autosquash", "reapply-cherry-picks", "rerere-autoupdate"))
                and re.search(r"--empty[^\n]*\bstop\b", help_text), "installed Git lacks required safe rebase options")
        command = git.argv("rebase", *REBASE_FLAGS, "--onto", target, base, current["identity"]["branch"])
    source_commits = commits(git, base, head)
    remote_commits = [{"oid": oid, "subject": git.text("show", "-s", "--format=%s", oid)}
                      for oid in commits(git, base, target)]
    return {"version": 1, "kind": "upstream-plan", "before": before, "current": current,
            "classification": classification, "base": base, "source_commits": source_commits,
            "remote_commits": remote_commits, "replay": local, "recovery_head": head, "command": command,
            "limits": ["Fresh fetch execution must be observed by the caller; this helper cannot attest it.",
                       "No containing local ref does not prove global nonpublication; human confirmation is required.",
                       "A current check is not an atomic lock or permission to execute the preview."]}


def check(git, record):
    validate_record(record, "upstream-plan")
    expected = plan(git, record["before"], inspect(git))
    require(expected == record, "stale or altered plan; inspect and preview again")
    return {"version": 1, "status": "current", "command": expected["command"]}


def verify(git, record):
    validate_record(record, "upstream-plan")
    now = inspect(git)
    current = record["current"]
    require(now["identity"] == current["identity"] and now["target"] == current["target"]
            and now["other_refs"] == current["other_refs"], "integration identities or other refs changed")
    require(plan(git, record["before"], current) == record, "altered plan")
    classification = record["classification"]
    head, target, old_head = now["head"], current["target"], current["head"]
    if classification in ("unchanged", "local-ahead"):
        require(head == old_head, "no-op source changed")
    else:
        require(git.oid("ORIG_HEAD") == old_head, "pre-operation recovery identity does not match the preview")
        log = git.text("reflog", "show", "-2", "--format=%H", f"refs/heads/{now['identity']['branch']}").splitlines()
        require(log == [head, old_head], "branch reflog does not bind this integration to the preview")
        if classification == "fast-forward":
            require(head == target, "fast-forward did not land at the pinned target")
        else:
            require(git.ancestor(target, head), "fetched target is not preserved as an ancestor")
            actual = replay(git, target, head)
            require([item["patch_id"] for item in actual] == [item["patch_id"] for item in record["replay"]],
                    "replayed patches changed; manual range-diff review and disposition required")
    require(git.ancestor(target, head), "fetched target ancestry was not preserved")
    return {"version": 1, "status": "verified", "head": head, "target": target,
            "limits": "Ancestry and stable patch equivalence only; conflict review and repository tests remain caller-owned.",
            "range_diff_command": git.argv("range-diff", f"{record['base']}..{old_head}", f"{target}..{head}")}


def load(path):
    require(path is not None, "missing evidence file")
    if path == "-":
        data = sys.stdin.buffer.read(1024 * 1024 + 1)
    else:
        with Path(path).open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, "evidence exceeds 1 MiB")
    return json.loads(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "plan", "check", "verify"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mgit", help="explicit trusted wrapper, invoked from the current working directory")
    parser.add_argument("--service")
    parser.add_argument("--before", help="pre-fetch inspect JSON for plan; - reads stdin")
    parser.add_argument("--plan", help="unchanged preview JSON for check or verify; - reads stdin")
    args = parser.parse_args()
    try:
        git = Git(args)
        if args.action == "inspect":
            result = inspect(git)
        elif args.action == "plan":
            result = plan(git, load(args.before), inspect(git))
        elif args.action == "check":
            result = check(git, load(args.plan))
        else:
            result = verify(git, load(args.plan))
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        reason = str(error) if isinstance(error, Refusal) else "invalid or unavailable evidence"
        print(json.dumps({"version": 1, "status": "refuse", "reason": reason}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
