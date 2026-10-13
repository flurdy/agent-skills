"""Offline gh-pr-details projection and pr-status rendering contracts; no GitHub access.

A fake `gh` records its arguments and applies the script's own `--jq` projection to a
fixture response with the real `jq`, so the projection is exercised exactly as written.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parents[1]
DETAILS = SKILL / "scripts" / "gh-pr-details.sh"
JQ = shutil.which("jq")

FAKE_GH = """#!/bin/bash
printf '%s\\0' "$@" >"$GH_TEST_LOG"
expression=""
while (($#)); do
  if [[ $1 == --jq ]]; then expression=$2; shift; fi
  shift
done
printf '%s' "$GH_TEST_RESPONSE" | "$GH_TEST_JQ" -c "$expression"
"""


def pull_request(number, **overrides):
    fields = {
        "number": number,
        "headRefName": f"feat/AB-{number}-change",
        "baseRefName": "main",
        "isDraft": False,
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "REVIEW_REQUIRED",
        "reviews": {"nodes": []},
        "reviewRequests": {"totalCount": 0},
        "reviewThreads": {"nodes": []},
        "createdAt": "2026-10-01T09:00:00Z",
        "commits": {"nodes": [{"commit": {
            "committedDate": "2026-10-01T10:00:00Z",
            "statusCheckRollup": {"state": "SUCCESS"},
        }}]},
        "mergeCommit": None,
        "timelineItems": {"nodes": []},
    }
    fields.update(overrides)
    return fields


@unittest.skipIf(JQ is None, "jq is required to apply the collector projection")
class DetailsCollectorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pr details ")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        self.log = self.work / "gh-args"
        self.env = {
            "PATH": f"{bin_dir}:{os.defpath}",
            "HOME": str(self.work),
            "GH_TEST_LOG": str(self.log),
            "GH_TEST_JQ": JQ,
        }

    def collect(self, *pulls):
        response = {"data": {"repository": {f"pr{p['number']}": p for p in pulls}}}
        result = subprocess.run(
            [str(DETAILS), "acme", "widgets", *(str(p["number"]) for p in pulls)],
            cwd=self.work, env=self.env | {"GH_TEST_RESPONSE": json.dumps(response)},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return {row["number"]: row for row in json.loads(result.stdout)}

    def query(self):
        arguments = [value.decode() for value in self.log.read_bytes().split(b"\0")[:-1]]
        return next(value for value in arguments if value.startswith("query="))

    def test_query_reads_exact_connection_total_not_a_capped_page(self):
        self.collect(pull_request(1))
        query = self.query()
        self.assertRegex(query, r"reviewRequests\s*\{\s*totalCount\s*\}")
        self.assertNotRegex(query, r"reviewRequests\s*\(")

    def test_zero_one_many_and_beyond_one_page_are_exact(self):
        counts = {1: 0, 2: 1, 3: 3, 4: 250}
        rows = self.collect(*(
            pull_request(number, reviewRequests={"totalCount": count})
            for number, count in counts.items()
        ))
        for number, count in counts.items():
            with self.subTest(count=count):
                self.assertIs(type(rows[number]["reviewRequestCount"]), int)
                self.assertEqual(rows[number]["reviewRequestCount"], count)

    def test_user_and_team_requests_each_count_once(self):
        requests = {"totalCount": 2, "nodes": [
            {"requestedReviewer": {"__typename": "User", "login": "alice"}},
            {"requestedReviewer": {"__typename": "Team", "slug": "platform"}},
        ]}
        rows = self.collect(pull_request(7, reviewRequests=requests))
        self.assertEqual(rows[7]["reviewRequestCount"], 2)

    def test_unknown_count_stays_null_never_zero(self):
        missing = pull_request(9)
        del missing["reviewRequests"]
        rows = self.collect(pull_request(8, reviewRequests=None), missing)
        for number in (8, 9):
            with self.subTest(number=number):
                self.assertIn("reviewRequestCount", rows[number])
                self.assertIsNone(rows[number]["reviewRequestCount"])

    def test_approvals_drafts_and_existing_fields_are_unchanged(self):
        approved_draft = pull_request(
            11, isDraft=True, reviewDecision="APPROVED",
            reviews={"nodes": [{"author": {"login": "bob"}}, {"author": {"login": "alice"}},
                               {"author": {"login": "bob"}}]},
            reviewRequests={"totalCount": 1},
        )
        changes = pull_request(12, reviewDecision="CHANGES_REQUESTED",
                               reviewThreads={"nodes": [{"isResolved": False}]})
        rows = self.collect(approved_draft, changes)
        self.assertEqual(
            {key: rows[11][key] for key in
             ("isDraft", "reviewDecision", "approvers", "reviewRequestCount", "checksState")},
            {"isDraft": True, "reviewDecision": "APPROVED", "approvers": ["alice", "bob"],
             "reviewRequestCount": 1, "checksState": "SUCCESS"},
        )
        self.assertEqual(rows[12]["reviewDecision"], "CHANGES_REQUESTED")
        self.assertEqual(rows[12]["unresolvedThreads"], 1)
        self.assertEqual(rows[12]["reviewRequestCount"], 0)


class RenderingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (SKILL / "SKILL.md").read_text()
        cls.flat = " ".join(cls.text.split())

    def assert_phrases(self, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in self.flat, f"missing: {phrase}")

    def approved_cells(self):
        section = self.text.split("Approved cell", 1)[1]
        rows = {}
        for line in section.splitlines()[1:]:
            if line.startswith("| ") and not line.startswith("| Evidence"):
                evidence, cell = (part.strip() for part in line.strip("|").split("|"))
                rows[evidence] = cell
            elif rows and not line.startswith("|"):
                break
        return rows

    def test_collector_contract_documents_exact_and_unknown_counts(self):
        example = self.text.split("```json", 1)[1].split("```", 1)[0]
        self.assertIn('"reviewRequestCount": 0', example)
        self.assert_phrases(
            "each requested user or team counts once",
            "`null` means unknown",
            "never treat it as zero",
            "submitted reviews, approvals or withdrawn requests",
        )

    def test_fallback_never_invents_an_exact_count(self):
        self.assert_phrases(
            "treat `reviewRequestCount` as unknown",
            "Do not derive it from the length of a capped",
            "inbound review-request queue",
        )

    def test_approved_cell_states(self):
        cells = self.approved_cells()
        self.assertEqual(cells, {
            "`reviewDecision` `APPROVED`": "one ✅ per approver",
            "`REVIEW_REQUIRED` with approvers": "one ☑️ per approver (stale approvals)",
            "`CHANGES_REQUESTED`": "👎",
            "Draft with no approvers": "`—`",
            "Awaiting review, `reviewRequestCount` 0": "⚠️ 0",
            "Awaiting review, `reviewRequestCount` N > 0": "🔔 N (e.g. 🔔 2)",
            "Awaiting review, `reviewRequestCount` null or missing": "🔔",
        })
        self.assert_phrases("never a bell per reviewer", "no question mark")
        self.assertNotRegex(self.text, r"🔔\s*\?")

    def test_reviewer_suggestion_requires_known_zero(self):
        self.assertIn(
            "| → ⚠️ 0 awaiting review with no requests | "
            "`gh pr edit {n} --repo {owner}/{repo} --add-reviewer <handle>` |",
            self.text,
        )
        self.assert_phrases(
            "only for a known zero",
            "suggest nothing for either",
            "on the first check of a session list the currently-actionable PRs as baseline",
            "Read-only: point at commands, never run them",
        )

    def test_suite_is_wired_into_the_full_gate(self):
        makefile = (ROOT / "Makefile").read_text()
        targets = makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0]
        self.assertIn("test-pr-status", targets)
        self.assertIn("-p 'test_pr_details.py'", makefile)


if __name__ == "__main__":
    unittest.main()
