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
call=$(ls "$GH_TEST_LOG" | wc -l)
printf '%s\\0' "$@" >"$GH_TEST_LOG/$((call))"
response=$GH_TEST_RESPONSE
status=0
for argument in "$@"; do
  if [[ $argument == query=*'compare(headRef'* ]]; then
    response=${GH_TEST_COMPARE_RESPONSE:-}
    status=${GH_TEST_COMPARE_EXIT:-0}
  fi
done
expression=""
while (($#)); do
  if [[ $1 == --jq ]]; then expression=$2; shift; fi
  shift
done
if [[ -n $expression ]]; then
  printf '%s' "$response" | "$GH_TEST_JQ" -c "$expression"
else
  printf '%s' "$response"
fi
exit "$status"
"""


def pull_request(number, **overrides):
    fields = {
        "number": number,
        "state": "OPEN",
        "headRefName": f"feat/AB-{number}-change",
        "baseRefName": "main",
        "isCrossRepository": False,
        "isDraft": False,
        "mergeable": "MERGEABLE",
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
        (bin_dir / "jq").symlink_to(JQ)
        self.log = self.work / "gh-calls"
        self.log.mkdir()
        self.env = {
            "PATH": f"{bin_dir}:{os.defpath}",
            "HOME": str(self.work),
            "GH_TEST_LOG": str(self.log),
            "GH_TEST_JQ": JQ,
        }

    def collect(self, *pulls, behind=None, compare_response=None, compare_exit=0):
        response = {"data": {"repository": {f"pr{p['number']}": p for p in pulls}}}
        if compare_response is None:
            compare_response = {"data": {"repository": {
                f"pr{number}": {"compare": {"behindBy": count}}
                for number, count in (behind or {}).items()
            }}}
        if not isinstance(compare_response, str):
            compare_response = json.dumps(compare_response)
        result = subprocess.run(
            [str(DETAILS), "acme", "widgets", *(str(p["number"]) for p in pulls)],
            cwd=self.work, env=self.env | {
                "GH_TEST_RESPONSE": json.dumps(response),
                "GH_TEST_COMPARE_RESPONSE": compare_response,
                "GH_TEST_COMPARE_EXIT": str(compare_exit),
            },
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.stderr = result.stderr
        return {row["number"]: row for row in json.loads(result.stdout)}

    def calls(self):
        paths = sorted(self.log.iterdir(), key=lambda path: int(path.name))
        return [[value.decode() for value in path.read_bytes().split(b"\0")[:-1]] for path in paths]

    def query(self, call=0):
        return next(value for value in self.calls()[call] if value.startswith("query="))

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

    def test_blocked_pr_still_reports_mergeability_and_behind_count(self):
        rows = self.collect(
            pull_request(21, mergeStateStatus="BLOCKED"),
            pull_request(22, mergeStateStatus="BLOCKED", mergeable="CONFLICTING"),
            pull_request(23),
            behind={21: 6, 22: 1, 23: 0},
        )
        self.assertEqual(
            {key: rows[21][key] for key in ("mergeState", "mergeable", "behindBy")},
            {"mergeState": "BLOCKED", "mergeable": "MERGEABLE", "behindBy": 6},
        )
        self.assertEqual(rows[22]["mergeable"], "CONFLICTING")
        self.assertIs(type(rows[23]["behindBy"]), int)
        self.assertEqual(rows[23]["behindBy"], 0)
        self.assertNotIn("compare", rows[21])

    def test_compare_uses_each_actual_base_through_variables(self):
        stacked = pull_request(31, baseRefName="feat/AB-30-parent", headRefName='feat/AB-31-"child"')
        rows = self.collect(pull_request(30), stacked, behind={30: 0, 31: 2})
        self.assertEqual(rows[31]["behindBy"], 2)
        compare = self.calls()[1]
        query = self.query(1)
        for alias in (30, 31):
            with self.subTest(alias=alias):
                self.assertIn(f"pr{alias}: ref(qualifiedName: $base{alias})", query)
                self.assertIn(f"compare(headRef: $head{alias})", query)
        self.assertNotIn("AB-3", query)
        self.assertIn("base30=refs/heads/main", compare)
        self.assertIn("base31=refs/heads/feat/AB-30-parent", compare)
        self.assertIn('head31=feat/AB-31-"child"', compare)

    def test_closed_and_fork_prs_are_never_compared(self):
        rows = self.collect(pull_request(41, state="MERGED"), pull_request(42, isCrossRepository=True),
                            pull_request(43), behind={41: 5, 42: 5, 43: 1})
        query = self.query(1)
        self.assertIn("pr43:", query)
        self.assertNotIn("pr41:", query)
        self.assertNotIn("pr42:", query)
        self.assertEqual((rows[41]["behindBy"], rows[42]["behindBy"], rows[43]["behindBy"]), (None, None, 1))

    def test_no_comparable_pr_makes_no_compare_call(self):
        rows = self.collect(pull_request(44, state="CLOSED"), pull_request(45, isCrossRepository=True))
        self.assertEqual(len(self.calls()), 1)
        self.assertIsNone(rows[44]["behindBy"])
        self.assertIsNone(rows[45]["behindBy"])

    def test_failed_compare_keeps_details_with_unknown_counts(self):
        for response, status in (("", 1), ("not json", 0), ('{"data": null}', 0), ('{"data": []}', 0)):
            with self.subTest(response=response):
                rows = self.collect(pull_request(51, mergeStateStatus="BLOCKED"),
                                    compare_response=response, compare_exit=status)
                self.assertIsNone(rows[51]["behindBy"])
                self.assertEqual(rows[51]["mergeState"], "BLOCKED")
        self.collect(pull_request(52), compare_response="", compare_exit=1)
        self.assertIn("behind counts", self.stderr)

    def test_partial_compare_errors_keep_resolved_counts(self):
        partial = {"data": {"repository": {"pr61": {"compare": {"behindBy": 3}}, "pr62": None}},
                   "errors": [{"message": "Could not resolve to a Ref"}]}
        rows = self.collect(pull_request(61), pull_request(62), compare_response=partial, compare_exit=1)
        self.assertEqual(rows[61]["behindBy"], 3)
        self.assertIsNone(rows[62]["behindBy"])


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

    def bullet(self, name):
        return next(line for line in self.text.splitlines() if line.startswith(f"- **{name}**"))

    def test_collector_documents_independent_sync_fields(self):
        example = self.text.split("```json", 1)[1].split("```", 1)[0]
        self.assertIn('"mergeable": "MERGEABLE"', example)
        self.assertIn('"behindBy": 0', example)
        self.assert_phrases(
            "actual base branch",
            "second batched compare query",
            "cross-repository (fork) PRs",
            "unknown, never zero",
        )

    def test_sync_reads_mergeability_and_actual_base_not_merge_state(self):
        sync = self.bullet("Sync")
        for phrase in ("actual base", "regardless of `mergeState`", "`mergeable` `CONFLICTING`",
                       "💥 conflict", "`behindBy` > 0 → ⚠️ N behind", "`behindBy` 0 → ✅",
                       "→ `?`", "never `—`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, sync)
        self.assertNotIn("Stacked PRs (📌) → `—`", sync)

    def test_lgtm_keeps_requiring_clean_on_a_default_base(self):
        lgtm = self.bullet("LGTM")
        self.assertIn("`mergeState` `CLEAN`", lgtm)
        self.assertIn("`main`/`master`", lgtm)

    def test_behind_suggestion_fires_before_approval_against_actual_base(self):
        self.assertIn(
            "| → ⚠️ behind (fell behind its base) | "
            "`/rebase main` (on that PR's branch); stacked: `/rebase parent {base}` |",
            self.text,
        )
        self.assert_phrases("regardless of review or approval state", "a growing count is not a new transition")

    def test_suite_is_wired_into_the_full_gate(self):
        makefile = (ROOT / "Makefile").read_text()
        targets = makefile.split("TEST_TARGETS :=", 1)[1].split("test:", 1)[0]
        self.assertIn("test-pr-status", targets)
        self.assertIn("-p 'test_pr_details.py'", makefile)


if __name__ == "__main__":
    unittest.main()
