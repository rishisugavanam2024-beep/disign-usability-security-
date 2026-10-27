"""Native CLI must run the real engine, preserve cleanup, and fail closed on config errors."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from saferevoke.__main__ import main
from saferevoke.external import configuration, analyze, latest_report, control, describe


CONNECTOR = '''
from saferevoke.external import ExternalAnalysis
from saferevoke.adapter import InMemoryAdapter
from saferevoke.model import Lab, Grant, Workflow, WorkflowRun, AccessEvent

def create_analysis(root, output, options):
    grant = Grant('write', 'alice', 'identity', 'alice', 'items', 'write', 'Write items')
    def work(ctx):
        allowed = bool(ctx.policy.grants_for('alice', 'items', 'write'))
        return WorkflowRun('save', allowed, 'saved' if allowed else 'denied',
            [AccessEvent('save', 'alice', 'items', 'write', allowed, ['write'] if allowed else [])], '',
            {'writes': 1 if allowed else 0})
    workflow = Workflow('save', 'Save', '', work, 'saved', {'writes': 1})
    lab = Lab({'write': grant}, {}, {'save': workflow}, set(), {('items', 'write')}, {'write': 1}, {})
    def close():
        (root / 'closed').write_text('yes')
        if options.get('fail_close'): raise RuntimeError('cleanup failed')
    return ExternalAnalysis(lab, InMemoryAdapter(lab), lambda: {'real_engine': True}, close)

def control(action, subject, permission, root, options):
    value = {'action': action, 'subject': subject, 'permission': permission}
    (root / 'control.json').write_text(__import__('json').dumps(value))
    return value
'''


class ExternalCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'connector.py').write_text(CONNECTOR, encoding='utf-8')
        self.path = self.root / 'saferevoke.json'
        self.data = {'schema_version': 1, 'name': 'test app', 'test_environment': True, 'module': 'connector.py'}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def test_all_commands_visible_without_loading_application(self):
        (self.root / 'connector.py').write_text("raise AssertionError('must not import')")
        with redirect_stdout(StringIO()) as output, self.assertRaises(SystemExit) as result:
            main(['--help'])
        self.assertEqual(result.exception.code, 0)
        for name in ('inspect', 'setup', 'test', 'connector', 'permissions', 'revoke', 'grant', 'restore', 'baseline', 'report', 'database', 'db'):
            self.assertIn(name, output.getvalue())
        self.assertFalse(describe(configuration(self.path))['module_executed'])

    def test_external_test_runs_engine_generates_report_and_cleans_up(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['test', '--connector', str(self.path)]), 0)
        self.assertTrue((self.root / 'closed').exists())
        paths = latest_report(configuration(self.path))
        report = json.loads(Path(paths['json']).read_text())
        self.assertEqual(report['experiments'][0]['classification'], 'REQUIRED_ACCESS')
        self.assertTrue(report['integration']['evidence']['real_engine'])
        self.assertIn('REQUIRED_ACCESS', Path(paths['html']).read_text())

    def test_controls_forward_literal_identifiers_and_restore_alias(self):
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['grant', 'alice; echo bad', 'WRITE', '--connector', str(self.path)]), 0)
        record = json.loads((self.root / 'control.json').read_text())
        self.assertEqual(record, {'action': 'restore', 'subject': 'alice; echo bad', 'permission': 'WRITE'})

    def test_baseline_does_not_publish_analysis_or_remove_permissions(self):
        with redirect_stdout(StringIO()):
            report = analyze(configuration(self.path), baseline_only=True)
        self.assertTrue(report['baseline']['save']['success'])
        with self.assertRaisesRegex(ValueError, 'No completed'):
            latest_report(configuration(self.path))

    def test_cleanup_failure_does_not_publish_completed_report(self):
        self.data['options'] = {'fail_close': True}; self.save()
        with redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            analyze(configuration(self.path))
        self.assertFalse(list(self.root.glob('reports/**/complete.json')))

    def test_opt_in_is_required_before_import_and_mutation(self):
        self.data['test_environment'] = False; self.save()
        (self.root / 'connector.py').write_text("raise AssertionError('must not import')")
        with self.assertRaisesRegex(ValueError, 'test_environment'):
            control(configuration(self.path), 'revoke', 'alice', 'WRITE')

    def test_paths_cannot_escape_and_invalid_config_does_not_fall_back(self):
        for value in ('../elsewhere.py', str(self.root / 'connector.py')):
            self.data['module'] = value; self.save()
            with self.assertRaises(ValueError): configuration(self.path)
        with patch('saferevoke.auto_testing.run_auto_tests') as fallback, redirect_stdout(StringIO()):
            self.assertEqual(main(['test', '--connector', str(self.path)]), 2)
            fallback.assert_not_called()

    def test_grant_limit_cleans_up_without_running_workflows(self):
        self.data['options'] = {}; self.save()
        with self.assertRaisesRegex(ValueError, 'positive'):
            analyze(configuration(self.path), max_targets=0)
        self.assertFalse((self.root / 'closed').exists())

    def test_report_does_not_import_connector(self):
        with redirect_stdout(StringIO()): analyze(configuration(self.path))
        (self.root / 'connector.py').write_text("raise AssertionError('must not import')")
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['report', '--connector', str(self.path)]), 0)


if __name__ == '__main__': unittest.main()
