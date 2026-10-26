"""Run the real pytest and Flask clients in fresh child processes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from textwrap import dedent
import unittest


ROOT = Path(__file__).resolve().parents[1]
AVAILABLE = all(importlib.util.find_spec(name) for name in ("pytest", "flask"))


@unittest.skipUnless(AVAILABLE, "Flask and pytest required")
class FlaskPytestTests(unittest.TestCase):
    def invoke(self, output, *options):
        env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        env.pop("PYTEST_ADDOPTS", None)
        return subprocess.run([
            sys.executable, "-m", "pytest", "-p", "saferevoke.flask_pytest", "-c", str(ROOT / "pyproject.toml"),
            "-q", "--tb=short", "--saferevoke-flask-output", str(output), *options,
        ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)

    def test_existing_tests_unchanged_when_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, "examples/flask_pytest")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("4 passed", result.stdout)
            self.assertFalse((Path(folder) / "report.json").exists())

    def test_real_assertions_and_shared_users_and_fallback_with_verified_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.invoke(folder, "examples/flask_pytest", "--saferevoke-flask",
                                 "--saferevoke-flask-deny", "g_orders", "--saferevoke-flask-deny", "g_refund")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("2 failed, 10 passed", result.stdout)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(report["baseline_failures"], [])
            self.assertEqual(len(report["runs"]), 12)
            self.assertTrue(all(run["state_restored"] for run in report["runs"]))
            self.assertTrue(all(run["teardown"] == "passed" for run in report["runs"]))
            findings = report["findings"]
            self.assertEqual(sum(finding["classification"] == "REQUIRED_ACCESS" for finding in findings), 2)
            fallback = [finding for finding in findings if finding["classification"] == "UNSAFE_FALLBACK"]
            self.assertEqual(len(fallback), 1)
            self.assertEqual(fallback[0]["denied"], "g_refund")
            self.assertTrue((Path(folder) / "report.html").exists())

    def test_uninventoried_and_unexercised_targets_are_not_reported_safe(self):
        for target, expected in (("absent", "NOT_APPLICABLE"), ("g_service", "UNKNOWN")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                result = self.invoke(folder, "examples/flask_pytest", "--saferevoke-flask", "--saferevoke-flask-deny", target)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads((Path(folder) / "report.json").read_text())
                self.assertEqual({finding["classification"] for finding in report["findings"]}, {expected})

    def test_explicit_unique_target_required(self):
        for targets in ([], ["--saferevoke-flask-deny", "g_orders"] * 2):
            with self.subTest(targets=targets), tempfile.TemporaryDirectory() as folder:
                result = self.invoke(folder, "examples/flask_pytest", "--saferevoke-flask", *targets)
                self.assertEqual(result.returncode, 4, result.stdout + result.stderr)

    def write_suite(self, folder, mode):
        path = Path(folder) / "test_lifecycle.py"
        path.write_text(dedent('''
            import pytest
            from flask import Flask
            from saferevoke.adapters.callback import StateHooks
            from saferevoke.adapters.web import record_access
            from saferevoke.flask_testing import FlaskTestIntegration
            from saferevoke.model import Grant
            MODE = MODE_VALUE
            @pytest.fixture
            def state():
                return {'allowed': True, 'writes': []}
            @pytest.fixture
            def saferevoke_flask(state):
                from copy import deepcopy
                app = Flask(__name__)
                app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)
                grant = Grant('g', 'alice', 'identity', 'alice', 'orders', 'read', '')
                def deny(ids):
                    if MODE == 'no_op_deny':
                        return
                    state['allowed'] = False
                    state['writes'].append('partial')
                    if MODE == 'deny_failure':
                        raise RuntimeError('denial failed')
                def restore(snapshot):
                    if MODE == 'restore_failure':
                        raise RuntimeError('restore failed')
                    state.clear()
                    state.update(snapshot)
                return FlaskTestIntegration(app, [grant], StateHooks(lambda: deepcopy(state), deny, restore),
                                            lambda snapshot: state == snapshot and MODE != 'verify_failure')
            @pytest.fixture(autouse=True)
            def cleanup_check(state):
                yield
                if MODE not in ('restore_failure', 'verify_failure'):
                    assert state == {'allowed': True, 'writes': []}
            def test_existing_assertion(state):
                allowed = state['allowed']
                record_access('alice', 'orders', 'read', allowed, ['g'] if allowed else [])
                state['writes'].append('business write')
                if MODE == 'trace_missing':
                    record_access('alice', 'orders', 'read', True)
                assert allowed
        ''').replace("MODE_VALUE", repr(mode)), encoding="utf-8")
        return path

    def test_denial_failure_is_inconclusive_and_still_restores_partial_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_suite(folder, "deny_failure")
            result = self.invoke(folder, str(path), "--saferevoke-flask", "--saferevoke-flask-deny", "g")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(report["findings"][0]["classification"], "INCONCLUSIVE")
            self.assertTrue(all(run["state_restored"] and run["teardown"] == "passed" for run in report["runs"]))

    def test_missing_trace_attribution_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_suite(folder, "trace_missing")
            result = self.invoke(folder, str(path), "--saferevoke-flask", "--saferevoke-flask-deny", "g")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(report["findings"][0]["classification"], "INCONCLUSIVE")
            self.assertTrue(report["baseline_failures"])

    def test_ineffective_removal_is_reported_even_when_all_assertions_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_suite(folder, "no_op_deny")
            result = self.invoke(folder, str(path), "--saferevoke-flask", "--saferevoke-flask-deny", "g")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(report["findings"][0]["classification"], "ACCESS_STILL_OBSERVED")

    def test_cleanup_failure_stops_before_next_variant(self):
        for mode in ("restore_failure", "verify_failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                path = self.write_suite(folder, mode)
                result = self.invoke(folder, str(path), "--saferevoke-flask", "--saferevoke-flask-deny", "g")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads((Path(folder) / "report.json").read_text())
                self.assertTrue(report["cleanup_failed"])
                self.assertEqual(len(report["runs"]), 1)
                self.assertFalse(report["runs"][0]["state_restored"])


if __name__ == "__main__":
    unittest.main()
