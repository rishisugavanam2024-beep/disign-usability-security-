"""Executable boundary checks; do not start servers or touch a database."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
JAVA = Path(os.environ.get('DIBSLY_TEST_JAVA', r'C:\Program Files\Java\jdk-21.0.11\bin\java.exe'))
CLASSES = ROOT / '.local/python-connector/classes'
COMMAND = [str(JAVA), '-cp', os.pathsep.join((str(CLASSES), str(ROOT / 'target/dibsly-1.0.0.jar'))), 'DibslyWorkflow']


class ConnectorGuards(unittest.TestCase):
    def call(self, arguments, enabled):
        env = dict(os.environ)
        env.pop('DIBSLY_CONNECTOR_TEST', None)
        if enabled:
            env['DIBSLY_CONNECTOR_TEST'] = 'true'
        return subprocess.run([*COMMAND, *arguments], env=env, capture_output=True, text=True, timeout=15)

    def test_explicit_opt_in_required(self):
        result = self.call(['publish_project'], False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Explicit connector test opt-in required', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_unknown_workflow_rejected(self):
        result = self.call(['arbitrary_workflow'], True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unknown workflow', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_unknown_permission_rejected(self):
        result = self.call(['publish_project', 'not_in_inventory'], True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unknown grant', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
