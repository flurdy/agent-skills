"""Instruction contracts, not an executable migration or a data-loss certification."""

import fnmatch
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
ROOT = SKILL_DIR.parents[1]
CORE = (SKILL_DIR / 'SKILL.md').read_text()


def reference(name):
    path = SKILL_DIR / 'references' / name
    return path.read_text() if path.exists() else ''


AFTERCARE = reference('aftercare.md')
COMPATIBILITY = reference('compatibility.md')


class MigrationContractTests(unittest.TestCase):
    def test_canonical_entry_and_explicit_aftercare(self):
        self.assertIn('/beads-migrate-to-dolt [repository-path]', CORE)
        self.assertIn('/beads-migrate-to-dolt --aftercare [repository-path]', CORE)
        self.assertNotRegex(CORE, r'(?m)^/beads-migrate\s*$')
        self.assertIn('Never enter aftercare automatically', CORE)
        self.assertIn('(references/aftercare.md)', CORE)
        self.assertIn('(references/compatibility.md)', CORE)

    def test_file_only_target_binding_before_backup(self):
        self.assertIn('next-select stores', CORE)
        self.assertIn('Do not resolve a Bead ID before backup', CORE)
        self.assertIn('Every database command uses `bd -C "$ROOT"`', CORE)
        self.assertIn('redirected or external storage', CORE)

    def test_backup_precedes_store_opening_commands(self):
        self.assertIn('## 2. Quiesce and verify a mandatory backup', CORE)
        self.assertIn('## 3. Inspect the protected store', CORE)
        backup = CORE.index('## 2. Quiesce and verify a mandatory backup')
        inspect = CORE.index('## 3. Inspect the protected store')
        self.assertLess(backup, inspect)
        preflight = CORE[:inspect]
        for block in re.findall(r'```(?:bash|sh)\n(.*?)```', preflight, re.S):
            self.assertNotRegex(block, r'(?m)^bd .*\b(list|export|sql|migrate|doctor|bootstrap)\b')
        for phrase in ('auto-migrate on store open', 'all writers', 'shared server',
                       'copy or verification failure is a hard stop', 'Never overwrite a backup',
                       'WAL/SHM', 'file hashes', 'before counts or schema inspection'):
            self.assertIn(phrase, CORE)

    def test_backup_allocation_failure_never_calls_copy(self):
        recipe = next(block for block in re.findall(r'```bash\n(.*?)```', CORE, re.S)
                      if 'BACKUP=$(mktemp' in block)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in {'mktemp': 'exit 1', 'cp': 'printf called > "$MARKER"'}.items():
                path = root / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o700)
            marker = root / 'copied'
            env = {**os.environ, 'PATH': f'{root}:/usr/bin:/bin', 'MARKER': str(marker),
                   'ROOT': str(root / 'repo'), 'BACKUP_PARENT': str(root / 'backups')}
            result = subprocess.run(['bash', '-c', recipe], cwd=root, env=env,
                                    capture_output=True, timeout=10, check=False)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(marker.exists(), 'copy ran after backup allocation failed')

    def test_permissions_do_not_preapprove_mutation(self):
        frontmatter = CORE.split('---', 2)[1]
        self.assertNotRegex(frontmatter, r'Bash\((bd|dolt|env|git|rm|kill|brew|python3):\*\)')
        patterns = [pattern.replace(':*', ' *') for pattern in re.findall(r'Bash\((.*?)\)', frontmatter)]
        for command in ('bd dolt push', 'bd -C /repo dolt push', 'bd backup sync',
                        'bd bootstrap', 'bd init --reinit-local --discard-remote',
                        'env BD_ALLOW_REMOTE_MIGRATE=1 bd migrate', 'git reset --hard',
                        'rm -rf /repo/.beads'):
            with self.subTest(command=command):
                self.assertFalse(any(fnmatch.fnmatchcase(command, pattern) for pattern in patterns))

    def test_original_data_and_fields_are_preserved(self):
        for phrase in ('Preserve original sources', 'version-compatible exporter',
                       'working copy of the backup', 'Never use a fixed-field converter',
                       'Partial or mixed Dolt is recovery, not permission to reinitialize'):
            self.assertIn(phrase, CORE)
        self.assertNotIn('TOP_FIELDS', CORE)
        self.assertNotRegex(CORE, r'(?m)^\s*rm\s+-(?:rf|fr|f)\b')
        self.assertNotIn('|| true', CORE)

    def test_no_false_success_or_line_count_comparison(self):
        for phrase in ('IDs', 'statuses', 'dependencies', 'comments', 'labels',
                       'memories', 'metadata', 'acceptance criteria', 'priority 0',
                       'Verification mismatch is a hard stop', 'approval cannot turn it into success',
                       'not an issue count', '--include-infra --include-templates --include-gates'):
            self.assertIn(phrase, CORE)
        self.assertNotIn('proceed or investigate', CORE)
        self.assertNotIn('grep -c', CORE)
        self.assertNotIn('--dedup=false', CORE)

    def test_remote_coordination_and_approval(self):
        for phrase in ('exactly one designated migrator', 'BD_ALLOW_REMOTE_MIGRATE=1',
                       'BD_NO_PUSH=false', 'bootstrap --dry-run --json',
                       'remote-tracking', 'one verified adopter',
                       'one visible command per confirmation', 'backup sync',
                       'Never use `migrate schema` to bypass', 'may only validate'):
            self.assertIn(phrase, CORE)
        for block in re.findall(r'```bash\n(.*?)```', CORE, re.S):
            if re.search(r'\b(dolt push|bootstrap --yes)\b', block):
                self.assertEqual(1, len([line for line in block.splitlines() if line.strip()]))

    def test_aftercare_does_not_leak_into_core(self):
        for fragment in ('Husky', 'registry.json', 'git reset', 'git revert', 'worktree remove', 'CLAUDE.md'):
            self.assertNotIn(fragment, CORE)
        for phrase in ('Explicit opt-in only', 'Husky', 'registry.json', 'entry-scoped',
                       'Never rewrite Git history', 'Never force-remove',
                       'BEGIN BEADS INTEGRATION', 'Backup retention', 'separate confirmation'):
            self.assertIn(phrase, AFTERCARE)

    def test_version_evidence_is_bounded(self):
        for phrase in ('bd 1.2.2', 'command-surface evidence', 'not a live migration certification',
                       'Historical', '0.59', '1.0', '--skip-hooks', '--skip-agents',
                       '--allow-stale', 'help init-safety', 'mode must be observed'):
            self.assertIn(phrase, COMPATIBILITY)
        self.assertIn('Read `--help` before each version-sensitive command', CORE)
        self.assertNotIn('latest as of', CORE + AFTERCARE + COMPATIBILITY)
        self.assertNotIn('migrations through v53', CORE)

    def test_gates_and_detection_handoff(self):
        makefile = (ROOT / 'Makefile').read_text()
        targets = makefile.split('TEST_TARGETS :=', 1)[1].split('\n\ntest:', 1)[0]
        self.assertIn('test-beads-migrate', targets)
        self.assertNotIn('test-beads-migrate-cli', targets)
        self.assertIn('test-beads-migrate-cli:', makefile)
        self.assertIn('| beads-migrate-to-dolt |', (ROOT / 'skills/README.md').read_text())
        detector = (ROOT / 'skills/beads-check-dolt-migration/SKILL.md').read_text()
        self.assertIn('before store-opening probes', detector)
        self.assertIn('../beads-migrate-to-dolt/SKILL.md', detector)


if __name__ == '__main__':
    unittest.main()
