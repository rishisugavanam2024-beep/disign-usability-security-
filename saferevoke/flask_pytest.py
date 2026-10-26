"""Opt-in permission-removal variants for existing synchronous Flask tests.

Load with ``pytest -p saferevoke.flask_pytest`` or pytest_plugins in conftest.py.
It is separate from the existing Django plugin and does not change its behavior.
"""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path

import pytest

from saferevoke.adapters.web import WebContext, _active
from saferevoke.engine import SafeRevokeEngine
from saferevoke.flask_testing import FlaskTestIntegration
from saferevoke.model import AccessEvent, WorkflowRun


def pytest_addoption(parser):
    group = parser.getgroup("saferevoke-flask")
    group.addoption("--saferevoke-flask", action="store_true", help="Rerun existing Flask tests before and after permission removal")
    group.addoption("--saferevoke-flask-deny", action="append", default=[], metavar="GRANT_ID",
                    help="Repeat for each grant ID configured in the saferevoke_flask fixture")
    group.addoption("--saferevoke-flask-output", default="reports/pytest-saferevoke-flask")
    group.addoption("--saferevoke-flask-discover", action="store_true",
                    help="Run baselines only and export their real test-fixture inventory")


def pytest_configure(config):
    config.addinivalue_line("markers", "saferevoke_flask_skip: exclude a test from Flask permission variants")
    config._saferevoke_flask_records = []
    config._saferevoke_flask_dirty = False
    discovering = config.getoption("saferevoke_flask_discover")
    if discovering:
        config.option.saferevoke_flask = True
    if not config.getoption("saferevoke_flask"):
        return
    if config.getoption("saferevoke", default=False):
        raise pytest.UsageError("Run the Flask and Django mutation plugins separately")
    targets = config.getoption("saferevoke_flask_deny")
    if discovering and targets:
        raise pytest.UsageError("Discovery runs baselines only; omit removal targets")
    if (not targets and not discovering) or any(not value.strip() for value in targets):
        raise pytest.UsageError("Supply at least one --saferevoke-flask-deny GRANT_ID")
    if len(set(targets)) != len(targets):
        raise pytest.UsageError("Flask grant identifiers must be unique")
    if getattr(config.option, "numprocesses", None) not in (None, 0, "0"):
        raise pytest.UsageError("Flask permission mutation currently requires serial pytest; omit -n")


def pytest_generate_tests(metafunc):
    if not metafunc.config.getoption("saferevoke_flask") or metafunc.definition.get_closest_marker("saferevoke_flask_skip"):
        return
    if metafunc.cls is not None:
        import unittest
        if issubclass(metafunc.cls, unittest.TestCase):
            raise pytest.UsageError("Select pytest-style functions; unittest.TestCase parametrization is unsupported")
    cases = [{"id": "flask-baseline", "deny": None}]
    cases.extend({"id": f"flask-deny-{index}", "deny": grant_id}
                 for index, grant_id in enumerate(metafunc.config.getoption("saferevoke_flask_deny")))
    metafunc.parametrize("_saferevoke_flask_case", cases, indirect=True,
                         ids=[case["id"] for case in cases])


def pytest_collection_modifyitems(config, items):
    if not config.getoption("saferevoke_flask"):
        return
    import inspect
    for item in items:
        if item.get_closest_marker("saferevoke_flask_skip"):
            continue
        case = getattr(getattr(item, "callspec", None), "params", {}).get("_saferevoke_flask_case")
        if case is None or inspect.iscoroutinefunction(getattr(item, "obj", None)):
            raise pytest.UsageError("Select synchronous pytest-style tests for Flask permission variants")


@pytest.fixture(autouse=True)
def _saferevoke_flask_case(request):
    request.node._saferevoke_flask_context = (request, getattr(request, "param", None))


def _record(item, case):
    record = getattr(item, "_saferevoke_flask_record", None)
    if record is None:
        record = {"test": "flask-case".join(item.nodeid.rsplit(case["id"], 1)),
                  "nodeid": item.nodeid, "denied": case["deny"], "events": [],
                  "mutation_applied": False, "state_restored": False}
        item._saferevoke_flask_record = record
        item.config._saferevoke_flask_records.append(record)
    return record


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if item.config.getoption("saferevoke_flask") and item.config._saferevoke_flask_dirty:
        pytest.exit("SafeRevoke stopped: test-state restoration failed; reset the test environment", returncode=2)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    context = getattr(item, "_saferevoke_flask_context", None)
    if not item.config.getoption("saferevoke_flask") or context is None or context[1] is None:
        yield
        return
    request, case = context
    record = _record(item, case)
    integration = snapshot = token = None
    taken = False
    trace = None
    try:
        integration = request.getfixturevalue("saferevoke_flask")
        if not isinstance(integration, FlaskTestIntegration):
            raise TypeError("The saferevoke_flask fixture must return FlaskTestIntegration")
        # Copy fixture metadata before the application mutates anything.
        from copy import deepcopy
        lab = deepcopy(integration.lab)
        record["_lab"] = lab
        record["inventory"] = [asdict(grant) for grant in lab.grants.values()]
        snapshot = integration.hooks.snapshot()
        taken = True
        trace = WebContext(record["test"], lab, None)
        token = _active.set(trace)
        target = case["deny"]
        if target is not None:
            if target not in lab.grants:
                record["not_applicable"] = True
            else:
                integration.hooks.deny({target})
                record["mutation_applied"] = True
        # Trace actual test-body decisions, not fixture or mutation setup.
        trace.events.clear()
        trace.errors.clear()
        yield
    finally:
        if token is not None:
            _active.reset(token)
        if trace is not None:
            record["events"] = [event.to_dict() for event in trace.events]
            record["trace_uncertainties"] = sorted(trace.errors)
        if taken:
            try:
                integration.hooks.restore(snapshot)
                if integration.verify_restored(snapshot) is not True:
                    raise RuntimeError("Application state restoration could not be verified")
                record["state_restored"] = True
            except Exception:
                record["cleanup_failed"] = True
                item.config._saferevoke_flask_dirty = True
                item.session.shouldstop = "SafeRevoke: restoration failed; reset the test environment"
                raise


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    record = getattr(item, "_saferevoke_flask_record", None)
    if record is None and item.config.getoption("saferevoke_flask"):
        case = getattr(getattr(item, "callspec", None), "params", {}).get("_saferevoke_flask_case")
        if case:
            record = _record(item, case)
    if record is not None:
        record[report.when] = "xfail" if hasattr(report, "wasxfail") else report.outcome
        # Do not include assertion traceback text: it may contain application secrets.


