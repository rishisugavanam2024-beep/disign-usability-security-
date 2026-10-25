"""Opt-in reruns of existing pytest-django tests under grant removal."""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("saferevoke")
    group.addoption("--saferevoke", action="store_true", help="Run selected Django tests with baseline and permission-removal variants")
    group.addoption("--saferevoke-deny", action="append", default=[], metavar="SELECTOR",
                    help="Repeatable user:USERNAME:app.codename or group:NAME:app.codename")
    group.addoption("--saferevoke-users", default="", help="Comma-separated test usernames; default: all active non-superusers in fixtures")
    group.addoption("--saferevoke-output", default="reports/pytest-saferevoke", help="Directory for JSON and HTML results")
    group.addoption("--saferevoke-selection", choices=("all", "affected"), default="all",
                    help="all: run every variant; affected: use fresh baseline traces to skip unrelated variants")


def _selector(value):
    parts = value.split(":")
    if len(parts) != 3 or parts[0] not in {"user", "group"} or not parts[1] or len(parts[2].split(".")) != 2 or not all(parts[2].split(".")):
        raise pytest.UsageError("Use --saferevoke-deny user:alice:auth.view_user or group:operators:auth.view_user")
    return value


def pytest_configure(config):
    config.addinivalue_line("markers", "saferevoke_skip: omit tests that are incompatible with permission mutation")
    config.addinivalue_line("markers", "saferevoke_full: always run all permission mutations for this test")
    config._saferevoke_records = []
    config._saferevoke_baselines = {}
    if not config.getoption("saferevoke"):
        return
    targets = config.getoption("saferevoke_deny")
    if not targets:
        raise pytest.UsageError("Supply at least one --saferevoke-deny selector")
    for value in targets:
        _selector(value)
    if len(set(targets)) != len(targets):
        raise pytest.UsageError("Permission-removal selectors must be unique")
    workers = getattr(config.option, "numprocesses", None)
    if workers not in (None, 0, "0"):
        raise pytest.UsageError("This initial SafeRevoke plugin requires a serial pytest run; omit -n")


def pytest_generate_tests(metafunc):
    if not metafunc.config.getoption("saferevoke") or metafunc.definition.get_closest_marker("saferevoke_skip"):
        return
    cases = [{"id": "saferevoke-baseline", "deny": None}]
    cases += [{"id": f"saferevoke-deny-{index}", "deny": selector}
              for index, selector in enumerate(metafunc.config.getoption("saferevoke_deny"))]
    metafunc.parametrize("_saferevoke_case", cases, indirect=True, ids=[case["id"] for case in cases])


def _case(item):
    return getattr(getattr(item, "callspec", None), "params", {}).get("_saferevoke_case")


def _test_key(item, case):
    return "saferevoke-case".join(item.nodeid.rsplit(case["id"], 1))


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    if config.getoption("saferevoke") and config.getoption("saferevoke_selection") == "affected":
        # Compute this run's dependencies before considering any mutation. Do not
        # reuse maps from an earlier run, where fixtures or code may have changed.
        items.sort(key=lambda item: bool(_case(item) and _case(item)["deny"]))


def _dependency_decision(baseline, selector):
    """Only skip when the observed, passing baseline has no dependency on target."""
    if baseline is None or baseline.get("call") != "passed" or baseline.get("teardown") != "passed":
        return True, "No passing baseline available; run conservatively"
    if not baseline.get("database_restored"):
        return True, "Baseline restoration was not verified; run conservatively"
    if baseline.get("trace_uncertainties") or not baseline.get("events"):
        return True, "Baseline trace is incomplete or empty; run conservatively"
    lab = baseline.get("_lab")
    if lab is None or selector not in lab.grants:
        return True, "Target was not inventoried in the baseline; check current fixtures"
    grant = lab.grants[selector]
    for event in baseline["events"]:
        if selector in event["grant_ids"]:
            return True, "Baseline used this grant"
        principal_matches = (
            grant.principal == event["identity"] if grant.principal_type == "identity"
            else grant.principal in lab.roles.get(event["identity"], set())
        )
        if not principal_matches:
            continue
        if (event["resource"], event["action"]) == (grant.resource, grant.action):
            return True, "Baseline checked the corresponding permission"
        if event["action"] == "all_permissions":
            return True, "Baseline enumerated this identity's permissions"
        if event["action"] == "user_permissions" and grant.principal_type == "identity":
            return True, "Baseline enumerated direct user permissions"
        if event["action"] == "group_permissions" and grant.principal_type == "role":
            return True, "Baseline enumerated group permissions"
        if event["action"] == "module_permissions" and grant.resource.startswith(event["resource"] + "."):
            return True, "Baseline checked access to this application module"
    return False, "No dependency on this grant in the observed baseline trace"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    case = _case(item)
    if not item.config.getoption("saferevoke") or not case or not case["deny"]:
        return
    if item.config.getoption("saferevoke_selection") != "affected":
        return
    record = _start_record(item, case)
    if item.get_closest_marker("saferevoke_full"):
        record["selection_reason"] = "Test explicitly requires all mutation variants"
        return
    baseline = item.config._saferevoke_baselines.get(record["test"])
    selected, reason = _dependency_decision(baseline, case["deny"])
    record["selection_reason"] = reason
    if not selected:
        record["selection_omitted"] = True
        # This hook precedes fixture preparation, saving its database/setup cost.
        pytest.skip("SafeRevoke: " + reason)


