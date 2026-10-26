"""Discovery must not execute source; resets and automatic runs use real stores."""
from copy import deepcopy
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from saferevoke.adapters.sqlite import SQLiteTestState
from saferevoke.flask_testing import FlaskTestIntegration
from saferevoke.model import Grant
from saferevoke.setup_assistant import inspect_project, setup_plan, write_setup


ROOT = Path(__file__).resolve().parents[1]


class DiscoveryTests(unittest.TestCase):
    def make_project(self, folder):
        root = Path(folder)
        (root / "app.py").write_text("from flask import Flask\nfrom saferevoke.model import Grant as G\n"
            "raise RuntimeError('must never import this app')\n"
            "GRANTS = [G('read', 'alice', 'identity', 'alice', 'orders', 'read', 'Read orders')]\n", encoding="utf-8")
        (root / "conftest.py").write_text("from pytest import fixture as f\n@f\ndef saferevoke_flask():\n    raise RuntimeError('not executed')\n", encoding="utf-8")
        (root / "test_orders.py").write_text("def test_orders():\n    pass\n", encoding="utf-8")
        return root

    def test_static_scan_does_not_import_app_and_finds_aliases_and_literal_grants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            report = inspect_project(root)
            self.assertEqual(report["frameworks"], ["flask"])
            self.assertEqual(report["fixtures"][0]["name"], "saferevoke_flask")
            self.assertEqual(report["grants"][0]["grant"]["id"], "read")
            plan = setup_plan(report)
            self.assertEqual(plan["status"], "configuration_detected")
            self.assertFalse(plan["runtime_verified"])

    def test_env_and_dependency_folders_are_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            (root / ".env.py").write_text("from django import secret\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "hidden.py").write_text("import fastapi\n", encoding="utf-8")
            report = inspect_project(root)
            self.assertEqual(report["frameworks"], ["flask"])
            self.assertEqual(report["files_scanned"], 3)

    def test_sibling_fixture_is_not_mistaken_for_project_wide_wiring(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            (root / "conftest.py").unlink()
            (root / "unrelated").mkdir()
            (root / "unrelated" / "conftest.py").write_text("import pytest\n@pytest.fixture\ndef saferevoke_flask(): pass\n", encoding="utf-8")
            self.assertTrue(any("Connect a saferevoke_flask fixture" in item for item in setup_plan(inspect_project(root))["blockers"]))

    def test_dynamic_and_conflicting_grants_are_not_used_as_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            (root / "other.py").write_text("from saferevoke.model import Grant\n"
                "Grant('read', 'bob', 'identity', 'bob', 'orders', 'read', 'Different principal')\n"
                "Grant(variable, 'bob', 'identity', 'bob', 'orders', 'read', '')\n", encoding="utf-8")
            report = inspect_project(root)
            self.assertEqual(report["grants"], [])
            self.assertTrue(any("Conflicting" in item for item in report["warnings"]))
            self.assertTrue(any("Dynamic" in item for item in report["warnings"]))

    def test_generation_never_overwrites_existing_files_or_modifies_conftest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            original = (root / "conftest.py").read_bytes()
            destination, plan = write_setup(root)
            self.assertTrue((destination / "plan.json").exists())
            self.assertEqual((root / "conftest.py").read_bytes(), original)
            marker = destination / "README.txt"
            marker.write_text("my edited instructions", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_setup(root)
            self.assertEqual(marker.read_text(), "my edited instructions")

    def test_ambiguous_framework_and_truncated_scan_require_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_project(folder)
            (root / "other.py").write_text("import django\n", encoding="utf-8")
            self.assertIsNone(setup_plan(inspect_project(root))["framework"])
            report = inspect_project(root, max_files=1)
            self.assertFalse(report["scan_complete"])
            self.assertTrue(setup_plan(report, "flask")["blockers"])


class RegisteredStoreTests(unittest.TestCase):
    def test_inventory_and_role_hooks_are_wired_from_explicitly_registered_store(self):
        state = {"permission": True, "writes": []}
        grant = Grant("read", "staff", "role", "alice", "orders", "read", "Read orders")

        class Store:
            def inventory(self):
                return [grant]
            def user_roles(self):
                return {"alice": {"staff"}}
            def snapshot(self):
                return deepcopy(state)
            def remove_grants(self, ids):
                state["permission"] = False
                state["writes"].append("business effect")
            def restore(self, snapshot):
                state.clear()
                state.update(snapshot)
            def matches_snapshot(self, snapshot):
                return state == snapshot

        app = SimpleNamespace(config={"TESTING": True, "SAFEREVOKE_TEST_ENVIRONMENT": True}, extensions={"saferevoke": Store()})
        integration = FlaskTestIntegration.from_registered_store(app)
        self.assertEqual(integration.lab.roles, {"alice": {"staff"}})
        self.assertEqual(set(integration.lab.grants), {"read"})
        snapshot = integration.hooks.snapshot()
        integration.hooks.deny({"read"})
        self.assertFalse(state["permission"])
        integration.hooks.restore(snapshot)
        self.assertTrue(integration.verify_restored(snapshot))

    def test_non_test_app_does_not_even_read_registered_inventory(self):
        calls = []
        store = SimpleNamespace(inventory=lambda: calls.append("read"))
        app = SimpleNamespace(config={}, extensions={"saferevoke": store})
        with self.assertRaises(ValueError):
            FlaskTestIntegration.from_registered_store(app)
        self.assertEqual(calls, [])


class SQLiteResetTests(unittest.TestCase):
    def create_database(self, folder):
        path = Path(folder) / "isolated.db"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE permissions (id TEXT PRIMARY KEY)")
            connection.execute("INSERT INTO permissions VALUES ('read')")
            connection.execute("CREATE TABLE refunds (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            connection.commit()
        return path

    def test_permissions_business_writes_and_schema_changes_restore_together(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.create_database(folder)

            def deny(ids):
                with closing(sqlite3.connect(path)) as connection:
                    connection.executemany("DELETE FROM permissions WHERE id = ?", [(item,) for item in ids])
                    connection.execute("INSERT INTO refunds DEFAULT VALUES")
                    connection.execute("CREATE TABLE unexpected (value TEXT)")
                    connection.commit()

            state = SQLiteTestState(path, test_root=folder, remove_grants=deny, test_environment=True)
            snapshot = state.snapshot()
            state.hooks.deny({"read"})
            self.assertFalse(state.matches_snapshot(snapshot))
            state.restore(snapshot)
            self.assertTrue(snapshot.closed)
            self.assertTrue(state.matches_snapshot(snapshot))
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT id FROM permissions").fetchall(), [("read",)])
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name='unexpected'").fetchall(), [])

    def test_outside_root_and_missing_optin_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.create_database(folder)
            subroot = Path(folder) / "other"
            subroot.mkdir()
            for test_root, enabled in ((subroot, True), (folder, False)):
                with self.assertRaises(ValueError):
                    SQLiteTestState(path, test_root=test_root, remove_grants=lambda ids: None, test_environment=enabled)

    def test_large_database_refused_and_snapshots_cannot_cross_database_helpers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.create_database(folder)
            small = SQLiteTestState(path, test_root=folder, remove_grants=lambda ids: None,
                                    test_environment=True, max_database_bytes=1)
            with self.assertRaisesRegex(ValueError, "size limit"):
                small.snapshot()
            first = SQLiteTestState(path, test_root=folder, remove_grants=lambda ids: None, test_environment=True)
            second = SQLiteTestState(path, test_root=folder, remove_grants=lambda ids: None, test_environment=True)
            snapshot = first.snapshot()
            try:
                with self.assertRaises(ValueError):
                    second.restore(snapshot)
            finally:
                snapshot.close()


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ("pytest", "flask")), "Flask and pytest required")
class AutomaticRunTests(unittest.TestCase):
    def invoke(self, folder, *options):
        env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
        env.pop("PYTEST_ADDOPTS", None)
        return subprocess.run([sys.executable, "-m", "saferevoke", "test", folder, *options],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)

    def copy_example(self, folder):
        for filename in ("app.py", "conftest.py", "test_business.py"):
            shutil.copyfile(ROOT / "examples" / "flask_pytest" / filename, Path(folder) / filename)

    def summary(self, folder):
        paths = list((Path(folder) / "reports" / "saferevoke-auto").glob("*/summary.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def test_real_test_inventory_selects_observed_permissions_without_typed_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            self.copy_example(folder)
            result = self.invoke(folder)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            summary = self.summary(folder)
            self.assertEqual(summary["selected_grant_ids"], ["g_orders", "g_refund"])
            self.assertEqual(summary["unexercised_grant_ids"], ["g_service"])
            self.assertEqual(summary["findings_summary"]["REQUIRED_ACCESS"], 2)
            self.assertEqual(summary["findings_summary"]["UNSAFE_FALLBACK"], 1)
            self.assertEqual(summary["status"], "removal_test_run_completed")

    def test_target_limit_prevents_removal_run(self):
        with tempfile.TemporaryDirectory() as folder:
            self.copy_example(folder)
            result = self.invoke(folder, "--max-targets", "1")
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            summary = self.summary(folder)
            self.assertEqual(summary["status"], "target_limit_exceeded_no_removals_attempted")
            self.assertFalse((Path(summary["output"]) / "removals").exists())

    def test_failed_baseline_never_proceeds_to_permission_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            self.copy_example(folder)
            (Path(folder) / "test_business.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
            result = self.invoke(folder)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            summary = self.summary(folder)
            self.assertEqual(summary["status"], "baseline_failed_no_removals_attempted")
            self.assertFalse((Path(summary["output"]) / "removals").exists())


if __name__ == "__main__":
    unittest.main()
