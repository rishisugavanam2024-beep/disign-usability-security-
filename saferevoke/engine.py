from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from itertools import combinations
from threading import RLock

from saferevoke.adapter import ApplicationAdapter, InMemoryAdapter
from saferevoke.model import AccessEvent, ExecutionContext, Grant, Lab, Policy, WorkflowRun


SEVERITY = {
    "SAFE": 0,
    "UNKNOWN": 1,
    "PARTIAL_REMOVAL": 2,
    "REQUIRED_ACCESS": 3,
    "DELAYED_REMOVAL": 4,
    "UNSAFE_FALLBACK": 5,
}


class SafeRevokeEngine:
    """Execution-based permission mutation and adaptive sequence planner.

    The prototype combines three established testing ideas:
    policy mutation (remove a grant), execution-provenance comparison, and
    adaptive interaction testing (only explore pairs revealed by a changed path).
    """

    def __init__(self, lab: Lab, adapter: ApplicationAdapter | None = None):
        self.lab = lab
        self.adapter = adapter if adapter is not None else InMemoryAdapter(lab)
        self._execution_lock = RLock()

    def _run_all(self, removed: set[str]) -> dict[str, WorkflowRun]:
        runs: dict[str, WorkflowRun] = {}
        with self._execution_lock:
            for workflow in self.lab.workflows.values():
                snapshot = self.adapter.snapshot()
                try:
                    self.adapter.deny(set(removed))
                    run = self.adapter.run(workflow)
                    if run.workflow_id != workflow.id:
                        raise ValueError("Adapter returned the wrong workflow trace")
                    errors = list(run.validation_errors)
                    if workflow.expected_output is not None and run.output != workflow.expected_output:
                        errors.append("Output does not match the approved expected output")
                    for key, expected in workflow.expected_side_effects.items():
                        if key not in run.side_effects or run.side_effects[key] != expected:
                            errors.append(f"Side effect does not match: {key}")
                    run.validation_errors = errors
                    run.success = run.success and not errors
                    runs[workflow.id] = run
                finally:
                    # Cleanup failure propagates: never continue using uncertain state.
                    self.adapter.restore(snapshot)
        return runs

    def _baseline(self) -> dict[str, WorkflowRun]:
        runs = self._run_all(set())
        failed = [key for key, run in runs.items() if not run.success]
        if failed:
            raise ValueError(f"Baseline workflows must pass before testing removals: {failed}")
        return runs

    @staticmethod
    def _used_grants(runs: dict[str, WorkflowRun]) -> set[str]:
        return {
            grant_id
            for run in runs.values()
            for event in run.events
            if event.allowed
            for grant_id in event.grant_ids
        }

    def baseline(self) -> dict:
        """Run and validate all workflows with reset, without removing permissions."""
        return {name: run.to_dict() for name, run in self._baseline().items()}

    @staticmethod
    def _event_paths(run: WorkflowRun) -> set[tuple[str, str, str]]:
        return {
            (event.identity, event.resource, event.action)
            for event in run.events
            if event.allowed
        }

    @staticmethod
    def _semantic_key(event: AccessEvent) -> tuple[str, str, str]:
        """A stable operation identity that tolerates retries and event reordering."""
        return (event.checkpoint, event.resource, event.action)

    def _align_runs(self, before: WorkflowRun, after: WorkflowRun) -> dict:
        """Align successful protected operations by semantic checkpoint and occurrence.

        Denied retries are deliberately excluded from the candidate side. If an
        application retries the same operation with a fallback identity, the
        fallback aligns with the original successful operation.
        """
        before_groups: dict[tuple[str, str, str], list[AccessEvent]] = {}
        after_groups: dict[tuple[str, str, str], list[AccessEvent]] = {}
        for event in before.events:
            if event.allowed:
                before_groups.setdefault(self._semantic_key(event), []).append(event)
        for event in after.events:
            if event.allowed:
                after_groups.setdefault(self._semantic_key(event), []).append(event)

        aligned = []
        consumed_after: set[int] = set()
        for key, baseline_events in before_groups.items():
            mutated_events = after_groups.get(key, [])
            for occurrence, baseline_event in enumerate(baseline_events):
                mutated_event = mutated_events[occurrence] if occurrence < len(mutated_events) else None
                if mutated_event is not None:
                    consumed_after.add(id(mutated_event))
                aligned.append(
                    {
                        "semantic_key": list(key),
                        "occurrence": occurrence,
                        "baseline": baseline_event,
                        "mutated": mutated_event,
                    }
                )

        unmatched_after = [
            event
            for event in after.events
            if event.allowed and id(event) not in consumed_after
        ]
        return {"aligned": aligned, "unmatched_after": unmatched_after}

    def _effective_after(self, grant: Grant, removed: set[str]) -> list[str]:
        if grant.resource == "*" or grant.action == "*":
            return []
        matches = Policy(self.lab, removed).grants_for(
            grant.probe_identity, grant.resource, grant.action
        )
        return [match.id for match in matches]

    def _delayed_event(self, grant: Grant, removed: set[str]) -> AccessEvent | None:
        if grant.id not in self.lab.delayed_grants or grant.id not in removed:
            return None
        return AccessEvent(
            workflow="customer_sync",
            identity=grant.probe_identity,
            resource=grant.resource,
            action=grant.action,
            allowed=True,
            grant_ids=[grant.id],
            checkpoint="customer-sync/preauthorized-write",
            ordinal=999,
            phase="post-revocation",
            note="A job authorized before revocation completed without re-authorization.",
        )

    def _classify(
        self,
        removed: set[str],
        baseline: dict[str, WorkflowRun],
        mutated: dict[str, WorkflowRun],
        focus_grant_id: str,
    ) -> dict:
        grant = self.lab.grants[focus_grant_id]
        baseline_used = focus_grant_id in self._used_grants(baseline)
        effective_after = self._effective_after(grant, removed)
        delayed = self._delayed_event(grant, removed)
        changed_runs = []
        new_paths: list[dict] = []
        fallback_edges: list[dict] = []
        risk_evidence: list[dict] = []
        baseline_policy = Policy(self.lab)
        mutated_policy = Policy(self.lab, removed)

        for workflow_id, before in baseline.items():
            after = mutated[workflow_id]
            if before.success != after.success or before.output != after.output or self._event_paths(before) != self._event_paths(after):
                changed_runs.append(workflow_id)
            before_paths = self._event_paths(before)
            for event in after.events:
                path = (event.identity, event.resource, event.action)
                if event.allowed and path not in before_paths:
                    new_paths.append(event.to_dict())

            alignment = self._align_runs(before, after)
            for pair in alignment["aligned"]:
                original = pair["baseline"]
                alternate = pair["mutated"]
                # Permission inventories/module menus provide selection evidence,
                # not a substitute identity performing a protected operation.
                if original.phase == "dependency":
                    continue
                if alternate is None or focus_grant_id not in original.grant_ids:
                    continue
                changed_principal = original.identity != alternate.identity
                changed_source = set(original.grant_ids) != set(alternate.grant_ids)
                if not (changed_principal or changed_source):
                    continue
                baseline_scope = baseline_policy.scope_metrics(original.identity)
                alternate_scope = mutated_policy.scope_metrics(alternate.identity)
                edge = {
                    "workflow": workflow_id,
                    "checkpoint": original.checkpoint,
                    "from_identity": original.identity,
                    "to_identity": alternate.identity,
                    "from_grant_ids": original.grant_ids,
                    "to_grant_ids": alternate.grant_ids,
                    "resource": original.resource,
                    "action": original.action,
                    "baseline_scope": baseline_scope,
                    "alternate_scope": alternate_scope,
                    "impact_delta": alternate_scope["impact_score"] - baseline_scope["impact_score"],
                }
                fallback_edges.append(edge)
                if edge["impact_delta"] > 0:
                    risk_evidence.append(edge)

        fallback_events = [
            edge for edge in fallback_edges if edge["impact_delta"] > 0
        ]

        failures = [
            workflow_id
            for workflow_id, before in baseline.items()
            if before.success and (
                not mutated[workflow_id].success
                or before.output != mutated[workflow_id].output
                or before.side_effects != mutated[workflow_id].side_effects
            )
        ]

        if fallback_events:
            classification = "UNSAFE_FALLBACK"
            reason = "The workflow still works by switching to a more privileged access path."
        elif delayed:
            classification = "DELAYED_REMOVAL"
            reason = "New access is denied, but work authorized before revocation can still complete."
        elif effective_after:
            classification = "PARTIAL_REMOVAL"
            reason = "The selected grant is gone, but equivalent effective access remains through another grant."
        elif failures:
            classification = "REQUIRED_ACCESS"
            reason = "At least one approved workflow fails after the removal."
        elif not baseline_used:
            classification = "UNKNOWN"
            reason = "No known workflow exercised this grant, so absence of failure is not proof that it is unnecessary."
        else:
            classification = "SAFE"
            reason = "All observed workflows retain their output without an alternative privileged path."

        evidence = fallback_events or ([delayed.to_dict()] if delayed else [])
        return {
            "classification": classification,
            "reason": reason,
            "changed_workflows": changed_runs,
            "failed_workflows": failures,
            "effective_access_remaining_via": effective_after,
            "new_paths": new_paths,
            "fallback_edges": fallback_edges,
            "risk_evidence": risk_evidence,
            "evidence": evidence,
        }

    def _single_experiment(self, grant_id: str, baseline: dict[str, WorkflowRun]) -> dict:
        removed = {grant_id}
        mutated = self._run_all(removed)
        result = self._classify(removed, baseline, mutated, grant_id)
        grant = self.lab.grants[grant_id]
        return {
            "removed": [grant_id],
            "grant": asdict(grant),
            "workflow_runs": {key: run.to_dict() for key, run in mutated.items()},
            **result,
        }

    def _discover_interactions(self, singles: list[dict]) -> list[tuple[str, str, str]]:
        """Select pairs from observed alternate paths rather than testing every pair."""
        discovered: dict[tuple[str, str], str] = {}

        def add_pair(source: str, alternate: str, cause: str) -> None:
            if source == alternate:
                return
            pair = tuple(sorted((source, alternate)))
            existing = discovered.get(pair)
            if existing is None or cause == "runtime-fallback":
                discovered[pair] = cause

        for result in singles:
            source = result["removed"][0]
            for alternate in result["effective_access_remaining_via"]:
                add_pair(source, alternate, "residual-access")
            for edge in result["fallback_edges"]:
                if edge["from_identity"] == edge["to_identity"]:
                    continue
                for alternate in edge["to_grant_ids"]:
                    add_pair(source, alternate, "runtime-fallback")
        return [(first, second, cause) for (first, second), cause in sorted(discovered.items())]

    def _step_result(self, removed: set[str], focus: str, baseline: dict[str, WorkflowRun]) -> dict:
        mutated = self._run_all(removed)
        classified = self._classify(removed, baseline, mutated, focus)
        return {
            "removed_so_far": sorted(removed),
            "classification": classified["classification"],
            "reason": classified["reason"],
        }

    def _sequence_plan(self, first: str, second: str, cause: str, baseline: dict[str, WorkflowRun]) -> dict:
        orders = []
        for order in ((first, second), (second, first)):
            step_one = self._step_result({order[0]}, order[0], baseline)
            step_two = self._step_result(set(order), order[1], baseline)
            max_severity = max(SEVERITY[step_one["classification"]], SEVERITY[step_two["classification"]])
            intermediate_severity = SEVERITY[step_one["classification"]]
            orders.append(
                {
                    "order": list(order),
                    "steps": [step_one, step_two],
                    "score": [max_severity, intermediate_severity],
                }
            )
        orders.sort(key=lambda item: (item["score"][1], item["score"][0]))
        preferred = orders[0]
        final_class = preferred["steps"][-1]["classification"]
        needs_replacement = final_class in {"REQUIRED_ACCESS", "UNSAFE_FALLBACK", "DELAYED_REMOVAL"}
        recommendation = (
            "Provision and validate a least-privilege replacement before the final removal. "
            if needs_replacement
            else "The observed workflows permit this order without a high-risk intermediate state. "
        )
        recommendation += f"Prefer {preferred['order'][0]} before {preferred['order'][1]}."
        return {
            "pair": [first, second],
            "discovered_by": cause,
            "tested_orders": orders,
            "preferred_order": preferred["order"],
            "needs_replacement": needs_replacement,
            "recommendation": recommendation,
        }

    def analyze(self) -> dict:
        baseline = self._baseline()
        singles = [
            self._single_experiment(grant_id, baseline)
            for grant_id in self.lab.grants
        ]
        interactions = self._discover_interactions(singles)
        sequence_plans = [
            self._sequence_plan(first, second, cause, baseline)
            for first, second, cause in interactions
        ]
        counts = Counter(result["classification"] for result in singles)
        all_possible_pairs = len(list(combinations(self.lab.grants, 2)))
        discovered_pairs = {frozenset(plan["pair"]) for plan in sequence_plans}
        expected_pairs = set(self.lab.expected_interactions)
        found_expected = discovered_pairs & expected_pairs
        exhaustive_ordered_tests = all_possible_pairs * 2
        adaptive_total_tests = len(singles) + len(sequence_plans) * 2
        exhaustive_total_tests = len(singles) + exhaustive_ordered_tests
        reduction = (
            1 - adaptive_total_tests / exhaustive_total_tests
            if exhaustive_total_tests
            else 0
        )
        benchmark = {
            "kind": "synthetic planted-interaction benchmark",
            "expected_interactions": [
                {"pair": sorted(pair), "type": self.lab.expected_interactions[pair]}
                for pair in sorted(expected_pairs, key=lambda value: sorted(value))
            ],
            "discovered_interactions": [sorted(pair) for pair in sorted(discovered_pairs, key=lambda value: sorted(value))],
            "expected_found": len(found_expected),
            "expected_total": len(expected_pairs),
            "recall": len(found_expected) / len(expected_pairs) if expected_pairs else None,
            "adaptive_total_experiments": adaptive_total_tests,
            "exhaustive_total_experiments": exhaustive_total_tests,
            "experiment_reduction": reduction,
        }
        return {
            "coverage": self._coverage(baseline, singles),
            "method": {
                "name": "Adaptive Counterfactual Access Testing",
                "description": "Mutate one grant, compare runtime provenance, then test only removal orders exposed by alternate paths.",
                "single_tests": len(singles),
                "adaptive_pairs_discovered": len(sequence_plans),
                "ordered_sequence_tests": len(sequence_plans) * 2,
                "all_possible_pairs": all_possible_pairs,
                "pair_candidates_avoided": max(0, all_possible_pairs - len(sequence_plans)),
            },
            "benchmark": benchmark,
            "summary": dict(counts),
            "baseline": {key: value.to_dict() for key, value in baseline.items()},
            "experiments": singles,
            "sequence_plans": sequence_plans,
            "limitations": [
                "Results apply only to the workflows and states exercised by the lab.",
                "UNKNOWN access requires more workflow coverage or an owner decision.",
                "Production permissions are never modified by this prototype.",
            ],
        }

    def _coverage(self, baseline: dict[str, WorkflowRun], singles: list[dict]) -> dict:
        used = self._used_grants(baseline)
        denied = {item["removed"][0] for item in singles}
        return {
            "configured_grants": len(self.lab.grants),
            "mutation_tested_grants": sorted(denied),
            "baseline_exercised_grants": sorted(used),
            "baseline_unexercised_grants": sorted(set(self.lab.grants) - used),
            "baseline_grant_coverage": len(used) / len(self.lab.grants) if self.lab.grants else 0,
            "executed_workflows": sorted(baseline),
            "owner_checked_workflows": sorted(
                item.id for item in self.lab.workflows.values()
                if item.expected_output is not None or item.expected_side_effects
            ),
            "scope": "Only configured workflows and their exercised branches; this is not full application coverage.",
        }

    def describe_lab(self) -> dict:
        return {
            "grants": [asdict(grant) for grant in self.lab.grants.values()],
            "workflows": [
                {
                    "id": workflow.id,
                    "name": workflow.name,
                    "description": workflow.description,
                }
                for workflow in self.lab.workflows.values()
            ],
        }

    def simulate_grant(self, grant_id: str) -> dict | None:
        """Return a presenter-friendly before/after view for one denied grant."""
        grant = self.lab.grants.get(grant_id)
        if grant is None:
            return None

        baseline = self._baseline()
        mutated = self._run_all({grant_id})
        classified = self._classify({grant_id}, baseline, mutated, grant_id)
        workflows = []
        for workflow_id, workflow in self.lab.workflows.items():
            before = baseline[workflow_id]
            after = mutated[workflow_id]
            used_selected_grant = any(
                event.allowed and grant_id in event.grant_ids
                for event in before.events
            )
            denied_attempt = any(
                not event.allowed
                and event.identity == grant.probe_identity
                and event.resource == grant.resource
                and event.action == grant.action
                for event in after.events
            )
            before_paths = self._event_paths(before)
            after_paths = self._event_paths(after)
            fallback_used = any(
                edge["workflow"] == workflow_id
                and edge["from_identity"] != edge["to_identity"]
                for edge in classified["fallback_edges"]
            )
            source_changed = any(
                edge["workflow"] == workflow_id
                for edge in classified["fallback_edges"]
            )

            if before.success and (not after.success or before.output != after.output or before.side_effects != after.side_effects):
                outcome = "FAILED"
            elif fallback_used:
                outcome = "FALLBACK"
            elif source_changed or (used_selected_grant and classified["effective_access_remaining_via"]):
                outcome = "ACCESS_REMAINS"
            elif before.output != after.output or before_paths != after_paths:
                outcome = "CHANGED"
            else:
                outcome = "UNCHANGED"

            workflows.append(
                {
                    "id": workflow_id,
                    "name": workflow.name,
                    "used_selected_grant": used_selected_grant,
                    "denied_attempt_observed": denied_attempt,
                    "outcome": outcome,
                    "before": before.to_dict(),
                    "after": after.to_dict(),
                }
            )

        return {
            "grant": asdict(grant),
            "classification": classified["classification"],
            "reason": classified["reason"],
            "affected_workflows": [
                item["id"] for item in workflows if item["outcome"] != "UNCHANGED"
            ],
            "workflows": workflows,
        }

    def run_demo_workflow(self, workflow_id: str) -> dict | None:
        workflow = self.lab.workflows.get(workflow_id)
        if not workflow:
            return None
        return self._run_all(set())[workflow_id].to_dict()