@pytest.fixture(autouse=True)
def _saferevoke_case(request):
    # The mutation itself happens in runtest_call, after all application fixtures.
    request.node._saferevoke_context = (request, getattr(request, "param", None))


def _clear_user_caches(request, user_model):
    visited = set()
    uncertainties = set()
    def clear(value):
        if id(value) in visited:
            return
        visited.add(id(value))
        if isinstance(value, user_model):
            if value.is_superuser:
                uncertainties.add("A fixture contains a superuser whose checks may bypass tracing")
            for name in ("_perm_cache", "_user_perm_cache", "_group_perm_cache", "_prefetched_objects_cache"):
                value.__dict__.pop(name, None)
        elif isinstance(value, dict):
            for child in value.values():
                clear(child)
        elif isinstance(value, (tuple, list, set)):
            for child in value:
                clear(child)
    for value in request.node.funcargs.values():
        clear(value)
    return uncertainties


def _normalize_lab(lab, bindings):
    """Stable grant labels survive fixture-created database PK changes between runs."""
    from django.contrib.auth.models import Group, Permission
    from saferevoke.model import Grant, Lab
    group_names = {group.pk: group.name for group in Group.objects.all()}
    labels = {}
    grants = {}
    for native_id, binding in bindings.items():
        permission = Permission.objects.select_related("content_type").get(pk=binding.permission_pk)
        old = lab.grants[native_id]
        identity = old.principal if binding.principal_type == "identity" else group_names[binding.principal_pk]
        kind = "user" if binding.principal_type == "identity" else "group"
        label = f"{kind}:{identity}:{permission.content_type.app_label}.{permission.codename}"
        labels[native_id] = label
        principal = old.principal if kind == "user" else f"group:{identity}"
        grants[label] = Grant(label, principal, old.principal_type, old.probe_identity,
                              old.resource, old.action, old.description)
    roles = {identity: {f"group:{group_names[int(role.split(':')[-1])]}" for role in role_ids}
             for identity, role_ids in lab.roles.items()}
    return Lab(grants, roles, lab.workflows, set(), lab.capability_universe, lab.action_weights, {}), labels


