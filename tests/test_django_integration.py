"""Optional real-framework integration checks, isolated from other Django settings."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("django"), "Install requirements-django.txt to run")
class DjangoIntegrationTests(unittest.TestCase):
    def test_upstream_admin_real_permissions_and_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                [sys.executable, "-m", "examples.django_admin.run", "--output", folder],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((Path(folder) / "evidence.json").read_text(encoding="utf-8"))
            examples = result["demonstrations"]
            shared = examples["shared_group_permission"]
            self.assertEqual({item["id"] for item in shared["workflows"] if item["outcome"] == "FAILED"},
                             {"alice_list_users", "bob_list_users"})
            group_page = next(item for item in shared["workflows"] if item["id"] == "alice_list_groups")
            self.assertTrue(group_page["after"]["success"])
            self.assertEqual(group_page["outcome"], "CHANGED")
            for workflow in examples["shared_group_permission"]["workflows"]:
                if workflow["id"] in {"alice_list_users", "bob_list_users"}:
                    self.assertEqual(workflow["after"]["output"], "HTTP:403")
            self.assertEqual(examples["duplicate_direct_permission"]["classification"], "PARTIAL_REMOVAL")
            self.assertEqual(examples["required_write_permission"]["classification"], "REQUIRED_ACCESS")
            self.assertTrue(result["permissions_restored"])
            self.assertTrue(result["workflow_writes_rolled_back"])
            events = [event for run in result["analysis"]["baseline"].values() for event in run["events"]]
            self.assertTrue(events)
            self.assertTrue(any(event["grant_ids"] for event in events))
            self.assertTrue(all("Django ModelBackend" in event["note"] for event in events))
            self.assertTrue((Path(folder) / "report.html").exists())

    def test_database_is_restored_after_real_workflow_exception(self):
        code = """
from examples.django_admin.run import setup, build_integration
setup()
engine = build_integration()
from django.contrib.auth import get_user_model
from saferevoke.model import Workflow
from saferevoke.engine import SafeRevokeEngine
User = get_user_model()
original = User.objects.get(username='alice').first_name
def crash(ctx):
    User.objects.filter(username='alice').update(first_name='unexpected mutation')
    raise RuntimeError('forced workflow exception')
lab = engine.lab
original_workflows = lab.workflows
lab.workflows = {'crash': Workflow('crash', 'Crash test', '', crash)}
runner = SafeRevokeEngine(lab, engine.adapter)
try:
    runner._run_all({next(iter(lab.grants))})
except RuntimeError as error:
    assert str(error) == 'forced workflow exception'
else:
    raise AssertionError('Exception was hidden')
assert User.objects.get(username='alice').first_name == original
assert engine.adapter.removed == set()
lab.workflows = original_workflows
assert all(run.success for run in engine._baseline().values())
from django.test import override_settings
from saferevoke.adapters.django import DjangoAdapter
with override_settings(SAFEREVOKE_TEST_ENVIRONMENT=False):
    try:
        DjangoAdapter(lab, engine.adapter.bindings)
    except ValueError:
        pass
    else:
        raise AssertionError('Missing test-environment guard')
print('Django database rollback and environment guard: OK')
"""
        process = subprocess.run([sys.executable, "-c", code],
                                 cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=90)
        self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
