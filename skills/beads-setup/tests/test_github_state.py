"""Exercise the real read-only GitHub gate with mocked CLI transport, never a live API."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/github_state.py"


def response(status, body, code=None):
    return subprocess.CompletedProcess([], (0 if status == 200 else 1) if code is None else code,
                                       f"HTTP/2.0 {status} Status\ncontent-type: application/json\n\n" + json.dumps(body),
                                       "private diagnostic must not escape")


def repository(**changes):
    result = {"id": 123, "name": "demo-beads", "full_name": "owner/demo-beads", "owner": {"login": "owner"},
              "private": True, "default_branch": "seed", "fork": False, "archived": False, "disabled": False}
    result.update(changes)
    return result


class GithubStateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "missing production read-only GitHub gate")
        spec = importlib.util.spec_from_file_location("github_state", SCRIPT)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def inspect(self, responses, **kwargs):
        with patch.object(self.helper.subprocess, "run", side_effect=responses) as run:
            result = self.helper.inspect("owner/demo-beads", **kwargs)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[:7], ["gh", "api", "--hostname", "github.com", "--method", "GET", "--include"])
            self.assertNotIn("shell", call.kwargs)
        self.assertNotIn("private diagnostic", json.dumps(result))
        return result, run

    def user(self):
        return response(200, {"login": "owner"})

    def test_personal_404_is_advisory_not_proof_of_absence(self):
        result, _ = self.inspect([self.user(), response(404, {"message": "Not Found"})])
        self.assertEqual(result["state"], "not-visible")
        self.assertFalse(result["absenceProven"])
        self.assertEqual(result["repository"], "owner/demo-beads")

    def test_existing_repository_is_never_adopted_in_new_mode(self):
        for private in (True, False):
            with self.subTest(private=private):
                result, run = self.inspect([self.user(), response(200, repository(private=private))])
                self.assertEqual(result["state"], "exists")
                self.assertEqual(run.call_count, 2)

    def test_postcreate_verifies_id_privacy_and_branch_independently(self):
        result, run = self.inspect([self.user(), response(200, repository()),
                                   response(200, {"name": "seed", "commit": {"sha": "a" * 40}})], after_create=True)
        self.assertEqual(result["state"], "created")
        self.assertEqual(result["id"], 123)
        self.assertEqual(result["defaultBranch"], "seed")
        self.assertEqual(result["gitHead"], "a" * 40)
        self.assertEqual(run.call_args.args[0][-1], "repos/owner/demo-beads/branches/seed")

    def test_recorded_repo_identity_is_revalidated(self):
        result, run = self.inspect([self.user(), response(200, repository(id=124))], after_create=True, expected_id=123)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["reason"], "repository-identity-changed")
        self.assertEqual(run.call_count, 2)

    def test_partial_creation_stops_without_repair_or_delete(self):
        cases = [repository(private=False), repository(default_branch=None), repository(fork=True),
                 repository(archived=True), repository(disabled=True)]
        for data in cases:
            with self.subTest(data=data):
                result, run = self.inspect([self.user(), response(200, data)], after_create=True)
                self.assertEqual(result["state"], "blocked")
                self.assertEqual(result["id"], 123)
                self.assertEqual(run.call_count, 2)

    def test_disappeared_or_unreadable_branch_is_not_success(self):
        for branch in (response(404, {"message": "Not Found"}), response(200, {"name": "seed"}),
                       response(200, {"name": "different", "commit": {"sha": "b" * 40}})):
            with self.subTest(branch=branch):
                result, _ = self.inspect([self.user(), response(200, repository()), branch], after_create=True)
                self.assertEqual(result["state"], "blocked")
                self.assertEqual(result["id"], 123)

    def test_postcreate_404_is_retained_uncertain_state(self):
        result, _ = self.inspect([self.user(), response(404, {"message": "Not Found"})], after_create=True)
        self.assertEqual(result["state"], "blocked")

    def test_auth_permissions_transport_and_malformed_data_fail_closed(self):
        cases = [response(401, {}), response(403, {}), response(500, {}), response(200, {}, code=1),
                 response(200, []), response(200, {}),
                 subprocess.CompletedProcess([], 0, "HTTP/2.0 200 OK\n\n{broken", "secret"),
                 subprocess.TimeoutExpired("gh", 20), FileNotFoundError("sensitive local path")]
        for data in cases:
            with self.subTest(data=type(data).__name__):
                result, run = self.inspect([data])
                self.assertEqual(result["state"], "blocked")
                self.assertEqual(run.call_count, 1)
                self.assertNotIn("secret", json.dumps(result))
                self.assertNotIn("sensitive", json.dumps(result))

    def test_repo_errors_and_identity_mismatch_do_not_become_absence(self):
        for data in (response(403, {}), response(200, repository(full_name="someone/else")),
                     response(200, {"id": 123}), response(200, repository(id=True))):
            with self.subTest(data=data):
                result, _ = self.inspect([self.user(), data])
                self.assertEqual(result["state"], "blocked")

    def test_org_requires_active_admin_membership(self):
        member = {"state": "active", "role": "admin", "organization": {"login": "owner"}}
        result, run = self.inspect([response(200, {"login": "operator"}), response(200, member), response(404, {})])
        self.assertEqual(result["state"], "not-visible")
        self.assertEqual(run.call_args_list[1].args[0][-1], "user/memberships/orgs/owner")
        for changes in ({"role": "member"}, {"state": "pending"}, {"organization": {"login": "different"}}):
            with self.subTest(changes=changes):
                result, run = self.inspect([response(200, {"login": "operator"}), response(200, member | changes)])
                self.assertEqual(result["state"], "blocked")
                self.assertEqual(run.call_count, 2)

    def test_cli_json_and_exit_status_gate(self):
        cases = [
            ([], [self.user(), response(404, {})], "not-visible", 0),
            ([], [self.user(), response(200, repository())], "exists", 2),
            ([], [response(403, {})], "blocked", 2),
            (["--after-create", "--expected-id", "123"],
             [self.user(), response(200, repository()), response(200, {"name": "seed", "commit": {"sha": "a" * 40}})],
             "created", 0),
        ]
        for args, responses, state, code in cases:
            with self.subTest(state=state), patch("sys.argv", [str(SCRIPT), "owner/demo-beads", *args]), \
                    patch.object(self.helper.subprocess, "run", side_effect=responses):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(self.helper.main(), code)
                report = json.loads(output.getvalue())
                self.assertEqual(report["schemaVersion"], "beads-setup-github/v1")
                self.assertEqual(report["state"], state)

    def test_invalid_inputs_never_reach_cli(self):
        with patch.object(self.helper.subprocess, "run") as run:
            for name in ("owner/../escape", "--private", "owner/name;echo", "https://github.com/owner/name", "owner/.."):
                self.assertEqual(self.helper.inspect(name)["state"], "blocked")
            self.assertEqual(self.helper.inspect("owner/demo-beads", expected_id=123)["state"], "blocked")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
