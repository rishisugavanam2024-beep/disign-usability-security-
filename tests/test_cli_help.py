"""Expanded help must be informative without running or changing an application."""
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from saferevoke.__main__ import main


class CommandHelpTests(unittest.TestCase):
    def test_help_all_includes_each_command_and_never_executes_work(self):
        output = StringIO()
        with (redirect_stdout(output),
              patch("saferevoke.__main__.inspect_project") as inspect,
              patch("saferevoke.__main__.write_setup") as setup,
              patch("saferevoke.__main__.subprocess.run") as execute):
            self.assertEqual(main(["--help-all"]), 0)
        for label in ("Detailed help: inspect", "Detailed help: setup", "Detailed help: test",
                      "Detailed help: database", "--max-targets", "--seed", "Django testing uses pytest"):
            self.assertIn(label, output.getvalue())
        inspect.assert_not_called()
        setup.assert_not_called()
        execute.assert_not_called()

    def test_each_subcommand_help_exits_successfully_with_examples(self):
        for name in ("inspect", "setup", "test", "connector", "permissions", "revoke", "grant", "restore", "baseline", "report", "database", "db"):
            with self.subTest(command=name), redirect_stdout(StringIO()) as output:
                with self.assertRaises(SystemExit) as result:
                    main([name, "--help"])
                self.assertEqual(result.exception.code, 0)
                self.assertIn("Examples", output.getvalue())


if __name__ == "__main__":
    unittest.main()
