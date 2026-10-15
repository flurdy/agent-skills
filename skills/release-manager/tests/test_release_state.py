import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
RELEASE_STATE = SKILL_DIR / "scripts" / "release-state"
SHA = "a" * 40
OTHER = "b" * 40


def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


class ReleaseStateTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name, "project").resolve()
        self.root.mkdir()
        run(["git", "init", "-q", "-b", "main"], self.root)
        (self.root / ".gitignore").write_text(".release-state.json\n", encoding="utf-8")
        self.state = self.root / ".release-state.json"
        self.env = {**os.environ, "XDG_RUNTIME_DIR": str(Path(self.temp_dir.name, "runtime"))}
        Path(self.env["XDG_RUNTIME_DIR"]).mkdir(mode=0o700)

    def tearDown(self):
        self.temp_dir.cleanup()

    def helper(self, *args, cwd=None):
        result = subprocess.run(
            [str(RELEASE_STATE), *args], cwd=cwd or self.root, env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
        return result.returncode, payload, result.stderr

    def read(self):
        code, payload, stderr = self.helper("read")
        self.assertEqual(code, 0, stderr)
        return payload

    def update(self, patch, expect=None, owner="manager"):
        expect = expect or self.read()["sha256"]
        return self.helper("update", "--owner", owner, "--expect", expect, "--patch", json.dumps(patch))

    def write_state(self, value):
        self.state.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_state_reads_empty_and_first_update_creates_private_file(self):
        payload = self.read()
        self.assertEqual(payload["schemaVersion"], "release-state/v1")
        self.assertEqual((payload["exists"], payload["sha256"], payload["state"]), (False, "missing", {}))
        self.assertEqual(payload["path"], str(self.state))
        code, result, stderr = self.update({"quietStreak": 1, "deferred": {"web": True}}, expect="missing")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["sha256"], hashlib.sha256(self.state.read_bytes()).hexdigest())
        self.assertEqual(json.loads(self.state.read_text()), {"deferred": {"web": True}, "quietStreak": 1})
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), [".git", ".gitignore", ".release-state.json"])

    def test_merge_patch_preserves_unknown_and_legacy_keys(self):
        self.write_state({"deferred": {"web": True, "api": True}, "configApply": {"x": 1}, "future": [1]})
        code, result, stderr = self.update({"deferred": {"web": None}, "rolloutWatch": {"api": {"sha": SHA, "fromTag": None}}})
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["state"], {
            "deferred": {"api": True}, "configApply": {"x": 1}, "future": [1],
            "rolloutWatch": {"api": {"sha": SHA, "fromTag": None}},
        })

    def test_stale_expectation_conflicts_without_writing(self):
        self.write_state({"quietStreak": 0})
        stale = self.read()["sha256"]
        self.assertEqual(self.update({"quietStreak": 1}, expect=stale)[0], 0)
        before = self.state.read_bytes()
        code, result, _ = self.update({"quietStreak": 9}, expect=stale)
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.update({"quietStreak": 2}, expect="missing")[0], 3)

    def test_owners_patch_only_their_keys_and_publishing_needs_its_commands(self):
        self.write_state({})
        for owner, key in (("manager", "configApply"), ("maintenance", "quietStreak"), ("manager", "publishing"), ("maintenance", "publishing")):
            code, _, stderr = self.update({key: {}}, owner=owner)
            self.assertEqual(code, 2, f"{owner} {key}")
            self.assertIn(key, stderr)
        self.assertEqual(self.update({"restartPending": None, "rolloutWatch": {"web": None}}, owner="maintenance")[0], 0)
        for bad in ("[]", "1", "{bad"):
            code, _, _ = self.helper("update", "--owner", "manager", "--expect", self.read()["sha256"], "--patch", bad)
            self.assertEqual(code, 2, bad)

    def test_unsafe_targets_and_malformed_state_are_refused(self):
        self.state.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.helper("read")[0], 2)
        digest = hashlib.sha256(self.state.read_bytes()).hexdigest()
        self.assertEqual(self.update({"quietStreak": 1}, expect=digest)[0], 2)
        self.assertEqual(self.state.read_text(), "{not json")
        for content in ("[]", json.dumps({"deferred": []}), json.dumps({"publishing": {"web": {"sha": "nope"}}})):
            self.state.write_text(content, encoding="utf-8")
            self.assertEqual(self.helper("read")[0], 2, content)
        self.state.unlink()
        elsewhere = Path(self.temp_dir.name, "elsewhere.json")
        elsewhere.write_text("{}", encoding="utf-8")
        self.state.symlink_to(elsewhere)
        self.assertEqual(self.helper("read")[0], 2)
        self.state.unlink()
        os.link(elsewhere, self.state)
        self.assertEqual(self.helper("read")[0], 2)
        self.state.unlink()
        self.state.mkdir()
        self.assertEqual(self.helper("read")[0], 2)
        self.state.rmdir()
        self.assertEqual(json.loads(elsewhere.read_text()), {})

    def test_unignored_or_tracked_state_is_never_created_or_written(self):
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        code, _, stderr = self.update({"quietStreak": 1}, expect="missing")
        self.assertEqual(code, 2)
        self.assertIn("gitignored", stderr)
        self.assertFalse(self.state.exists())
        (self.root / ".gitignore").write_text(".release-state.json\n", encoding="utf-8")
        self.write_state({})
        run(["git", "add", "-f", ".release-state.json"], self.root)
        self.assertEqual(self.update({"quietStreak": 1})[0], 2)

    def test_project_root_comes_from_git_not_the_subdirectory(self):
        nested = self.root / "service"
        nested.mkdir()
        code, payload, stderr = self.helper("read", cwd=nested)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["path"], str(self.state))
        outside = Path(self.temp_dir.name, "outside")
        outside.mkdir()
        self.assertEqual(self.helper("read", cwd=outside)[0], 2)

    def test_concurrent_writers_with_one_expectation_have_exactly_one_winner(self):
        self.write_state({"quietStreak": 0})
        expect = self.read()["sha256"]
        processes = [
            subprocess.Popen(
                [str(RELEASE_STATE), "update", "--owner", "manager", "--expect", expect, "--patch", json.dumps({"quietStreak": index + 1})],
                cwd=self.root, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for index in range(8)
        ]
        codes = [process.wait(timeout=30) for process in processes]
        for process in processes:
            process.stdout.close()
            process.stderr.close()
        self.assertEqual(sorted(codes), [0] + [3] * 7)
        self.assertIn(json.loads(self.state.read_text())["quietStreak"], range(1, 9))
        self.assertEqual([path.name for path in self.root.iterdir() if path.name.startswith(".release-state.json.")], [])

    def begin(self, service, sha=SHA, deploying=True, expect=None):
        return self.helper(
            "begin-publication", "--service", service, "--sha", sha, "--from-tag", "v1.2.3",
            "--session", "session-1", "--deploying" if deploying else "--no-deploying",
            "--expect", expect or self.read()["sha256"],
        )

    def test_write_ahead_publication_record_serializes_and_records_outcomes(self):
        self.write_state({"rolloutWatch": {}})
        code, result, stderr = self.begin("web")
        self.assertEqual(code, 0, stderr)
        record = result["state"]["publishing"]["web"]
        self.assertEqual({key: record[key] for key in ("sha", "fromTag", "session", "deploying")}, {"sha": SHA, "fromTag": "v1.2.3", "session": "session-1", "deploying": True})
        self.assertIn("startedAt", record)
        code, result, _ = self.begin("api", sha=OTHER)
        self.assertEqual(code, 4)
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["pending"], ["web"])
        self.assertEqual(self.helper("finish-publication", "--service", "web", "--sha", OTHER, "--status", "ok")[0], 2)
        code, result, stderr = self.helper("finish-publication", "--service", "web", "--sha", SHA, "--status", "ok")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["state"], {"rolloutWatch": {"web": {"sha": SHA, "fromTag": "v1.2.3"}}, "publishing": {}})
        self.assertEqual(self.begin("api", sha=OTHER, deploying=False)[0], 0)
        code, result, _ = self.helper("finish-publication", "--service", "api", "--sha", OTHER, "--status", "ok")
        self.assertNotIn("api", result["state"]["rolloutWatch"])
        for status in ("uptodate", "rejected", "failed", "stale", "declined"):
            self.assertEqual(self.begin("api", sha=OTHER)[0], 0)
            code, result, _ = self.helper("finish-publication", "--service", "api", "--sha", OTHER, "--status", status)
            self.assertEqual(code, 0, status)
            self.assertEqual(result["state"]["publishing"], {}, status)
            self.assertNotIn("api", result["state"]["rolloutWatch"], status)
        self.assertEqual(self.helper("finish-publication", "--service", "api", "--sha", OTHER, "--status", "ok")[0], 2)

    def test_unknown_outcomes_hold_until_an_explicit_resolution(self):
        self.write_state({})
        self.assertEqual(self.begin("web")[0], 0)
        code, result, _ = self.helper("finish-publication", "--service", "web", "--sha", SHA, "--status", "unknown")
        self.assertEqual(code, 0)
        self.assertTrue(result["state"]["publishing"]["web"]["uncertain"])
        self.assertEqual(self.begin("web")[0], 4)
        self.assertEqual(self.helper("update", "--owner", "maintenance", "--expect", self.read()["sha256"], "--patch", '{"publishing": null}')[0], 2)
        code, _, _ = self.helper("resolve-publication", "--service", "web", "--sha", OTHER, "--published", "--expect", self.read()["sha256"])
        self.assertEqual(code, 2)
        code, result, stderr = self.helper("resolve-publication", "--service", "web", "--sha", SHA, "--published", "--expect", self.read()["sha256"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["state"], {"publishing": {}, "rolloutWatch": {"web": {"sha": SHA, "fromTag": "v1.2.3"}}})
        self.assertEqual(self.begin("web")[0], 0)
        self.helper("finish-publication", "--service", "web", "--sha", SHA, "--status", "unknown")
        code, result, _ = self.helper("resolve-publication", "--service", "web", "--sha", SHA, "--not-published", "--expect", self.read()["sha256"])
        self.assertEqual(code, 0)
        self.assertEqual(result["state"]["publishing"], {})

    def test_invalid_arguments_are_refused(self):
        self.write_state({})
        for args in (
            ("begin-publication", "--service", "../web", "--sha", SHA, "--session", "s", "--deploying", "--expect", self.read()["sha256"]),
            ("begin-publication", "--service", "web", "--sha", "HEAD", "--session", "s", "--deploying", "--expect", self.read()["sha256"]),
            ("finish-publication", "--service", "web", "--sha", SHA, "--status", "maybe"),
            ("update", "--owner", "root", "--expect", "missing", "--patch", "{}"),
            ("update", "--owner", "manager", "--expect", "nothex", "--patch", "{}"),
        ):
            self.assertEqual(self.helper(*args)[0], 2, args)
        self.assertEqual(json.loads(self.state.read_text()), {})


if __name__ == "__main__":
    unittest.main()