def _start_record(item, case):
    record = getattr(item, "_saferevoke_record", None)
    if record is None:
        key = _test_key(item, case)
        record = {"test": key, "nodeid": item.nodeid, "variant": case["id"], "denied": case["deny"],
                  "events": [], "mutation_applied": False}
        item._saferevoke_record = record
        item.config._saferevoke_records.append(record)
    return record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    context = getattr(item, "_saferevoke_context", None)
    if not item.config.getoption("saferevoke") or context is None or context[1] is None:
        yield
        return
    request, case = context
    record = _start_record(item, case)
    key = record["test"]
    adapter = snapshot = token = None
    settings_override = None
    try:
        request.getfixturevalue("db")
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.test import override_settings
        from saferevoke.adapters.django import DjangoAdapter, TraceSession, _trace, discover_lab
        from saferevoke.model import Workflow
        standard = "django.contrib.auth.backends.ModelBackend"
        tracing = "saferevoke.adapters.django.TracingModelBackend"
        if settings.AUTHENTICATION_BACKENDS not in ([standard], [tracing], [tracing, standard]):
            raise RuntimeError("SafeRevoke currently supports standard Django ModelBackend only")
        settings_override = override_settings(SAFEREVOKE_TEST_ENVIRONMENT=True,
                                             AUTHENTICATION_BACKENDS=[tracing, standard])
        settings_override.enable()
        user_model = get_user_model()
        configured_users = [value.strip() for value in item.config.getoption("saferevoke_users").split(",") if value.strip()]
        usernames = configured_users or list(user_model.objects.filter(is_active=True, is_superuser=False)
                                            .values_list(user_model.USERNAME_FIELD, flat=True))
        if not usernames:
            if case["deny"]:
                record["not_applicable"] = "No active non-superuser accounts in this test's fixtures"
                pytest.skip(record["not_applicable"])
            # A normal unit test can still supply a baseline without any users.
            yield
            return
        placeholder = Workflow(key, key, "Existing pytest test", lambda ctx: None)
        lab, bindings = discover_lab(usernames, [placeholder])
        normalized_lab, labels = _normalize_lab(lab, bindings)
        record["_lab"] = normalized_lab
        record["inventory"] = [asdict(grant) for grant in normalized_lab.grants.values()]
        target = next((native_id for native_id, label in labels.items() if label == case["deny"]), None)
        if case["deny"] and target is None:
            record["not_applicable"] = "Selected grant is absent from this test's prepared fixtures"
            pytest.skip(record["not_applicable"])
        adapter = DjangoAdapter(lab, bindings)
        snapshot = adapter.snapshot()
        adapter.deny({target} if target else set())
        record["mutation_applied"] = target is not None
        uncertainties = _clear_user_caches(request, user_model)
        events = []
        record["_events"] = events
        trace_session = TraceSession(key, events, bindings)
        trace_session.uncertainties.update(uncertainties)
        token = _trace.set(trace_session)
        yield
    finally:
        if token is not None:
            _trace.reset(token)
            record["trace_uncertainties"] = sorted(trace_session.uncertainties)
            record["events"] = [dict(event.to_dict(), grant_ids=[labels[value] for value in event.grant_ids])
                                for event in record.pop("_events", [])]
        try:
            if snapshot is not None:
                adapter.restore(snapshot)
                record["database_restored"] = True
        finally:
            if settings_override is not None:
                settings_override.disable()
                _clear_user_caches(request, get_user_model())


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    record = getattr(item, "_saferevoke_record", None)
    if record is None and item.config.getoption("saferevoke"):
        case = getattr(getattr(item, "callspec", None), "params", {}).get("_saferevoke_case")
        if case:
            record = _start_record(item, case)
    if record is not None:
        record[report.when] = "xfail" if hasattr(report, "wasxfail") else report.outcome
        if report.failed:
            record["failure"] = str(report.longrepr)
        if report.when == "teardown" and record["denied"] is None:
            item.config._saferevoke_baselines[record["test"]] = record


