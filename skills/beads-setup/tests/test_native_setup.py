"""Opt-in characterization of the installed bd in disposable repositories; no network or publication."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BD = shutil.which("bd")
CLASSIFIER = Path(__file__).resolve().parents[1] / "scripts/ancestor_stores.py"
_spec = importlib.util.spec_from_file_location("ancestor_stores", CLASSIFIER)
ancestor_stores = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ancestor_stores)


def snapshot(path):
    """Names, bytes and modification times beneath path, for an unchanged-state assertion."""
    return {str(item.relative_to(path)): (item.stat().st_mtime_ns, item.read_bytes() if item.is_file() else None)
            for item in sorted(path.rglob("*"))}


@unittest.skipUnless(os.environ.get("BEADS_NATIVE_SETUP_TESTS") == "1", "opt in with BEADS_NATIVE_SETUP_TESTS=1")
class NativeSetupTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(BD, "native gate requires an installed bd")
        # Native init fixtures must have no discoverable ancestor store; registry-only ancestors are inert.
        self.temp = tempfile.TemporaryDirectory(prefix="native-setup-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(os.path.realpath(self.temp.name))
        report = ancestor_stores.classify(str(self.base))
        self.assertEqual(report["status"], "clear", f"fixture ancestors could route bd: {report['entries']}")
        self.home = self.base / "home"
        self.home.mkdir()
        self.repo = self.base / "target"
        self.launcher = self.base / "launcher"
        self.launcher.mkdir()
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "DOLT_ROOT_PATH": str(self.home), "DOLT_DISABLE_UPDATE_CHECK": "1",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "file",
            "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.com",
            "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.com",
            "BD_DISABLE_METRICS": "1", "BD_DISABLE_EVENT_FLUSH": "1",
            "BD_BACKUP_ENABLED": "false", "BD_EXPORT_AUTO": "false", "BD_EVENTS_EXPORT": "false",
            "BD_NO_PUSH": "true", "BD_DOLT_AUTO_PUSH": "false",
        }
        self.assertRegex(self.call(BD, "--version").stdout, r"^bd version \S+")
        self.seed(self.repo)
        self.remote = self.base / "private.git"
        self.seed(self.remote)
        self.url = "git+" + self.remote.as_uri()
        self.call("git", "-C", str(self.repo), "remote", "add", "origin", str(self.base / "wrong-source-origin"))

    def call(self, *args, check=True):
        return subprocess.run(args, cwd=self.launcher, env=self.env, text=True, capture_output=True,
                              timeout=90, check=check)

    def inspect_bd(self, *args):
        return self.call("/usr/bin/env", "--chdir=" + str(self.repo), BD, "-C", str(self.repo),
                         "--sandbox", "--readonly", *args)

    def where(self, directory, *prefix, flag=True):
        target = ("-C", str(directory)) if flag else ()
        result = self.call(*prefix, "/usr/bin/env", "--chdir=" + str(directory), BD, *target,
                           "--sandbox", "--readonly", "where", "--json", check=False)
        located = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
        return result.returncode, {**located, "stderr": result.stderr.strip()}

    def init(self, directory, prefix, *remote):
        return self.call("/usr/bin/env", "--chdir=" + str(directory), BD, "--sandbox", "init", "--prefix", prefix,
                         *remote, "--non-interactive", "--skip-agents", "--skip-hooks", check=False)

    def test_registry_only_ancestor_does_not_route_fresh_init(self):
        ancestor = self.base / ".beads"
        ancestor.mkdir()
        for name in ("registry.json", "registry.lock", "machine-id"):
            (ancestor / name).write_text("{}\n")
        (ancestor / "eventsData").mkdir()
        report = ancestor_stores.classify(str(self.repo))
        self.assertEqual(report["status"], "clear")
        self.assertIn({"path": str(ancestor), "kind": "registry-only"}, report["entries"])
        before = snapshot(ancestor)
        for flag in (True, False):
            code, located = self.where(self.repo, flag=flag)
            self.assertNotEqual(code, 0, f"registry-only ancestor bound bd: {located}")
        result = self.init(self.repo, "fixture", "--remote", self.url)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        code, located = self.where(self.repo)
        self.assertEqual((code, located.get("path")), (0, str(self.repo / ".beads")))
        self.assertEqual(self.inspect_bd("config", "get", "sync.remote").stdout.strip(), self.url)
        self.assertEqual(snapshot(ancestor), before, "registry-only ancestor changed")

    def test_real_ancestor_store_outside_independent_git_root_routes_bd(self):
        outer = self.base / "outer"
        self.seed(outer)
        result = self.init(outer, "outer")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        inner = outer / "inner"
        self.seed(inner)
        self.assertEqual(self.call("git", "-C", str(inner), "rev-parse", "--show-toplevel").stdout.strip(), str(inner))
        report = ancestor_stores.classify(str(inner))
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["entries"][0]["kind"], "project-store")
        before = snapshot(outer / ".beads")
        # -C lookups aimed at the fresh target bind the ancestor store across the Git-root boundary;
        # the cwd-only lookup used by fresh init stops at the Git root.
        code, located = self.where(inner)
        self.assertEqual((code, located.get("path")), (0, str(outer / ".beads")), located)
        code, located = self.where(inner, flag=False)
        self.assertNotEqual(code, 0, located)
        # An ambient override routes the cwd-only form, even for an unrelated store-free target.
        code, located = self.where(self.repo, "/usr/bin/env", "BEADS_DIR=" + str(outer / ".beads"), flag=False)
        self.assertEqual((code, located.get("path")), (0, str(outer / ".beads")), located)
        after = snapshot(outer / ".beads")
        changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
        # Characterized on bd 1.3.4: even --readonly store-opening probes rewrite Dolt manifest/journal
        # files, so preview classification lists names and never opens an ancestor store with bd.
        self.assertTrue(all(key.startswith("embeddeddolt/") for key in changed), changed)

    def seed(self, path):
        path.mkdir()
        self.call("git", "-C", str(path), "init", "-q", "-b", "seed")
        (path / "README.md").write_text("fixture\n")
        self.call("git", "-C", str(path), "add", "README.md")
        self.call("git", "-C", str(path), "commit", "-qm", "fixture")

    def test_explicit_remote_and_bound_cwd_preserve_authored_files(self):
        authored = {
            "AGENTS.md": "authored policy\n", "CLAUDE.md": "authored Claude policy\n",
            ".claude/settings.json": '{"permissions":{"deny":["anything"]}}\n',
            ".codex/config.toml": "# authored config\n", ".agents/skills/personal/SKILL.md": "authored skill\n",
        }
        for name, content in authored.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.call("git", "-C", str(self.repo), "add", *authored)
        self.call("git", "-C", str(self.repo), "commit", "-qm", "authored fixture")
        initial = self.call("git", "-C", str(self.repo), "rev-parse", "HEAD").stdout.strip()
        remote_refs = self.call("git", "-C", str(self.remote), "show-ref").stdout
        sentinel = self.launcher / "AGENTS.md"
        sentinel.write_text("launcher must not change\n")
        refused = self.call("/usr/bin/env", "--chdir=" + str(self.repo), BD, "-C", str(self.repo),
                            "--sandbox", "init", "--prefix", "fixture", "--remote", self.url,
                            "--non-interactive", "--skip-agents", "--skip-hooks", check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("no beads project found", refused.stderr)
        self.assertFalse((self.repo / ".beads").exists())
        result = self.call("/usr/bin/env", "--chdir=" + str(self.repo), BD,
                           "--sandbox", "init", "--prefix", "fixture", "--remote", self.url,
                           "--non-interactive", "--skip-agents", "--skip-hooks", check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for name, content in authored.items():
            self.assertEqual((self.repo / name).read_text(), content, name)
        self.assertEqual(sentinel.read_text(), "launcher must not change\n")
        self.assertFalse((self.launcher / ".beads").exists())
        self.assertEqual(self.call("git", "-C", str(self.repo), "status", "--porcelain").stdout, "")
        self.assertEqual(self.call("git", "-C", str(self.repo), "rev-parse", "HEAD^").stdout.strip(), initial)
        changed = self.call("git", "-C", str(self.repo), "diff", "--name-only", initial, "HEAD").stdout.splitlines()
        self.assertTrue(changed)
        self.assertTrue(all(name == ".gitignore" or name.startswith(".beads/") for name in changed), changed)
        self.assertIn(self.url, (self.repo / ".beads/config.yaml").read_text())
        remote = self.inspect_bd("dolt", "remote", "list").stdout
        self.assertIn(self.url, remote)
        self.assertIn("origin", remote)
        self.assertFalse((self.repo / ".beads/hooks").exists())
        self.assertEqual(self.call("git", "-C", str(self.remote), "show-ref").stdout, remote_refs)
        self.assertEqual(self.call("git", "-C", str(self.repo), "remote", "get-url", "origin").stdout.strip(),
                         str(self.base / "wrong-source-origin"))
        rows = self.inspect_bd("list", "--all", "--limit=0", "--json")
        self.assertEqual(json.loads(rows.stdout), [])
        self.assertEqual(self.inspect_bd("config", "get", "sync.remote").stdout.strip(), self.url)
        self.inspect_bd("vc", "status", "--json")
        self.inspect_bd("migrate", "--inspect", "--json")
        self.inspect_bd("dolt", "status", "--json")
        self.assertIn("FLAG SURFACE", self.call(BD, "help", "init-safety").stdout)
        metadata = json.loads((self.repo / ".beads/metadata.json").read_text())
        self.assertEqual(metadata["dolt_mode"], "embedded")
        dolt = shutil.which("dolt")
        self.assertTrue(dolt, "native identity gate requires the matching Dolt CLI")
        query = "SELECT active_branch() AS branch, DOLT_HASHOF('HEAD') AS head, (SELECT COUNT(*) FROM dolt_status) AS dirty, (SELECT MAX(version) FROM schema_migrations) AS schema_version"
        state = self.call("/usr/bin/env", "--chdir=" + str(self.repo), dolt,
                          "--data-dir", str(self.repo / ".beads/embeddeddolt"),
                          "--use-db", metadata["dolt_database"], "sql", "--disable-auto-gc", "-r", "json", "-q", query)
        data = json.loads(state.stdout)["rows"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["branch"], "main")
        self.assertRegex(data[0]["head"], r"^[0-9a-v]{32}$")
        self.assertEqual(data[0]["dirty"], 0)
        self.assertGreater(data[0]["schema_version"], 0)
        # Transport-only proof: an empty Git-backed remote fetch can exit 0 without data.
        database = self.repo / ".beads/embeddeddolt" / metadata["dolt_database"]
        self.call("/usr/bin/env", "--chdir=" + str(database), dolt, "fetch", "origin")
        refspec = self.call("/usr/bin/env", "--chdir=" + str(database), dolt, "fetch", "origin",
                            "refs/heads/main:refs/remotes/origin/main", check=False)
        self.assertNotEqual(refspec.returncode, 0, "explicit missing-branch fetch must not prove publication")
        missing = self.call(dolt, "--data-dir", str(self.repo / ".beads/embeddeddolt"),
                            "--use-db", metadata["dolt_database"], "sql", "--disable-auto-gc", "-r", "json",
                            "-q", "SELECT DOLT_HASHOF('origin/main')", check=False)
        self.assertNotEqual(missing.returncode, 0, "an empty Git remote must not prove Dolt publication")
        self.assertEqual(self.call("git", "-C", str(self.remote), "show-ref").stdout, remote_refs)

    def test_init_would_commit_unrelated_staged_content_so_preflight_must_refuse(self):
        unrelated = self.repo / "unrelated.txt"
        unrelated.write_text("not setup work\n")
        self.call("git", "-C", str(self.repo), "add", "unrelated.txt")
        result = self.call("/usr/bin/env", "--chdir=" + str(self.repo), BD, "--sandbox", "init",
                           "--prefix", "fixture", "--remote", self.url,
                           "--non-interactive", "--skip-agents", "--skip-hooks", check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        committed = self.call("git", "-C", str(self.repo), "show", "HEAD:unrelated.txt").stdout
        self.assertEqual(committed, "not setup work\n")


if __name__ == "__main__":
    unittest.main()
