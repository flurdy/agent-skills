#!/usr/bin/env python3
"""Read cached Git history for recap; never fetch, checkout or change configuration."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess


FAILURES = (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError)


def run(*command):
    return subprocess.check_output(
        command, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        timeout=30,
    ).rstrip("\n")


def git(repo, *args):
    return run("git", "-C", repo, *args)


def config_emails(repo, key):
    try:
        return git(repo, "config", "--get" if key == "user.email" else "--get-all", key).splitlines()
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return []
        raise


def github_emails():
    emails = []
    diagnostics = []
    try:
        account = json.loads(run("gh", "api", "user", "--jq", "{login,id,email}"))
        if not isinstance(account, dict) or not account.get("login") or not account.get("id"):
            raise ValueError("invalid GitHub identity")
        login = account["login"]
        emails.extend([
            account.get("email"), f"{login}@users.noreply.github.com",
            f"{account['id']}+{login}@users.noreply.github.com",
        ])
    except FAILURES:
        diagnostics.append("GitHub author identities unavailable; using configured local emails only.")
        return set(), diagnostics
    try:
        private = json.loads(run("gh", "api", "user/emails", "--jq", "[.[] | select(.verified) | .email]"))
        if not isinstance(private, list) or not all(isinstance(email, str) for email in private):
            raise ValueError("invalid GitHub email list")
        emails.extend(private)
    except FAILURES:
        diagnostics.append("GitHub email aliases unavailable; configure activity.authorEmail for missing identities.")
    return {email.lower() for email in emails if isinstance(email, str) and email}, diagnostics


def sources(repo, diagnostics):
    """Prefer worktree attribution; add unchecked branches and the cached default ref."""
    found = []
    for record in git(repo, "worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = dict(field.split(" ", 1) for field in record.split("\0") if " " in field)
        sha = fields.get("HEAD", "")
        if sha and set(sha) != {"0"}:
            found.append((sha, Path(fields["worktree"]).name,
                          fields.get("branch", "HEAD").removeprefix("refs/heads/")))
    refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin").splitlines()
    found.extend((ref, Path(repo).name, ref.removeprefix("refs/heads/"))
                 for ref in refs if ref.startswith("refs/heads/"))
    try:
        default = git(repo, "symbolic-ref", "refs/remotes/origin/HEAD")
    except subprocess.CalledProcessError:
        default = ""
    if default not in refs:
        default = ""
        diagnostics.append("cached origin default branch unknown; scanning any cached origin/main and origin/master.")
    defaults = [default] if default else [ref for ref in refs if ref in (
        "refs/remotes/origin/main", "refs/remotes/origin/master"
    )]
    for ref in defaults:
        branch = ref.removeprefix("refs/remotes/origin/")
        label = f"origin/{branch}"
        found.append((ref, Path(repo).name, label))
        local = f"refs/heads/{branch}"
        if local in refs:
            try:
                behind = int(git(repo, "rev-list", "--count", f"{local}..{ref}"))
                if behind:
                    diagnostics.append(f"{branch} is {behind} commit(s) behind cached {label}; cached commits included.")
            except FAILURES:
                diagnostics.append(f"Cached {label} lag unavailable; commit collection continues.")
    return found


def collect(repo, start, end, account_emails):
    diagnostics = []
    rows = []
    seen = set()
    status = "OK"
    try:
        git(repo, "rev-parse", "--git-dir")
        emails = account_emails | {
            value.strip().lower()
            for key in ("user.email", "activity.authorEmail")
            for value in config_emails(repo, key) if value.strip()
        }
        if not emails:
            return "NO_AUTHOR", rows, ["No author identities available."]
        refs = sources(repo, diagnostics)
        for ref, worktree, branch in refs:
            try:
                output = git(
                    repo, "log", ref, f"--since-as-filter={start.isoformat()}",
                    "--no-merges", "--format=%H%x00%h%x00%ae%x00%ct%x00%s", "--",
                )
                for line in output.split("\n"):
                    if not line:
                        continue
                    sha, short, email, timestamp, subject = line.split("\0", 4)
                    when = datetime.fromtimestamp(int(timestamp)).astimezone()
                    if sha in seen or email.lower() not in emails or not start <= when < end:
                        continue
                    seen.add(sha)
                    weekday = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[when.weekday()]
                    rows.append((timestamp, worktree, branch, short, subject,
                                 f"{weekday} {when:%Y-%m-%d %H:%M:%S %z}"))
            except FAILURES:
                status = "ERROR"
                diagnostics.append(f"Could not read commit history for {branch}; other refs retained.")
    except FAILURES:
        status = "ERROR"
        diagnostics.append("Could not enumerate repository history or identities.")
    rows.sort(key=lambda row: (int(row[0]), row[3]), reverse=True)
    return status, [row[1:] for row in rows], diagnostics


def clean(value):
    return " ".join(str(value).replace("|", "¦").splitlines())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--repo", nargs=2, action="append", default=[])
    args = parser.parse_args()
    start, end = datetime.fromisoformat(args.since), datetime.fromisoformat(args.until)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        parser.error("expected ordered timezone-aware bounds")
    account_emails, diagnostics = github_emails() if args.repo else (set(), [])
    statuses, commits = [], []
    for name, repo in args.repo:
        status, rows, notes = collect(repo, start, end, account_emails)
        statuses.append((name, status))
        commits.extend((name, *row) for row in rows)
        diagnostics.extend(f"{clean(name)}: {clean(note)}" for note in notes)
    if args.repo:
        diagnostics.append(
            "Searched local branches, worktree HEADs and cached origin default refs by committer date; "
            "no fetch performed, so unfetched/pruned history may be missing. Remote freshness is unknown."
        )
    print("---COMMIT-STATUS---")
    for row in statuses:
        print("|".join(map(clean, row)))
    print("---COMMIT-DIAGNOSTICS---")
    print("\n".join(diagnostics))
    print("---COMMITS---")
    for row in commits:
        print("|".join(map(clean, row)))


if __name__ == "__main__":
    main()