def _build_report(records):
    from saferevoke.engine import SafeRevokeEngine
    from saferevoke.model import AccessEvent, WorkflowRun
    baselines = {record["test"]: record for record in records if record["denied"] is None}
    findings = []
    for record in records:
        if record["denied"] is None:
            continue
        baseline = baselines.get(record["test"])
        finding = {"test": record["test"], "denied": record["denied"]}
        if baseline is None or baseline.get("call") != "passed" or baseline.get("teardown") != "passed":
            finding.update(classification="INCONCLUSIVE", reason="A passing baseline and teardown are required")
        elif record.get("selection_omitted"):
            finding.update(classification="NOT_SELECTED", reason="Omitted before fixture setup because no dependency was observed; this is not a tested safe-removal result")
        elif record.get("not_applicable"):
            finding.update(classification="NOT_APPLICABLE", reason=record["not_applicable"])
        elif record.get("call") not in {"passed", "failed"} or record.get("teardown") != "passed" or not record.get("database_restored"):
            finding.update(classification="INCONCLUSIVE", reason="Test was skipped, expected to fail, or did not complete cleanly")
        else:
            lab = baseline.get("_lab")
            if lab is None or record["denied"] not in lab.grants:
                finding.update(classification="INCONCLUSIVE", reason="Grant did not exist in the matching baseline fixture inventory")
            elif ({grant.id for grant in lab.grants.values()} != {grant["id"] for grant in record.get("inventory", [])}
                  or lab.roles != record["_lab"].roles):
                finding.update(classification="INCONCLUSIVE", reason="Fixture permission inventory differs between variants")
            else:
                key = record["test"]
                before = WorkflowRun(key, True, "assertions passed", [AccessEvent(**event) for event in baseline["events"]], "Baseline test passed")
                passed = record["call"] == "passed"
                after = WorkflowRun(key, passed, "assertions passed" if passed else "assertions failed",
                                    [AccessEvent(**event) for event in record["events"]], "Existing test assertions")
                classified = SafeRevokeEngine(lab)._classify({record["denied"]}, {key: before}, {key: after}, record["denied"])
                finding.update(classified)
                exercised = any(record["denied"] in event["grant_ids"] for event in baseline["events"] if event["allowed"])
                if not exercised:
                    finding.update(
                        classification="UNKNOWN" if passed else "TEST_FAILED_AFTER_REMOVAL",
                        reason="Selected grant was not observed in the baseline test trace; attribution needs more coverage",
                    )
                if finding["classification"] == "SAFE":
                    finding.update(classification="NO_FAILURE_OBSERVED", reason="Existing assertions passed; review trace and assertion coverage before removing real access")
        findings.append(finding)
    return {
        "kind": "Existing Django tests under permission removal",
        "scope": "Configured synchronous pytest-django tests and their existing assertions; no complete security or application coverage guarantee.",
        "findings": findings,
        "runs": [{key: value for key, value in record.items() if not key.startswith("_")} for record in records],
        "baseline_failures": [record["nodeid"] for record in baselines.values() if record.get("call") != "passed" or record.get("teardown") != "passed"],
        "counts": {
            "baseline_runs": len(baselines),
            "mutation_runs": len(records) - len(baselines),
            "mutations_applied": sum(bool(record["mutation_applied"]) for record in records),
            "mutation_variants_omitted": sum(bool(record.get("selection_omitted")) for record in records),
            "test_bodies_executed": sum(record.get("call") in {"passed", "failed", "xfail"} for record in records),
        },
    }


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if not config.getoption("saferevoke"):
        return
    report = _build_report(config._saferevoke_records)
    report["selection"] = {
        "mode": config.getoption("saferevoke_selection"),
        "basis": "Fresh baseline permission traces from this run; unobserved branches and direct database access may be missed",
        "dependencies": {
            record["test"]: sorted({grant_id for event in record["events"] for grant_id in event["grant_ids"]})
            for record in config._saferevoke_records if record["denied"] is None
        },
    }
    destination = Path(config.getoption("saferevoke_output"))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in
                    (finding["test"], finding["denied"], finding["classification"], finding["reason"])) + "</tr>"
                   for finding in report["findings"])
    (destination / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>SafeRevoke pytest report</title>'
        '<style>body{font:16px/1.5 system-ui;margin:32px}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #aaa;text-align:left;overflow-wrap:anywhere}</style>'
        '<h1>SafeRevoke: existing Django tests</h1><p>' + escape(report["scope"]) + '</p>'
        f'<p>Selection: {escape(report["selection"]["mode"])}. Test bodies executed: {report["counts"]["test_bodies_executed"]}. '
        f'Mutation variants omitted before setup: {report["counts"]["mutation_variants_omitted"]}.</p>'
        '<table><tr><th>Test</th><th>Grant removed</th><th>Finding</th><th>Reason</th></tr>' + rows + '</table></html>', encoding="utf-8")
    config._saferevoke_report = report


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    report = getattr(config, "_saferevoke_report", None)
    if report is None:
        return
    terminalreporter.section("SafeRevoke permission-removal results")
    terminalreporter.write_line(f"Selection: {config.getoption('saferevoke_selection')}; "
                               f"{report['counts']['test_bodies_executed']} test bodies executed; "
                               f"{report['counts']['mutation_variants_omitted']} mutation variants omitted before fixture setup")
    for finding in report["findings"]:
        terminalreporter.write_line(f"{finding['classification']}: {finding['denied']} -> {finding['test']}")
    terminalreporter.write_line(f"HTML/JSON reports: {Path(config.getoption('saferevoke_output')).resolve()}")
