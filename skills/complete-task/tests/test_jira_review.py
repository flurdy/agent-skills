"""Behavioral tests for the opt-in Jira review helper and its caller contracts.

The helper runs against fake ``bd`` and ``next-select`` executables in a private tree; no
Jira, tracker or Git remote is contacted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILLS = SKILL.parent
ROOT = SKILLS.parent
HELPER = SKILL / "scripts" / "jira-review.py"
REFERENCE = SKILL / "references" / "jira-review.md"

FAKE_BD = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
directory = Path.cwd()
if args[:1] == ["-C"]:
    directory, args = Path(args[1]), args[2:]
with open(os.environ["BD_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"directory": str(directory.resolve()), "args": args}) + "\n")
if "--readonly" not in args:
    sys.exit("fixture refuses writes")
data = json.loads((directory / ".beads" / "fixture.json").read_text())
faults = data.get("faults", [])
if args[0] == "show":
    if "show-error" in faults:
        sys.exit(9)
    rows = [row for row in data["issues"] if row["id"] == args[1]]
    if not rows:
        sys.exit(1)
    print(json.dumps(rows))
elif args[0] == "list":
    if "list-error" in faults:
        sys.exit(9)
    if "list-malformed" in faults:
        print("{")
        sys.exit(0)
    assert {"--all", "--limit=0", "--flat"} <= set(args), args
    reference = args[args.index("--external-ref") + 1]
    rows = [row for row in data["issues"] if row.get("external_ref") == reference]
    if "drop-ref" in faults:
        rows = [{k: v for k, v in row.items() if k != "external_ref"} for row in rows]
    print(json.dumps(rows))
else:
    sys.exit(2)
'''

FAKE_NEXT_SELECT = r'''#!/usr/bin/env python3
import sys
from pathlib import Path

if sys.argv[1:] != ["stores"]:
    sys.exit(2)
listing = Path.cwd() / ".fake-stores.json"
if not listing.exists():
    print('{"status": "unavailable"}')
    sys.exit(5)
print(listing.read_text())
'''

POLICY = (
    'milestones = ["trunk-commit", "pr-created"]\n'
    'source_statuses = ["In Progress"]\n'
    'target_status = "In Review"\n'
)


def issue(issue_id, status="closed", ref="jira-AB-1", **extra):
    row = {"id": issue_id, "title": f"Title {issue_id}", "status": status, **extra}
    if ref is not None:
        row["external_ref"] = ref
    return row


COMPLETED = (issue("ab-1"),)


def store(repository, directory, usable=True, **extra):
    return {
        "repository": repository, "repository_path": ".", "directory": str(directory),
        "usable": usable, "error": None if usable else "missing .beads", **extra,
    }


def transition(identifier, target, **extra):
    return {"id": identifier, "name": f"Move to {target}", "to": {"name": target}, "hasScreen": False, **extra}


def jira(status="In Progress", transitions=None, **extra):
    if transitions is None:
        transitions = [transition("31", "In Review"), transition("41", "Done")]
    return {
        "issue": {"key": "AB-1", "fields": {"status": {"name": status}}},
        "transitions": {"transitions": transitions},
        **extra,
    }


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        helper = self.base / "skills" / "complete-task" / "scripts" / HELPER.name
        helper.parent.mkdir(parents=True)
        shutil.copy(HELPER, helper)
        self.helper = helper
        resolver = self.base / "skills" / "next" / "scripts" / "next-select"
        resolver.parent.mkdir(parents=True)
        resolver.write_text(FAKE_NEXT_SELECT)
        resolver.chmod(0o755)
        binaries = self.base / "bin"
        binaries.mkdir()
        (binaries / "bd").write_text(FAKE_BD)
        (binaries / "bd").chmod(0o755)
        self.log = self.base / "bd.jsonl"
        self.environment = {
            "PATH": f"{binaries}:{os.environ['PATH']}", "HOME": str(self.base),
            "BD_LOG": str(self.log), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def repository(self, path, issues=(), faults=()):
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=path, check=True, env=self.environment)
        (path / ".beads").mkdir()
        self.issues(path, *issues, faults=faults)
        return path

    def issues(self, path, *rows, faults=()):
        (path / ".beads" / "fixture.json").write_text(json.dumps({"issues": list(rows), "faults": list(faults)}))

    def local_stores(self, path, usable=True):
        (path / ".fake-stores.json").write_text(json.dumps({"workspace": False, "stores": [store("local", path, usable)]}))

    def policy(self, path, text=POLICY):
        (path / ".agents").mkdir(exist_ok=True)
        (path / ".agents" / "jira-review.toml").write_text(text)

    def standalone(self, issues=COMPLETED, policy=POLICY):
        repo = self.repository(self.base / "code" / "repo", issues)
        self.local_stores(repo)
        if policy is not None:
            self.policy(repo, policy)
        return repo

    def workspace(self, root_issues=(), member_issues=COMPLETED):
        root = self.repository(self.base / "code" / "ws", root_issues)
        (root / "workspace.json").write_text("{}")
        member = self.repository(self.base / "code" / "member", member_issues)
        (root / "repos").mkdir()
        (root / "repos" / "member").symlink_to(member, target_is_directory=True)
        stores = [
            store("workspace", root), store("member", member),
            store("shared", root, owner="workspace", repository_directory=str(self.base / "code" / "shared")),
        ]
        (root / ".fake-stores.json").write_text(json.dumps({"workspace": True, "stores": stores}))
        return root, member

    def run_helper(self, cwd, *extra, command="plan", bead="ab-1", store_dir=None,
                   milestone="trunk-commit", stdin=None):
        arguments = [str(self.helper), command, "--bead", bead, "--store", str(store_dir or cwd),
                     "--milestone", milestone, *extra]
        if stdin is not None and not isinstance(stdin, str):
            stdin = json.dumps(stdin)
        result = subprocess.run(arguments, cwd=cwd, env={**self.environment, "PWD": str(cwd)},
                                input=stdin if stdin is not None else "", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class PlanTests(Fixture):
    def test_no_policy_is_silently_disabled(self):
        repo = self.standalone(policy=None)
        result = self.run_helper(repo)
        self.assertEqual((result["status"], result["reason"]), ("disabled", "no-policy"))
        self.assertEqual(self.calls(), [])

    def test_invalid_policy_is_reported_not_guessed(self):
        repo = self.standalone()
        cases = {
            "unknown key": POLICY + "done_status = 'Done'\n",
            "target is a source": POLICY.replace('["In Progress"]', '["In Progress", "in review"]'),
            "unknown milestone": POLICY.replace('"pr-created"', '"merged"'),
            "empty sources": POLICY.replace('["In Progress"]', "[]"),
            "not toml": "milestones = [",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.policy(repo, text)
                result = self.run_helper(repo)
                self.assertEqual((result["status"], result["reason"]), ("skip", "policy-invalid"))

    def test_milestone_draft_and_stacked_gates(self):
        repo = self.standalone(policy=POLICY.replace('"trunk-commit", ', ""))
        self.assertEqual(self.run_helper(repo)["reason"], "milestone-not-enabled")
        self.assertEqual(self.run_helper(repo)["status"], "disabled")
        draft = self.run_helper(repo, "--draft", milestone="pr-created")
        stacked = self.run_helper(repo, "--stacked", milestone="pr-created")
        self.assertEqual((draft["status"], draft["reason"]), ("skip", "draft-pr"))
        self.assertEqual((stacked["status"], stacked["reason"]), ("skip", "stacked-pr"))
        self.assertEqual(self.calls(), [])

    def test_single_associated_bead_is_ready(self):
        repo = self.standalone()
        result = self.run_helper(repo)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["key"], "AB-1")
        self.assertEqual(result["completing"], "local:ab-1")
        self.assertEqual(result["associated"], [{"selector": "local:ab-1", "status": "closed"}])
        self.assertEqual(result["policy"]["target_status"], "In Review")
        self.assertEqual(result["scope"]["kind"], "repository")
        self.assertEqual(result["delivery"]["published"], "unknown")
        self.assertRegex(result["fingerprint"], r"^[0-9a-f]{64}$")

    def test_last_of_several_associated_beads_is_ready(self):
        repo = self.standalone(issues=(issue("ab-1"), issue("ab-2"), issue("ab-3", "open", ref="jira-AB-9")))
        result = self.run_helper(repo)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(len(result["associated"]), 2)

    def test_any_unfinished_associated_status_blocks(self):
        repo = self.standalone()
        for status in ("open", "in_progress", "blocked", "deferred", "pinned"):
            with self.subTest(status):
                self.issues(repo, issue("ab-1"), issue("ab-2", status))
                result = self.run_helper(repo)
                self.assertEqual((result["status"], result["reason"]), ("skip", "remaining-work"))
                self.assertEqual(result["remaining"], ["local:ab-2"])

    def test_deferred_verification_follow_up_blocks_review(self):
        follow_up = issue(
            "ab-check", "deferred", defer_until="2030-02-01T10:00:00Z",
            dependencies=[{"depends_on_id": "ab-1", "type": "discovered-from"}],
        )
        repo = self.standalone(issues=(issue("ab-1"), follow_up))
        result = self.run_helper(repo)
        self.assertEqual((result["status"], result["reason"]), ("skip", "remaining-work"))
        self.assertEqual(result["remaining"], ["local:ab-check"])

    def test_only_an_exact_external_ref_associates(self):
        repo = self.standalone()
        self.issues(repo, issue("ab-1"), issue("ab-2", "open", ref=None, title="Mentions AB-1"))
        self.assertEqual(self.run_helper(repo)["status"], "ready")
        for name, ref in {"title mention": None, "other tracker": "trello-abc", "malformed key": "jira-ab-1"}.items():
            with self.subTest(name):
                self.issues(repo, issue("ab-1", ref=ref, title="Implements AB-1"))
                result = self.run_helper(repo)
                self.assertEqual((result["status"], result["reason"]), ("skip", "no-association"))
        self.issues(repo, issue("ab-1"))
        mismatch = self.run_helper(repo, "--expected-key", "AB-2", milestone="pr-created")
        self.assertEqual(mismatch["reason"], "association-mismatch")

    def test_completing_bead_must_already_be_closed(self):
        repo = self.standalone(issues=(issue("ab-1", "in_progress"),))
        result = self.run_helper(repo)
        self.assertEqual((result["status"], result["reason"]), ("skip", "not-completed"))

    def test_unavailable_or_untrusted_inventory_skips(self):
        repo = self.standalone()
        for fault in ("list-error", "list-malformed", "drop-ref"):
            with self.subTest(fault):
                self.issues(repo, issue("ab-1"), faults=[fault])
                self.assertEqual(self.run_helper(repo)["reason"], "coverage-unavailable")
        self.issues(repo, issue("ab-1"), faults=["show-error"])
        self.assertEqual(self.run_helper(repo)["reason"], "bead-unavailable")
        self.issues(repo, issue("ab-1"))
        self.local_stores(repo, usable=False)
        self.assertEqual(self.run_helper(repo)["reason"], "coverage-unavailable")

    def test_completing_store_must_belong_to_scope(self):
        repo = self.standalone()
        elsewhere = self.repository(self.base / "elsewhere", [issue("ab-1")])
        result = self.run_helper(repo, store_dir=elsewhere)
        self.assertEqual((result["status"], result["reason"]), ("skip", "store-out-of-scope"))

    def test_workspace_scope_reads_every_unique_store_once(self):
        root, member = self.workspace(root_issues=[issue("ws-9", "open")])
        self.policy(root)
        logical = root / "repos" / "member"
        result = self.run_helper(logical, store_dir=member)
        self.assertEqual((result["status"], result["reason"]), ("skip", "remaining-work"))
        self.assertEqual(result["remaining"], ["workspace:ws-9"])
        listed = Counter(call["directory"] for call in self.calls() if call["args"][0] == "list")
        self.assertEqual(listed, Counter({str(root): 1, str(member): 1}))
        self.issues(root, issue("ws-9"))
        ready = self.run_helper(logical, store_dir=member)
        self.assertEqual((ready["status"], ready["scope"]["kind"], ready["completing"]), ("ready", "workspace", "member:ab-1"))

    def test_repository_policy_overrides_workspace_policy(self):
        root, member = self.workspace()
        self.policy(root, POLICY.replace('"trunk-commit", ', ""))
        logical = root / "repos" / "member"
        self.assertEqual(self.run_helper(logical, store_dir=member)["reason"], "milestone-not-enabled")
        self.policy(member)
        result = self.run_helper(logical, store_dir=member)
        self.assertEqual((result["status"], result["scope"]["kind"]), ("ready", "workspace"))
        self.assertTrue(result["policy"]["path"].endswith("repos/member/.agents/jira-review.toml"), result)

    def test_unvalidated_workspace_fails_closed(self):
        root, member = self.workspace()
        self.policy(root)
        (root / ".fake-stores.json").write_text(json.dumps({"workspace": False, "stores": [store("local", root)]}))
        result = self.run_helper(root / "repos" / "member", store_dir=member)
        self.assertEqual((result["status"], result["reason"]), ("skip", "scope-unavailable"))


class DecideTests(Fixture):
    def setUp(self):
        super().setUp()
        self.repo = self.standalone()

    def decide(self, evidence, *extra):
        return self.run_helper(self.repo, *extra, command="decide", stdin=evidence)

    def test_eligible_status_proposes_one_exact_transition(self):
        plan = self.run_helper(self.repo)
        result = self.decide(jira())
        self.assertEqual(result["status"], "propose", result)
        self.assertEqual(result["proposal"], {
            "key": "AB-1", "transitionId": "31", "transitionName": "Move to In Review",
            "from": "In Progress", "to": "In Review", "fingerprint": plan["fingerprint"],
        })

    def test_source_status_gate_and_already_in_target(self):
        self.assertEqual(self.decide(jira("To Do"))["reason"], "ineligible-status")
        result = self.decide(jira("in review"))
        self.assertEqual((result["status"], result["reason"]), ("noop", "already-in-target"))

    def test_transition_resolution_fails_closed(self):
        reviewer = {"customfield_1": {"required": True, "name": "Reviewer"}}
        cases = {
            "no transition": ([transition("41", "Done")], "no-transition"),
            "unavailable": ([transition("31", "In Review", isAvailable=False)], "no-transition"),
            "ambiguous": ([transition("31", "In Review"), transition("32", "In Review")], "ambiguous-transition"),
            "required field": ([transition("31", "In Review", fields=reviewer)], "required-fields"),
            "unknown screen": ([transition("31", "In Review", hasScreen=True)], "screen-fields-unknown"),
            "malformed": ([{"id": "31"}], "jira-unavailable"),
        }
        for name, (transitions, reason) in cases.items():
            with self.subTest(name):
                result = self.decide(jira(transitions=transitions))
                self.assertEqual((result["status"], result["reason"]), ("skip", reason), result)
        defaulted = {"resolution": {"required": True, "hasDefaultValue": True, "name": "Resolution"}}
        self.assertEqual(self.decide(jira(transitions=[transition("31", "In Review", fields=defaulted)]))["status"], "propose")
        self.assertEqual(self.decide({"issue": {}, "transitions": []})["reason"], "jira-unavailable")
        self.assertEqual(self.decide("{")["reason"], "jira-unavailable")

    def test_approval_is_bound_to_the_unchanged_proposal(self):
        first = self.decide(jira())["proposal"]
        self.assertEqual(self.decide(jira(previous=first))["status"], "propose")
        changed = self.decide(jira(transitions=[transition("35", "In Review")], previous=first))
        self.assertEqual((changed["status"], changed["reason"]), ("changed", "evidence-changed"))
        self.issues(self.repo, issue("ab-1"), issue("ab-2", "open"))
        self.assertEqual(self.decide(jira(previous=first))["reason"], "remaining-work")
        self.issues(self.repo, issue("ab-1"))
        moved = self.decide(jira("In Review", previous=first))
        self.assertEqual((moved["status"], moved["reason"]), ("noop", "already-in-target"))


class ContractTests(unittest.TestCase):
    @staticmethod
    def text(name):
        return (SKILLS / name / "SKILL.md").read_text()

    def assertOrder(self, text, *terms):
        positions = [text.index(term) for term in terms]
        self.assertEqual(positions, sorted(positions), terms)

    def test_both_completion_callers_share_one_procedure(self):
        grant = "Bash(~/.agents/skills/complete-task/scripts/jira-review.py:*)"
        complete, create = self.text("complete-task"), self.text("create-pr")
        for text in (complete, create):
            self.assertIn(grant, text.split("---", 2)[1])
            self.assertNotIn("jira_transition_issue", text)
        self.assertIn("(references/jira-review.md)", complete)
        self.assertIn("(../complete-task/references/jira-review.md)", create)
        self.assertNotIn("mcp__jira__", create)
        self.assertOrder(complete, "bd -C <directory> close <bead-id>", "--milestone trunk-commit")
        self.assertIn("**Close the bead anyway**", complete.split("### 6a.", 1)[1])
        jira_offer = " ".join(complete.split("### 6a.", 1)[1].split("### 7.", 1)[0].split())
        for term in ("Deferred-verification", "skip", "never claim verification", "no Jira comment"):
            self.assertIn(term, jira_offer)
        self.assertOrder(complete, "#### A. Close implementation", "#### B. Snooze", "### 6a.")
        for term in ("--milestone pr-created", "--expected-key", "--draft", "--stacked"):
            self.assertIn(term, create)
        self.assertOrder(create, "Confirm PR creation", "bd -C <directory> close <bead-id>", "--milestone pr-created")

    def test_verification_stays_read_only(self):
        metadata = self.text("verify-task").split("---", 2)[1]
        for term in ("jira-review", "jira_transition_issue", "jira_post"):
            self.assertNotIn(term, metadata)

    def test_reference_requires_one_fresh_approved_transition(self):
        text = " ".join(REFERENCE.read_text().split())
        for term in (
            "`jira-<KEY>`", "Python 3.11+", "stops below `$HOME`", "Nearest wins",
            "Move to review", "Skip", '"previous"', "Approval does not carry",
            "No fields, no retry", "transitioned", "failed", "uncertain",
            "never reopens the bead", "superseded", "already-closed", "../../jira-ticket/SKILL.md",
            "does not prove", "workspace path",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_suite_runs_with_lifecycle_checks(self):
        makefile = (ROOT / "Makefile").read_text()
        target = re.search(r"^test-git-pr-lifecycle:\n((?:\t.*\n)+)", makefile, re.M).group(1)
        self.assertIn("-s skills/complete-task/tests", target)


if __name__ == "__main__":
    unittest.main()
