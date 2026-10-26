"""Discover runtime test permissions, then reuse the Flask pytest integration."""
from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from saferevoke.setup_assistant import inspect_project, setup_plan


def run_auto_tests(project, *, framework=None, max_targets=10, timeout=120):
    if max_targets <= 0 or timeout <= 0:
        raise ValueError("Positive target and subprocess timeout limits required")
    discovery = inspect_project(project)
    plan = setup_plan(discovery, framework)
    if plan["framework"] != "flask":
        raise ValueError("Automatic test wiring currently supports uniquely detected Flask projects; use the other adapters explicitly")
    if not discovery["scan_complete"] or not plan["test_paths"]:
        raise ValueError("A complete source scan with existing tests is required")
    if any("Connect a saferevoke_flask fixture" in blocker for blocker in plan["blockers"]):
        raise ValueError("Connect the generated saferevoke_flask fixture to a registered test store first")
    root = Path(discovery["root"])
    # New output per invocation; never overwrite a prior security report.
    parent = root / "reports" / "saferevoke-auto"
    if not parent.resolve().is_relative_to(root):
        raise ValueError("The report directory must remain inside the selected project")
    parent.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=parent))
    environment = dict(os.environ)
    sdk_parent = str(Path(__file__).resolve().parent.parent)
    environment["PYTHONPATH"] = sdk_parent + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    common = [sys.executable, "-m", "pytest", "-p", "saferevoke.flask_pytest", "-q",
              *("./" + path for path in plan["test_paths"])]
    summary = {"schema_version": 1, "framework": "flask", "output": str(destination),
               "selected_grant_ids": [], "unexercised_grant_ids": [], "status": "discovery_started"}

    def finish(status, code):
        summary["status"] = status
        (destination / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return code, summary

    def run(arguments):
        return subprocess.run(arguments, cwd=root, env=environment, timeout=timeout, shell=False).returncode

    try:
        baseline_dir = destination / "discovery"
        status = run([*common, "--saferevoke-flask-discover", "--saferevoke-flask-output", str(baseline_dir)])
        if status != 0:
            return finish("baseline_failed_no_removals_attempted", status)
        report = json.loads((baseline_dir / "report.json").read_text(encoding="utf-8"))
        if report["cleanup_failed"] or report["baseline_failures"] or not report["runs"]:
            return finish("baseline_inconclusive_no_removals_attempted", 2)
        observed = {grant_id for record in report["runs"] for event in record["events"]
                    if event["allowed"] for grant_id in event["grant_ids"]}
        inventoried = {grant["id"] for record in report["runs"] for grant in record.get("inventory", [])}
        summary["selected_grant_ids"] = sorted(observed)
        summary["unexercised_grant_ids"] = sorted(inventoried - observed)
        if not observed:
            return finish("no_exercised_permissions_no_removals_attempted", 2)
        if not observed <= inventoried:
            return finish("inconsistent_inventory_no_removals_attempted", 2)
        if len(observed) > max_targets:
            return finish("target_limit_exceeded_no_removals_attempted", 2)
        arguments = [*common, "--saferevoke-flask", "--saferevoke-flask-output", str(destination / "removals")]
        for grant_id in sorted(observed):
            arguments.append("--saferevoke-flask-deny=" + grant_id)
        status = run(arguments)
        removal_path = destination / "removals" / "report.json"
        if not removal_path.is_file():
            return finish("removal_test_run_incomplete", status or 2)
        removal_report = json.loads(removal_path.read_text(encoding="utf-8"))
        summary["findings_summary"] = dict(Counter(item["classification"] for item in removal_report["findings"]))
        if removal_report["cleanup_failed"]:
            return finish("restoration_failed_reset_test_environment", 2)
        if removal_report["baseline_failures"]:
            return finish("mutation_baseline_inconclusive", status or 2)
        applied = {item["denied"] for item in removal_report["runs"] if item["mutation_applied"]}
        if not observed <= applied:
            return finish("discovered_targets_not_applied_review_inventory", status or 2)
        return finish("removal_test_run_completed" if status in (0, 1) else "removal_test_run_incomplete", status)
    except subprocess.TimeoutExpired:
        return finish("timeout_state_unverified_reset_test_environment", 2)
