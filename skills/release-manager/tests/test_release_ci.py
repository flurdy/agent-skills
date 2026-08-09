import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
RELEASE_CI = SKILL_DIR / "scripts" / "release-ci"


class ReleaseCiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_manifest(self, provider, settings=""):
        docs = self.root / "docs"
        docs.mkdir(exist_ok=True)
        body = f"ci:\n  provider: {provider}\n"
        if settings:
            body += textwrap.indent(textwrap.dedent(settings).strip() + "\n", "  ")
        (docs / "release-manifest.yaml").write_text(body, encoding="utf-8")

    def create_service(self, name, remote=None):
        service = self.root / name
        service.mkdir()
        run(["git", "init", "-b", "main"], service)
        (service / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        run(["git", "add", "README.md"], service)
        run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                "initial",
            ],
            service,
        )
        sha = run(["git", "rev-parse", "HEAD"], service).stdout.strip()
        remote = remote or f"git@github.com:acme/{name}.git"
        run(["git", "remote", "add", "origin", remote], service)
        run(["git", "update-ref", "refs/remotes/origin/main", sha], service)
        run(["git", "branch", "--set-upstream-to=origin/main", "main"], service)
        return sha

    def write_command(self, name, body):
        path = self.bin_dir / name
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def run_ci(self, *services, env=None):
        command_env = os.environ.copy()
        command_env.update(
            {
                "PATH": f"{self.bin_dir}:{command_env['PATH']}",
                "RELEASE_PROJECT_ROOT": str(self.root),
            }
        )
        if env:
            command_env.update(env)
        return subprocess.run(
            [str(RELEASE_CI), *services],
            cwd=self.root,
            env=command_env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_no_provider_returns_bounded_unknown_evidence(self):
        sha = self.create_service("web")

        result = self.run_ci("web")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("none", metadata(result.stdout)["provider"])
        self.assertEqual("unavailable", metadata(result.stdout)["availability"])
        self.assertEqual(
            ["web", "unknown", "-", "-", sha, "-", "provider-none"],
            rows(result.stdout)[0],
        )

    def test_circleci_accepts_only_an_exact_revision(self):
        sha = self.create_service("web")
        self.write_manifest(
            "circleci",
            """
            circleci:
              token_env: TEST_CIRCLE_TOKEN
            """,
        )
        self.write_command(
            "curl",
            f"""
            #!/usr/bin/env python3
            import json, os, sys
            url = sys.argv[-1]
            if '/workflow' in url:
                status = os.environ.get("TEST_WORKFLOW_STATUS", "success")
                if os.environ.get("TEST_CIRCLE_PAGINATE") and 'page-token=next' in url:
                    status = "failed"
                response = {{"items": [{{"status": status}}]}}
                if os.environ.get("TEST_CIRCLE_PAGINATE") and 'page-token=' not in url:
                    response["next_page_token"] = "next"
                print(json.dumps(response))
            else:
                print(json.dumps({{"items": [{{
                    "id": "pipeline-1",
                    "number": 42,
                    "vcs": {{"branch": os.environ.get("TEST_CIRCLE_REF", "main"), "revision": "{sha}"}}
                }}]}}))
            """,
        )

        result = self.run_ci("web", env={"TEST_CIRCLE_TOKEN": "secret"})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("circleci", metadata(result.stdout)["provider"])
        self.assertEqual("available", metadata(result.stdout)["availability"])
        row = rows(result.stdout)[0]
        self.assertEqual(["web", "success", "main", sha, sha], row[:5])
        self.assertIn("app.circleci.com/pipelines/github/acme/web/42", row[5])
        self.assertEqual("exact-revision", row[6])

        for native, expected in (
            ("failed", "failed"),
            ("running", "running"),
            ("error", "error"),
        ):
            with self.subTest(native=native):
                mapped = self.run_ci(
                    "web",
                    env={
                        "TEST_CIRCLE_TOKEN": "secret",
                        "TEST_WORKFLOW_STATUS": native,
                    },
                )
                self.assertEqual(expected, rows(mapped.stdout)[0][1])

        paginated = self.run_ci(
            "web",
            env={"TEST_CIRCLE_TOKEN": "secret", "TEST_CIRCLE_PAGINATE": "1"},
        )
        self.assertEqual("failed", rows(paginated.stdout)[0][1])

        missing_ref = self.run_ci(
            "web",
            env={"TEST_CIRCLE_TOKEN": "secret", "TEST_CIRCLE_REF": ""},
        )
        self.assertEqual("unknown", rows(missing_ref.stdout)[0][1])
        self.assertEqual("-", rows(missing_ref.stdout)[0][2])
        self.assertEqual("missing-ref", rows(missing_ref.stdout)[0][6])

    def test_circleci_derives_bitbucket_vcs_from_checkout_origin(self):
        sha = self.create_service(
            "worker",
            remote="git@bitbucket.org:acme/worker.git",
        )
        self.write_manifest("circleci")
        log = self.root / "curl.log"
        self.write_command(
            "curl",
            f"""
            #!/usr/bin/env python3
            import json, os, sys
            url = sys.argv[-1]
            with open(os.environ["TEST_CURL_LOG"], "a", encoding="utf-8") as output:
                output.write(url + "\\n")
            if url.endswith('/workflow'):
                print(json.dumps({{"items": [{{"status": "success"}}]}}))
            else:
                print(json.dumps({{"items": [{{
                    "id": "pipeline-bb",
                    "number": 4,
                    "vcs": {{"branch": "main", "revision": "{sha}"}}
                }}]}}))
            """,
        )

        result = self.run_ci(
            "worker",
            env={"CIRCLECI_TOKEN": "secret", "TEST_CURL_LOG": str(log)},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("success", rows(result.stdout)[0][1])
        self.assertIn("project/bb/acme/worker/pipeline", log.read_text(encoding="utf-8"))
        self.assertIn("app.circleci.com/pipelines/bitbucket/acme/worker/4", rows(result.stdout)[0][5])

    def test_circleci_revision_mismatch_is_unknown(self):
        expected = self.create_service("web")
        observed = "f" * 40
        self.write_manifest("circleci")
        self.write_command(
            "curl",
            f"""
            #!/usr/bin/env python3
            import json
            print(json.dumps({{"items": [{{
                "id": "pipeline-1",
                "number": 7,
                "vcs": {{"branch": "main", "revision": "{observed}"}}
            }}]}}))
            """,
        )

        result = self.run_ci("web", env={"CIRCLECI_TOKEN": "secret"})

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["web", "unknown", "main", observed, expected],
            rows(result.stdout)[0][:5],
        )
        self.assertEqual("revision-mismatch", rows(result.stdout)[0][6])

    def test_github_actions_maps_an_exact_completed_run(self):
        sha = self.create_service("api")
        self.write_manifest("github-actions")
        self.write_command(
            "gh",
            f"""
            #!/usr/bin/env python3
            import json, os
            request = ' '.join(os.sys.argv)
            run = {{
                "head_sha": "{sha}",
                "head_branch": os.environ.get("TEST_GITHUB_REF", "main"),
                "status": os.environ.get("TEST_GITHUB_STATUS", "completed"),
                "conclusion": os.environ.get("TEST_GITHUB_CONCLUSION", "success"),
                "html_url": "https://github.com/acme/api/actions/runs/1"
            }}
            runs = [run]
            extra = os.environ.get("TEST_GITHUB_EXTRA_CONCLUSION")
            if extra:
                runs.append({{**run, "conclusion": extra, "html_url": "https://github.com/acme/api/actions/runs/2"}})
            total = len(runs)
            if os.environ.get("TEST_GITHUB_PAGINATE"):
                total = 2
                if 'page=2' in os.sys.argv:
                    runs = [{{**run, "conclusion": "failure", "html_url": "https://github.com/acme/api/actions/runs/2"}}]
            print(json.dumps({{"total_count": total, "workflow_runs": runs}}))
            """,
        )

        result = self.run_ci("api")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("available", metadata(result.stdout)["availability"])
        self.assertEqual(
            [
                "api",
                "success",
                "main",
                sha,
                sha,
                "https://github.com/acme/api/actions/runs/1",
                "exact-revision",
            ],
            rows(result.stdout)[0],
        )
        for native_status, conclusion, expected in (
            ("in_progress", "", "running"),
            ("completed", "failure", "failed"),
        ):
            with self.subTest(native_status=native_status, conclusion=conclusion):
                mapped = self.run_ci(
                    "api",
                    env={
                        "TEST_GITHUB_STATUS": native_status,
                        "TEST_GITHUB_CONCLUSION": conclusion,
                    },
                )
                self.assertEqual(expected, rows(mapped.stdout)[0][1])

        mixed = self.run_ci("api", env={"TEST_GITHUB_EXTRA_CONCLUSION": "failure"})
        self.assertEqual("failed", rows(mixed.stdout)[0][1])

        paginated = self.run_ci("api", env={"TEST_GITHUB_PAGINATE": "1"})
        self.assertEqual("failed", rows(paginated.stdout)[0][1])

        missing_ref = self.run_ci("api", env={"TEST_GITHUB_REF": ""})
        self.assertEqual("unknown", rows(missing_ref.stdout)[0][1])
        self.assertEqual("-", rows(missing_ref.stdout)[0][2])
        self.assertEqual("missing-ref", rows(missing_ref.stdout)[0][6])

        mismatched_ref = self.run_ci("api", env={"TEST_GITHUB_REF": "other"})
        self.assertEqual("unknown", rows(mismatched_ref.stdout)[0][1])
        self.assertEqual("ref-mismatch", rows(mismatched_ref.stdout)[0][6])

    def test_cloud_build_maps_an_exact_repository_build(self):
        sha = self.create_service(
            "worker",
            remote="git@gitlab.com:acme/worker.git",
        )
        self.write_manifest(
            "cloud-build",
            """
            cloud-build:
              project: example-project
              region: europe-west1
            """,
        )
        self.write_command(
            "gcloud",
            f"""
            #!/usr/bin/env python3
            import json, os
            build = {{
                "status": os.environ.get("TEST_CLOUD_STATUS", "SUCCESS"),
                "logUrl": "https://console.cloud.google.com/cloud-build/builds/1",
                "substitutions": {{
                    "COMMIT_SHA": "{sha}",
                    "REPO_NAME": "worker",
                    "BRANCH_NAME": os.environ.get("TEST_CLOUD_REF", "main")
                }}
            }}
            builds = [build]
            extra = os.environ.get("TEST_CLOUD_EXTRA_STATUS")
            if extra:
                builds.append({{**build, "status": extra, "logUrl": "https://console.cloud.google.com/cloud-build/builds/2"}})
            if os.environ.get("TEST_CLOUD_MALFORMED"):
                builds.append("malformed")
            print(json.dumps(builds))
            """,
        )

        result = self.run_ci("worker")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("available", metadata(result.stdout)["availability"])
        self.assertEqual(
            [
                "worker",
                "success",
                "main",
                sha,
                sha,
                "https://console.cloud.google.com/cloud-build/builds/1",
                "exact-revision",
            ],
            rows(result.stdout)[0],
        )
        for native, expected in (
            ("WORKING", "running"),
            ("FAILURE", "failed"),
            ("INTERNAL_ERROR", "error"),
        ):
            with self.subTest(native=native):
                mapped = self.run_ci("worker", env={"TEST_CLOUD_STATUS": native})
                self.assertEqual(expected, rows(mapped.stdout)[0][1])

        mixed = self.run_ci("worker", env={"TEST_CLOUD_EXTRA_STATUS": "FAILURE"})
        self.assertEqual("failed", rows(mixed.stdout)[0][1])

        malformed = self.run_ci("worker", env={"TEST_CLOUD_MALFORMED": "1"})
        self.assertEqual("unknown", rows(malformed.stdout)[0][1])
        self.assertEqual("malformed-response", rows(malformed.stdout)[0][6])

        missing_ref = self.run_ci("worker", env={"TEST_CLOUD_REF": ""})
        self.assertEqual("unknown", rows(missing_ref.stdout)[0][1])
        self.assertEqual("-", rows(missing_ref.stdout)[0][2])
        self.assertEqual("missing-ref", rows(missing_ref.stdout)[0][6])

    def test_partial_provider_failure_does_not_hide_other_services(self):
        good_sha = self.create_service("good")
        bad_sha = self.create_service("bad")
        self.write_manifest("github-actions")
        self.write_command(
            "gh",
            f"""
            #!/usr/bin/env python3
            import json, sys
            request = ' '.join(sys.argv)
            if '/bad/' in request:
                print('api unavailable', file=sys.stderr)
                raise SystemExit(1)
            print(json.dumps({{"workflow_runs": [{{
                "head_sha": "{good_sha}",
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.com/acme/good/actions/runs/1"
            }}]}}))
            """,
        )

        result = self.run_ci("good", "bad")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("partial", metadata(result.stdout)["availability"])
        evidence = {row[0]: row for row in rows(result.stdout)}
        self.assertEqual("success", evidence["good"][1])
        self.assertEqual(["unknown", "-", "-", bad_sha], evidence["bad"][1:5])
        self.assertEqual("provider-error", evidence["bad"][6])

    def test_missing_credentials_command_and_malformed_output_fail_safely(self):
        sha = self.create_service("web")
        self.write_manifest("circleci")
        self.write_command("curl", "#!/usr/bin/env bash\nprintf '{}\\n'\n")

        credentials = self.run_ci(
            "web",
            env={
                "CIRCLECI_TOKEN": "",
                "SECRET_API_KEY_PROJECT": "",
            },
        )

        self.assertEqual(0, credentials.returncode, credentials.stderr)
        self.assertEqual("unavailable", metadata(credentials.stdout)["availability"])
        self.assertEqual("missing-credentials", rows(credentials.stdout)[0][6])

        self.write_manifest("github-actions")
        missing = self.run_ci("web", env={"RELEASE_CI_GH": "missing-gh"})

        self.assertEqual(0, missing.returncode, missing.stderr)
        self.assertEqual("unavailable", metadata(missing.stdout)["availability"])
        self.assertEqual(["unknown", "-", "-", sha], rows(missing.stdout)[0][1:5])
        self.assertEqual("missing-command", rows(missing.stdout)[0][6])

        self.write_command("gh", "#!/usr/bin/env bash\nprintf 'not-json\\n'\n")
        malformed = self.run_ci("web")

        self.assertEqual(0, malformed.returncode, malformed.stderr)
        self.assertEqual("unavailable", metadata(malformed.stdout)["availability"])
        self.assertEqual("malformed-response", rows(malformed.stdout)[0][6])

        missing_git = self.run_ci("web", env={"RELEASE_CI_GIT": "/definitely/missing"})
        self.assertEqual(0, missing_git.returncode, missing_git.stderr)
        self.assertEqual("unknown", rows(missing_git.stdout)[0][1])
        self.assertEqual("missing-git", rows(missing_git.stdout)[0][6])


def run(command, cwd):
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def metadata(output):
    lines = output.splitlines()
    start = lines.index("---SOURCE---") + 1
    end = lines.index("---CI---")
    return dict(line.split("=", 1) for line in lines[start:end])


def rows(output):
    lines = output.splitlines()
    start = lines.index("---CI---") + 2
    return [line.split("|") for line in lines[start:]]


if __name__ == "__main__":
    unittest.main()