def _inventory(lab):
    return ({key: asdict(grant) for key, grant in lab.grants.items()}, lab.roles,
            lab.capability_universe, lab.action_weights)


def _complete(record):
    return (record is not None and record.get("setup") == "passed"
            and record.get("call") in {"passed", "failed"}
            and record.get("teardown") == "passed" and record.get("state_restored")
            and not record.get("trace_uncertainties"))


def _build_report(records):
    baselines = {record["test"]: record for record in records if record["denied"] is None}
    findings = []
    for record in records:
        if record["denied"] is None:
            continue
        before = baselines.get(record["test"])
        finding = {"test": record["test"], "denied": record["denied"]}
        if not _complete(before) or before.get("call") != "passed" or not _complete(record):
            finding.update(classification="INCONCLUSIVE", reason="Passing baseline, complete traces and verified state restoration are required")
        elif record.get("not_applicable"):
            finding.update(classification="NOT_APPLICABLE", reason="Selected grant is absent from this test fixture's inventory")
        elif not record.get("mutation_applied"):
            finding.update(classification="INCONCLUSIVE", reason="Permission mutation did not complete successfully")
        elif _inventory(before["_lab"]) != _inventory(record["_lab"]):
            finding.update(classification="INCONCLUSIVE", reason="Fixture permission metadata changed between variants")
        else:
            key, target = record["test"], record["denied"]
            exercised = any(target in event["grant_ids"] for event in before["events"] if event["allowed"])
            passed = record["call"] == "passed"
            if any(target in event["grant_ids"] for event in record["events"] if event["allowed"]):
                finding.update(classification="ACCESS_STILL_OBSERVED",
                               reason="The selected grant still authorized access after removal; check mutation hooks, tokens and caches")
            elif not exercised:
                finding.update(classification="UNKNOWN" if passed else "TEST_FAILED_AFTER_REMOVAL",
                               reason="Selected grant was not observed in the baseline; more coverage is required")
            else:
                baseline = WorkflowRun(key, True, "assertions passed", [AccessEvent(**event) for event in before["events"]], "Existing test")
                mutated = WorkflowRun(key, passed, "assertions passed" if passed else "assertions failed",
                                      [AccessEvent(**event) for event in record["events"]], "Existing test")
                finding.update(SafeRevokeEngine(before["_lab"])._classify({target}, {key: baseline}, {key: mutated}, target))
                if finding["classification"] == "SAFE":
                    finding.update(classification="NO_FAILURE_OBSERVED", reason="Existing assertions passed; this is not proof that real access can safely be removed")
        findings.append(finding)
    return {"kind": "Existing Flask tests under permission removal",
            "scope": "Configured test-body permission hooks and existing assertions; fixture setup, unobserved branches and external effects are outside coverage.",
            "findings": findings,
            "baseline_failures": [record["nodeid"] for record in baselines.values()
                                  if not _complete(record) or record.get("call") != "passed"],
            "runs": [{key: value for key, value in record.items() if not key.startswith("_")} for record in records]}


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("saferevoke_flask"):
        return
    report = _build_report(session.config._saferevoke_flask_records)
    report["cleanup_failed"] = session.config._saferevoke_flask_dirty
    destination = Path(session.config.getoption("saferevoke_flask_output"))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = "".join("<tr>" + "".join(f"<td>{escape(str(finding[key]))}</td>" for key in ("test", "denied", "classification", "reason")) + "</tr>"
                   for finding in report["findings"])
    (destination / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>SafeRevoke Flask tests</title>'
        '<h1>SafeRevoke: existing Flask tests</h1><p>' + escape(report["scope"]) + '</p>'
        '<table><tr><th>Test</th><th>Removed grant</th><th>Finding</th><th>Reason</th></tr>' + rows + '</table></html>', encoding="utf-8")
    session.config._saferevoke_flask_report = report


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    report = getattr(config, "_saferevoke_flask_report", None)
    if report is None:
        return
    terminalreporter.section("SafeRevoke Flask results")
    for finding in report["findings"]:
        terminalreporter.write_line(f"{finding['classification']}: {finding['denied']} -> {finding['test']}")
    terminalreporter.write_line(f"HTML/JSON reports: {Path(config.getoption('saferevoke_flask_output')).resolve()}")
