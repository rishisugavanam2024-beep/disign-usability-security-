from __future__ import annotations

from saferevoke.benchmark_labs import build_incident_lab, build_publishing_lab
from saferevoke.engine import SafeRevokeEngine
from saferevoke.lab import build_lab
from saferevoke.model import Lab, Policy


LAB_BUILDERS = (
    ("company_portal", "Company portal", build_lab),
    ("incident_console", "Incident-response console", build_incident_lab),
    ("publishing_service", "Document-publishing service", build_publishing_lab),
)


def policy_only_replay(lab: Lab) -> set[frozenset[str]]:
    """Replay baseline requests after one grant removal, without rerunning app logic.

    This control can see an alternate grant for the same identity and request. It
    cannot see a fallback identity that the application chooses only after a
    denial, because that request is absent from the baseline trace.
    """
    engine = SafeRevokeEngine(lab)
    baseline = engine._run_all(set())
    discovered: set[frozenset[str]] = set()
    for removed_id in lab.grants:
        policy = Policy(lab, {removed_id})
        for run in baseline.values():
            for event in run.events:
                if not event.allowed or removed_id not in event.grant_ids:
                    continue
                alternates = policy.grants_for(
                    event.identity, event.resource, event.action
                )
                for alternate in alternates:
                    if alternate.id != removed_id:
                        discovered.add(frozenset((removed_id, alternate.id)))
    return discovered


def run_comparative_benchmark() -> dict:
    applications = []
    expected_all: set[tuple[str, frozenset[str]]] = set()
    adaptive_found_all: set[tuple[str, frozenset[str]]] = set()
    policy_found_all: set[tuple[str, frozenset[str]]] = set()
    adaptive_experiments = 0
    exhaustive_experiments = 0

    for app_id, name, builder in LAB_BUILDERS:
        lab = builder()
        report = SafeRevokeEngine(lab).analyze()
        adaptive_pairs = {
            frozenset(plan["pair"]) for plan in report["sequence_plans"]
        }
        policy_pairs = policy_only_replay(lab)
        expected_pairs = set(lab.expected_interactions)
        expected_all.update((app_id, pair) for pair in expected_pairs)
        adaptive_found_all.update((app_id, pair) for pair in adaptive_pairs)
        policy_found_all.update((app_id, pair) for pair in policy_pairs)
        adaptive_experiments += report["benchmark"]["adaptive_total_experiments"]
        exhaustive_experiments += report["benchmark"]["exhaustive_total_experiments"]
        applications.append(
            {
                "id": app_id,
                "name": name,
                "grant_count": len(lab.grants),
                "workflow_count": len(lab.workflows),
                "expected_interactions": len(expected_pairs),
                "saferevoke_found": len(adaptive_pairs & expected_pairs),
                "policy_replay_found": len(policy_pairs & expected_pairs),
            }
        )

    runtime_expected = {
        (app_id, pair)
        for app_id, _, builder in LAB_BUILDERS
        for pair, interaction_type in builder().expected_interactions.items()
        if interaction_type == "runtime-fallback"
    }
    adaptive_matches = expected_all & adaptive_found_all
    policy_matches = expected_all & policy_found_all
    return {
        "kind": "multi-application synthetic comparative benchmark",
        "warning": "These are controlled synthetic applications with planted interactions, not production performance results.",
        "applications": applications,
        "expected_total": len(expected_all),
        "saferevoke": {
            "found": len(adaptive_matches),
            "recall": len(adaptive_matches) / len(expected_all) if expected_all else 1.0,
            "runtime_fallback_recall": len(runtime_expected & adaptive_found_all) / len(runtime_expected) if runtime_expected else 1.0,
        },
        "policy_only_replay": {
            "found": len(policy_matches),
            "recall": len(policy_matches) / len(expected_all) if expected_all else 1.0,
            "runtime_fallback_recall": len(runtime_expected & policy_found_all) / len(runtime_expected) if runtime_expected else 1.0,
        },
        "adaptive_total_experiments": adaptive_experiments,
        "exhaustive_total_experiments": exhaustive_experiments,
        "experiment_reduction": (
            1 - adaptive_experiments / exhaustive_experiments
            if exhaustive_experiments else 0
        ),
    }
