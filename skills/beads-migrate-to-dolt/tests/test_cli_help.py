"""Offline parser fixtures; no installed bd or database needed."""

import unittest

from check_cli_help import check_help


class HelpContractTests(unittest.TestCase):
    def test_prose_changes_do_not_hide_declared_capabilities(self):
        check_help('''New wording, independent of the checked version.
Usage:
  bd migrate [flags]
Flags:
      --inspect   New description
Global Flags:
  -C, --directory string   New description
      --sandbox   New description
''', 'bd migrate', ['--inspect', '-C', '--directory', '--sandbox'])

    def test_flag_prefix_is_not_a_flag_match(self):
        with self.assertRaisesRegex(AssertionError, 'missing declared flags: --all'):
            check_help('''Usage:
  bd export [flags]
Flags:
      --allow-stale   Not the requested flag
''', 'bd export', ['--all'])

    def test_prose_and_examples_are_not_flag_definitions(self):
        with self.assertRaisesRegex(AssertionError, 'missing declared flags: --dry-run'):
            check_help('''Modes:
  --dry-run  Historical description
Examples:
  bd import --dry-run
Usage:
  bd import [flags]
Flags:
  -h, --help   Help
''', 'bd import', ['--dry-run'])

    def test_parent_help_is_not_subcommand_help(self):
        with self.assertRaisesRegex(AssertionError, 'did not identify command'):
            check_help('''Example: bd migrate hooks --dry-run
Usage:
  bd migrate [command]
Flags:
      --dry-run   Preview
''', 'bd migrate hooks', ['--dry-run'])

    def test_command_prefix_is_not_a_command_match(self):
        with self.assertRaisesRegex(AssertionError, 'did not identify command'):
            check_help('Usage:\n  bd migrate hooks-extra [flags]\n', 'bd migrate hooks', [])

    def test_unknown_help_topic_is_not_success(self):
        with self.assertRaisesRegex(AssertionError, 'did not identify command'):
            check_help('Unknown help topic: init-safety\n', 'bd init-safety', [])


if __name__ == '__main__':
    unittest.main()
