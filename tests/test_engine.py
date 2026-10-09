import unittest

from saferevoke.benchmark import run_comparative_benchmark
from saferevoke.engine import SafeRevokeEngine
from saferevoke.lab import build_lab
from saferevoke.model import AccessEvent, WorkflowRun


class SafeRevokeEngineTests(unittest.TestCase):
    def setUp(self):
        self.report = SafeRevokeEngine(build_lab()).analyze()
        self.by_grant = {
            item["grant"]["id"]: item for item in self.report["experiments"]
        }

    def test_detects_privileged_fallback(self):
        self.assertEqual(
            self.by_grant["g_report_read"]["classification"],
            "UNSAFE_FALLBACK",
        )
        risk = self.by_grant["g_report_read"]["risk_evidence"][0]
        self.assertGreater(
            risk["alternate_scope"]["impact_score"],
            risk["baseline_scope"]["impact_score"],
        )
        self.assertNotIn("risk", self.by_grant["g_report_read"]["grant"])

    def test_detects_inherited_residual_access(self):
        self.assertEqual(
            self.by_grant["g_audit_direct"]["classification"],
            "PARTIAL_REMOVAL",
        )
        self.assertIn(
            "g_audit_role",
            self.by_grant["g_audit_direct"]["effective_access_remaining_via"],
        )

    def test_detects_required_and_delayed_access(self):
        self.assertEqual(
            self.by_grant["g_invoice_read"]["classification"],
            "REQUIRED_ACCESS",
        )
        self.assertEqual(
            self.by_grant["g_sync_write"]["classification"],
            "DELAYED_REMOVAL",
        )

    def test_does_not_call_unused_access_safe(self):
        self.assertEqual(
            self.by_grant["g_unused_archive"]["classification"],
            "UNKNOWN",
        )

    def test_detects_safe_observed_removal(self):
        self.assertEqual(
            self.by_grant["g_optional_metrics"]["classification"],
            "SAFE",
        )

    def test_adaptive_planner_finds_runtime_pair(self):
        pairs = {tuple(plan["pair"]): plan for plan in self.report["sequence_plans"]}
        self.assertIn(tuple(sorted(("g_report_read", "g_admin_all"))), pairs)
        self.assertEqual(len(pairs), len(self.report["sequence_plans"]))
        self.assertEqual(
            pairs[tuple(sorted(("g_report_read", "g_admin_all")))]["discovered_by"],
            "runtime-fallback",
        )
        self.assertEqual(
            pairs[tuple(sorted(("g_audit_direct", "g_audit_role")))]["discovered_by"],
            "residual-access",
        )

    def test_semantic_alignment_ignores_denied_retry_and_reordering(self):
        engine = SafeRevokeEngine(build_lab())
        baseline = WorkflowRun(
            "demo",
            True,
            "ok",
            [
                AccessEvent("demo", "reader", "sales_db", "read", True, ["a"], "read-sales", 0),
                AccessEvent("demo", "writer", "export_store", "write", True, ["b"], "write-export", 1),
            ],
            "ok",
        )
        mutated = WorkflowRun(
            "demo",
            True,
            "ok",
            [
                AccessEvent("demo", "writer", "export_store", "write", True, ["b"], "write-export", 0),
                AccessEvent("demo", "reader", "sales_db", "read", False, [], "read-sales", 1),
                AccessEvent("demo", "admin", "sales_db", "read", True, ["admin"], "read-sales", 2),
            ],
            "ok",
        )
        aligned = engine._align_runs(baseline, mutated)["aligned"]
        by_checkpoint = {pair["baseline"].checkpoint: pair for pair in aligned}
        self.assertEqual(by_checkpoint["read-sales"]["mutated"].identity, "admin")
        self.assertEqual(by_checkpoint["write-export"]["mutated"].identity, "writer")

    def test_synthetic_benchmark_matches_exhaustive_oracle(self):
        benchmark = self.report["benchmark"]
        self.assertEqual(benchmark["recall"], 1.0)
        self.assertGreater(benchmark["experiment_reduction"], 0.75)
        self.assertLess(
            benchmark["adaptive_total_experiments"],
            benchmark["exhaustive_total_experiments"],
        )

    def test_comparative_benchmark_uses_three_independent_apps(self):
        comparison = run_comparative_benchmark()
        self.assertEqual(len(comparison["applications"]), 3)
        self.assertEqual(comparison["expected_total"], 5)

    def test_runtime_execution_outperforms_policy_only_replay(self):
        comparison = run_comparative_benchmark()
        self.assertEqual(comparison["saferevoke"]["recall"], 1.0)
        self.assertEqual(
            comparison["saferevoke"]["runtime_fallback_recall"], 1.0
        )
        self.assertLess(comparison["policy_only_replay"]["recall"], 1.0)
        self.assertEqual(
            comparison["policy_only_replay"]["runtime_fallback_recall"], 0.0
        )

    def test_comparative_adaptive_testing_reduces_experiments(self):
        comparison = run_comparative_benchmark()
        self.assertLess(
            comparison["adaptive_total_experiments"],
            comparison["exhaustive_total_experiments"],
        )

    def test_single_permission_simulation_shows_before_and_after(self):
        simulation = SafeRevokeEngine(build_lab()).simulate_grant("g_report_read")
        self.assertIsNotNone(simulation)
        self.assertEqual(simulation["classification"], "UNSAFE_FALLBACK")
        sales = next(
            workflow
            for workflow in simulation["workflows"]
            if workflow["id"] == "sales_report"
        )
        self.assertEqual(sales["outcome"], "FALLBACK")
        self.assertTrue(sales["denied_attempt_observed"])
        self.assertEqual(sales["before"]["events"][0]["identity"], "report_user")
        self.assertEqual(sales["after"]["events"][-1]["identity"], "legacy_admin")


if __name__ == "__main__":
    unittest.main()
