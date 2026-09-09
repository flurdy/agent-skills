"""Static workflow contracts plus real-Git checks of the documented capture commands.

These do not execute an LLM workflow or prove any host-native reviewer integration.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = SKILL_DIR.parents[1]
SKILL = (SKILL_DIR / "SKILL.md").read_text()
REFERENCE_PATH = SKILL_DIR / "references" / "evidence.md"
REFERENCE = REFERENCE_PATH.read_text() if REFERENCE_PATH.exists() else ""


class WorkflowContractTests(unittest.TestCase):
    def test_portable_client_resolution(self):
        for client in ("Pi", "Claude Code", "Codex"):
            with self.subTest(client=client):
                self.assertRegex(SKILL, rf"\| {client} \|.*read.*SKILL.md")
        self.assertIn("Never infer availability from the client name", SKILL)
        self.assertIn("Do not type a slash command into a shell", SKILL)

    def test_composed_skills_exist_and_old_assumptions_are_removed(self):
        for name in ("clean-code", "verify-task", "pedantic-review", "second-opinion"):
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())
            self.assertIn(f"`{name}`", SKILL)
        for absent in ("/code-review", "/ultrareview", "Skill /review", "Skill /security-review"):
            self.assertNotIn(absent, SKILL)

    def test_capability_rows_have_explicit_unavailable_behavior(self):
        rows = [line for line in SKILL.splitlines() if re.match(r"\| G(?:[1-7]|5a) ", line)]
        self.assertEqual(8, len(rows))
        for row in rows:
            with self.subTest(row=row):
                self.assertTrue(any(word in row for word in ("manual", "unavailable")))

    def test_artifact_audit_is_a_required_redacted_gate(self):
        self.assertIn('Bash(~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py:*)', SKILL)
        self.assertIn('| G5a Artifact hygiene |', SKILL)
        self.assertIn('G1–G5 plus G5a', SKILL)
        self.assertIn('all eight', SKILL)
        audit = SKILL.split('### G5a — Artifact hygiene', 1)[1].split('### G6', 1)[0]
        self.assertIn('~/.agents/skills/artifact-hygiene/scripts/artifact_hygiene.py --pretty', audit)
        self.assertIn('../artifact-hygiene/SKILL.md#report', audit)
        self.assertIn('coverage before findings', audit)
        self.assertIn('partial is never clean', audit)
        self.assertIn('Exit `0` alone is not clearance', audit)
        self.assertIn('`status: complete`, `verdict: clean`', audit)
        self.assertIn('complete/findings', audit)
        self.assertIn('HALTED', audit)
        self.assertIn('PARTIAL', audit)
        self.assertIn('Never recover raw evidence', audit)
        self.assertIn('Remediation is a separate explicitly approved task', audit)
        self.assertIn('Excluded from the fix loop and Beads writes', audit)

    def test_artifact_audit_is_bound_to_actual_final_checkout(self):
        self.assertIn('### G5a — Artifact hygiene', SKILL)
        audit = SKILL.split('### G5a — Artifact hygiene', 1)[1].split('### G6', 1)[0]
        for field in ('target.head', 'generatedAt', 'provenance', 'coverage', 'revision'):
            self.assertIn(field, audit)
        self.assertIn('full publishable working tree and its own locally resolved unpublished history', audit)
        self.assertIn('not the selected diff or fixed review base', audit)
        self.assertIn('Diff-only PR: G5a is `unavailable`', SKILL)
        checkpoint = SKILL.split('## 2. Final checkpoint and verdict', 1)[1]
        self.assertIn('rerun G5a', checkpoint)
        self.assertIn('before reporting', checkpoint)
        self.assertIn('G5a', REFERENCE)
        self.assertIn('Never recover raw evidence', REFERENCE)

    def test_requested_coverage_controls_verdict_without_hiding_omissions(self):
        self.assertIn("Freeze the expected gate set", SKILL)
        self.assertIn("An unrequested G7", SKILL)
        self.assertIn("CLEAR is scoped to the expected gate set", SKILL)
        self.assertIn("missing expected", SKILL)
        self.assertIn("absent profile is `unavailable`", SKILL)

    def test_secret_indicators_are_validated_before_a_sticky_halt(self):
        self.assertIn("Suspected credentials pause capture", REFERENCE)
        self.assertIn("false positive", REFERENCE)
        self.assertIn("Confirmed secrets halt", REFERENCE)
        self.assertIn("unresolved suspicion is `unavailable`", REFERENCE)

    def test_capability_and_iteration_limits_apply_before_offers(self):
        self.assertIn("Reading a skill does not grant its tools", SKILL)
        self.assertIn("Offer the fix option only when iteration is still available", SKILL)
        self.assertIn("head-pinned neighboring context", SKILL)

    def test_required_manual_gates_are_concrete(self):
        self.assertIn("### Correctness fallback", REFERENCE)
        self.assertIn("### Security fallback", REFERENCE)
        for dimension in ("error paths", "authorization", "untrusted input", "dependencies"):
            self.assertIn(dimension, REFERENCE)
        self.assertIn("self-review, not independent review", REFERENCE)

    def test_final_revision_not_initial_head_drives_evidence(self):
        self.assertIn("fixed comparison base", SKILL)
        self.assertIn("Rebuild the scope after every accepted fix", SKILL)
        self.assertIn("stale", REFERENCE)
        self.assertIn("final revision", REFERENCE)
        self.assertNotIn("Do not re-read `HEAD`", SKILL)
        self.assertNotIn("/tmp/total-review-scope.patch", SKILL)
        self.assertIn("Never overwrite a previous revision", REFERENCE)

    def test_untracked_and_index_content_are_not_lost(self):
        self.assertIn("git diff --no-ext-diff --no-textconv --binary", REFERENCE)
        self.assertIn("git diff --cached --no-ext-diff --no-textconv --binary", REFERENCE)
        self.assertIn("git ls-files --others --exclude-standard -z", REFERENCE)
        self.assertIn("Read the exact contents of every in-scope untracked file", REFERENCE)
        self.assertIn("accepted fix paths", REFERENCE)
        self.assertIn("outside the initial file list", REFERENCE)
        self.assertIn("Do not stage files to capture them", REFERENCE)

    def test_optional_missing_declined_skipped_are_not_passes(self):
        for state in ("unavailable", "declined", "skipped", "stale", "failed"):
            self.assertIn(f"`{state}`", REFERENCE)
        self.assertIn("Only `pass` is a completed successful gate", REFERENCE)
        self.assertIn("PARTIAL", SKILL)
        self.assertIn("never full-gauntlet clearance", SKILL)

    def test_diff_only_pr_cannot_validate_local_fixes(self):
        self.assertIn("--repo {owner}/{repo}", SKILL)
        self.assertIn("Do not auto-checkout", SKILL)
        self.assertIn("diff-only", SKILL)
        self.assertIn("G1 and executable tests in G2 are `unavailable`", SKILL)
        self.assertIn("local fixes are not evidence for the remote PR head", SKILL)
        self.assertIn("re-read the qualified PR head and base", " ".join(SKILL.split()))

    def test_reviewers_get_exact_local_packet_not_stale_pr(self):
        self.assertIn("second-opinion ask", SKILL)
        self.assertNotIn("second-opinion review-pr", SKILL)
        self.assertIn("Do not let a composed skill replace the ledger scope", SKILL)

    def test_iteration_is_bounded_and_rechecks_cheap_gates(self):
        self.assertIn("2 total passes", SKILL)
        self.assertIn("increment `pass_count` before returning to G1", SKILL)
        self.assertIn("--no-iterate", SKILL)
        self.assertNotIn("--continue", SKILL)
        self.assertIn("Halt is sticky", SKILL)

    def test_composer_does_not_restore_blanket_runner_permissions(self):
        frontmatter = SKILL.split('---', 2)[1]
        self.assertNotRegex(frontmatter, r'Bash\((git|bd|make|npm|npx):\*\)')
        self.assertIn('Bash(bd -C * create:*)', frontmatter)
        self.assertIn('per-command permission', SKILL)

    def test_new_coverage_handoff_obeys_sticky_halt(self):
        self.assertIn('invalidate G2', SKILL)
        self.assertIn('no in-pass jump back to G2', SKILL)
        self.assertIn('fresh run from G1', SKILL)

    def test_safety_and_ledger_authority(self):
        self.assertIn("one authoritative ledger", SKILL)
        self.assertIn("Never send secrets", SKILL)
        self.assertIn("--inline-findings", SKILL)
        self.assertIn("next-select stores", SKILL)
        self.assertIn("bd -C <directory>", SKILL)
        self.assertIn("route failure is not permission to switch execution modes", SKILL)
        self.assertIn(".artifacts/", REFERENCE)


class CaptureCommandTests(unittest.TestCase):
    def test_late_tracked_staged_and_untracked_fixes_change_capture(self):
        blocks = re.findall(r"```bash\n(.*?)\n```", REFERENCE, flags=re.S)
        captures = {
            block.splitlines()[0].removeprefix("# scope-capture: "): block
            for block in blocks if block.startswith("# scope-capture: ")
        }
        self.assertEqual({"head", "status", "worktree", "index", "untracked"}, set(captures))
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            env = {
                key: value for key, value in os.environ.items()
                if not key.startswith("GIT_") and key not in {"HOME", "XDG_CONFIG_HOME"}
            }
            env.update(HOME=directory, XDG_CONFIG_HOME=directory,
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
                    stderr=subprocess.DEVNULL, env=env,
                )

            git("init", "-q", "--initial-branch=main")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            tracked = repo / "tracked.txt"
            tracked.write_text("base\n")
            git("add", "tracked.txt")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD").decode().strip()

            def snapshot():
                return {
                    name: subprocess.check_output(
                        ["bash", "-c", command], cwd=repo, env={**env, "SCOPE_BASE": base}
                    ) for name, command in captures.items()
                }

            before = snapshot()
            tracked.write_text("accepted late fix\n")
            git("add", "tracked.txt")
            # Different index and working-tree content must both remain visible.
            tracked.write_text("second accepted fix\n")
            (repo / "new file.txt").write_text("new untracked fix\n")
            after = snapshot()
            self.assertNotEqual(before, after)
            self.assertIn(b"accepted late fix", after["index"])
            self.assertIn(b"second accepted fix", after["worktree"])
            self.assertIn(b"new file.txt\x00", after["untracked"])
            self.assertEqual(base, git("rev-parse", "HEAD").decode().strip())
            self.assertIn(b"?? new file.txt\x00", git("status", "--porcelain=v1", "-z"))
            # Committing accepted work must not shrink a --uncommitted run's fixed base.
            git("add", "tracked.txt", "new file.txt")
            git("commit", "-qm", "accepted fixes")
            committed = snapshot()
            self.assertIn(b"second accepted fix", committed["worktree"])
            self.assertIn(b"new untracked fix", committed["worktree"])


if __name__ == "__main__":
    unittest.main()
