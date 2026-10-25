import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from saferevoke.adapter import InMemoryAdapter
from saferevoke.config import load_lab
from saferevoke.engine import SafeRevokeEngine
from saferevoke.lab import build_lab
from saferevoke.model import WorkflowRun
from saferevoke.report import render_html, render_json
from saferevoke.shared_example import RUNNERS


CONFIG = Path(__file__).resolve().parents[1] / "examples" / "shared_access.json"


class FoundationTests(unittest.TestCase):
    def test_shared_role_affects_two_identities_and_preserves_order_task(self):
        lab = load_lab(CONFIG, RUNNERS)
        result = SafeRevokeEngine(lab).simulate_grant("g_inventory_read")
        outcomes = {item["id"]: item["outcome"] for item in result["workflows"]}
        self.assertEqual(outcomes, {"check_stock": "FAILED", "shipping_quote": "FAILED", "save_order": "UNCHANGED"})

    def test_state_and_permissions_restored_across_repeated_analysis(self):
        lab = load_lab(CONFIG, RUNNERS)
        adapter = InMemoryAdapter(lab, {"orders": []})
        engine = SafeRevokeEngine(lab, adapter)
        first = engine.analyze()
        second = engine.analyze()
        self.assertEqual(first, second)
        self.assertEqual(adapter.state, {"orders": []})
        self.assertEqual(adapter.removed, set())

    def test_cleanup_runs_on_workflow_exception(self):
        lab = load_lab(CONFIG, RUNNERS)
        def crash(ctx):
            ctx.state["orders"].append("unexpected")
            raise RuntimeError("application crashed")
        lab.workflows = {"crash": replace(lab.workflows["save_order"], id="crash", runner=crash)}
        adapter = InMemoryAdapter(lab, {"orders": []})
        with self.assertRaisesRegex(RuntimeError, "application crashed"):
            SafeRevokeEngine(lab, adapter)._run_all({"g_order_write"})
        self.assertEqual(adapter.state, {"orders": []})
        self.assertEqual(adapter.removed, set())

    def test_successful_but_wrong_output_is_required_access(self):
        lab = build_lab()
        def corrupt(ctx):
            allowed = ctx.access("dashboard_user", "metrics_store", "read")
            return WorkflowRun(ctx.workflow_id, True, "correct" if allowed else "corrupted", ctx.events, "ok")
        lab.workflows["operations_dashboard"] = replace(lab.workflows["operations_dashboard"], runner=corrupt)
        result = SafeRevokeEngine(lab).simulate_grant("g_optional_metrics")
        self.assertEqual(result["classification"], "REQUIRED_ACCESS")

    def test_invalid_baseline_is_rejected_for_wrong_side_effect(self):
        lab = load_lab(CONFIG, RUNNERS)
        lab.workflows["save_order"] = replace(lab.workflows["save_order"], expected_side_effects={"orders_created": 99})
        with self.assertRaisesRegex(ValueError, "Baseline workflows must pass"):
            SafeRevokeEngine(lab).analyze()

    def test_changed_side_effect_is_detected_even_without_explicit_expectations(self):
        lab = build_lab()
        def wrong_effect(ctx):
            allowed = ctx.access("dashboard_user", "metrics_store", "read")
            return WorkflowRun(ctx.workflow_id, True, "ok", ctx.events, "ok",
                               side_effects={"records_written": 1 if allowed else 2})
        lab.workflows["operations_dashboard"] = replace(lab.workflows["operations_dashboard"], runner=wrong_effect)
        report = SafeRevokeEngine(lab).simulate_grant("g_optional_metrics")
        self.assertEqual(report["classification"], "REQUIRED_ACCESS")

    def test_permission_apply_failure_restores_partial_changes(self):
        lab = load_lab(CONFIG, RUNNERS)
        class BrokenDeny(InMemoryAdapter):
            def deny(self, grant_ids):
                super().deny(grant_ids)
                self.state["orders"].append("partial-change")
                raise RuntimeError("deny failed")
        adapter = BrokenDeny(lab, {"orders": []})
        with self.assertRaisesRegex(RuntimeError, "deny failed"):
            SafeRevokeEngine(lab, adapter)._run_all({"g_order_write"})
        self.assertEqual(adapter.state, {"orders": []})
        self.assertEqual(adapter.removed, set())

    def test_restore_failure_stops_further_workflows(self):
        lab = load_lab(CONFIG, RUNNERS)
        class BrokenRestore(InMemoryAdapter):
            calls = 0
            def run(self, workflow):
                self.calls += 1
                return super().run(workflow)
            def restore(self, snapshot):
                raise RuntimeError("restore failed")
        adapter = BrokenRestore(lab)
        with self.assertRaisesRegex(RuntimeError, "restore failed"):
            SafeRevokeEngine(lab, adapter).analyze()
        self.assertEqual(adapter.calls, 1)

    def test_unknown_runner_and_duplicate_grants_rejected(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            load_lab(CONFIG, {})
        data = json.loads(CONFIG.read_text())
        data["grants"].append(data["grants"][0])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "unique"):
                load_lab(path, RUNNERS)

    def test_coverage_distinguishes_mutation_tests_from_observed_use(self):
        report = SafeRevokeEngine(load_lab(CONFIG, RUNNERS)).analyze()
        coverage = report["coverage"]
        self.assertEqual(len(coverage["mutation_tested_grants"]), 3)
        self.assertEqual(coverage["baseline_unexercised_grants"], ["g_old_export"])
        self.assertEqual(len(coverage["owner_checked_workflows"]), 3)
        self.assertEqual(json.loads(render_json(report))["coverage"], coverage)
        report["experiments"][0]["grant"]["description"] = "<script>alert(1)</script>"
        self.assertNotIn("<script>", render_html(report))


if __name__ == "__main__":
    unittest.main()
