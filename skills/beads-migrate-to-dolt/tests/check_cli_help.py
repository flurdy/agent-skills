"""Opt-in command-surface checks; never a migration or a live database probe."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


BD = shutil.which('bd')


@unittest.skipUnless(BD, 'bd unavailable: CLI-help evidence skipped')
class CliHelpTests(unittest.TestCase):
    def test_documented_command_surface_without_database(self):
        commands = [
            (['migrate', '--help'], ['--inspect', '--dry-run', '--json']),
            (['migrate', 'schema', '--help'], ['automatically on store open']),
            (['init', '--help'], ['--skip-hooks', '--skip-agents', '--non-interactive',
                                '--reinit-local', '--from-jsonl']),
            (['help', 'init-safety'], ['--discard-remote', '--destroy-token', 'history-replacing']),
            (['import', '--help'], ['--dry-run', '--allow-stale', 'upsert', 'tie_kept_local_ids']),
            (['export', '--help'], ['--all', '--output', 'memories', 'not a full database backup']),
            (['list', '--help'], ['--all', '--limit', '--include-infra', '--include-templates',
                                '--include-gates', '--json']),
            (['backup', '--help'], ['sync', 'restore', 'DoltHub']),
            (['bootstrap', '--help'], ['--dry-run', '--json', '--yes', 'validates']),
            (['dolt', 'stop', '--help'], ['graceful', 'restart automatically']),
            (['migrate', 'hooks', '--help'], ['--dry-run', '--apply']),
            (['migrate', 'sync', '--help'], ['--dry-run']),
            (['doctor', '--help'], ['--migration', '--check']),
        ]
        with tempfile.TemporaryDirectory() as directory:
            home, cwd = Path(directory) / 'home', Path(directory) / 'cwd'
            home.mkdir()
            cwd.mkdir()
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('BD_', 'BEADS_', 'GIT_', 'DOLT_'))}
            env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / 'config'))

            def run(arguments):
                result = subprocess.run([BD, *arguments], cwd=cwd, env=env,
                                        capture_output=True, text=True, timeout=15, check=True)
                return result.stdout

            version = run(['--version']).strip()
            self.assertRegex(version, r'^bd version \S+')
            print(f'CLI help only: {version}; no database migration exercised', flush=True)
            for args, markers in commands:
                with self.subTest(command=' '.join(args)):
                    output = run(args)
                    for marker in markers:
                        self.assertIn(marker, output)
            self.assertFalse((cwd / '.beads').exists(), 'help created a database directory')


if __name__ == '__main__':
    unittest.main()
