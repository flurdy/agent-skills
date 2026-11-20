from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from github_remote import (  # noqa: E402
    GitHubRemote,
    default_github_host,
    github_remote,
    github_repository,
    known_github_hosts,
)

ENTERPRISE = "ghe.example.com"


class GitHubRemoteTest(unittest.TestCase):
    def test_enterprise_remotes_resolve_only_for_known_hosts(self) -> None:
        remotes = (
            f"git@{ENTERPRISE}:acme/widgets.git",
            f"ssh://git@{ENTERPRISE}/acme/widgets.git",
            f"ssh://git@{ENTERPRISE}:7999/acme/widgets.git",
            f"https://{ENTERPRISE}/acme/widgets.git",
            "https://GHE.Example.com/acme/widgets",
        )
        for remote in remotes:
            with self.subTest(remote=remote):
                self.assertEqual(
                    GitHubRemote(ENTERPRISE, "acme/widgets"),
                    github_remote(remote, {ENTERPRISE}),
                )
                self.assertIsNone(github_remote(remote))
                self.assertIsNone(github_repository(remote))

    def test_enterprise_hosts_are_exact_and_have_no_ssh_aliases(self) -> None:
        for remote in (
            f"git@work.{ENTERPRISE}:acme/widgets.git",
            f"https://{ENTERPRISE}.evil.example/acme/widgets.git",
            f"https://evil.example/{ENTERPRISE}/acme/widgets.git",
            f"https://{ENTERPRISE}/acme/widgets/extra",
            f"ftp://{ENTERPRISE}/acme/widgets.git",
        ):
            with self.subTest(remote=remote):
                self.assertIsNone(github_remote(remote, {ENTERPRISE}))

    def test_github_com_and_its_ssh_aliases_keep_the_default_host(self) -> None:
        for remote in (
            "git@github.com:acme/widgets.git",
            "git@work.github.com:acme/widgets.git",
            "https://github.com/acme/widgets.git",
        ):
            with self.subTest(remote=remote):
                remote_identity = github_remote(remote, {ENTERPRISE})
                self.assertEqual(GitHubRemote("github.com", "acme/widgets"), remote_identity)
                self.assertEqual("acme/widgets", remote_identity.qualified)
        self.assertEqual(
            f"{ENTERPRISE}/acme/widgets",
            GitHubRemote(ENTERPRISE, "acme/widgets").qualified,
        )

    def test_known_hosts_come_from_the_gh_hosts_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "hosts.yml").write_text(
                "github.com:\n"
                "    user: someone\n"
                f"{ENTERPRISE.upper()}:\n"
                "    git_protocol: ssh\n"
                "'quoted.example.com':\n"
                "not a host:\n"
                "# comment.example.com:\n",
                encoding="utf-8",
            )
            hosts = known_github_hosts({"GH_CONFIG_DIR": directory})
        self.assertEqual({"github.com", ENTERPRISE, "quoted.example.com"}, hosts)

    def test_xdg_config_home_locates_the_hosts_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "gh").mkdir()
            (Path(directory) / "gh" / "hosts.yml").write_text(f"{ENTERPRISE}:\n")
            hosts = known_github_hosts({"XDG_CONFIG_HOME": directory})
        self.assertIn(ENTERPRISE, hosts)

    def test_gh_host_counts_only_with_an_enterprise_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = {"GH_CONFIG_DIR": directory, "GH_HOST": ENTERPRISE}
            self.assertEqual({"github.com"}, known_github_hosts(base))
            for variable in ("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
                with self.subTest(variable=variable):
                    self.assertEqual(
                        {"github.com", ENTERPRISE},
                        known_github_hosts({**base, variable: "set"}),
                    )

    def test_default_host_is_gh_host_only_when_gh_knows_it(self) -> None:
        hosts = {"github.com", ENTERPRISE}
        self.assertEqual(ENTERPRISE, default_github_host({"GH_HOST": "GHE.example.com"}, hosts))
        self.assertEqual("github.com", default_github_host({"GH_HOST": "evil.example"}, hosts))
        self.assertEqual("github.com", default_github_host({}, hosts))

    def test_cli_prints_repositories_only_on_the_default_host(self) -> None:
        script = Path(__file__).parents[1] / "scripts" / "github_remote.py"
        with tempfile.TemporaryDirectory() as directory:
            base = {**os.environ, "GH_CONFIG_DIR": directory}
            base.pop("GH_HOST", None)
            enterprise = {**base, "GH_HOST": ENTERPRISE, "GH_ENTERPRISE_TOKEN": "set"}
            cases = (
                (base, "git@github.com:acme/widgets.git", 0),
                (base, f"git@{ENTERPRISE}:acme/widgets.git", 1),
                (enterprise, f"git@{ENTERPRISE}:acme/widgets.git", 0),
                (enterprise, "git@github.com:acme/widgets.git", 1),
            )
            for environment, remote, code in cases:
                with self.subTest(remote=remote, host=environment.get("GH_HOST")):
                    completed = subprocess.run(
                        [sys.executable, str(script), remote],
                        env=environment, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(code, completed.returncode)
                    self.assertEqual("acme/widgets\n" if code == 0 else "", completed.stdout)

    def test_missing_hosts_file_falls_back_to_github_com(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                {"github.com"},
                known_github_hosts({"GH_CONFIG_DIR": str(Path(directory) / "absent")}),
            )


if __name__ == "__main__":
    unittest.main()
