"""Explicit, trusted local connectors for applications outside the automatic Flask flow.

Connector modules are executable Python supplied by the application owner. They are
not sandboxed. Configuration is read without importing them for help/report commands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Callable
import uuid
import webbrowser

from saferevoke import __version__
from saferevoke.adapter import ApplicationAdapter
from saferevoke.engine import SafeRevokeEngine
from saferevoke.model import Lab
from saferevoke.report import render_html, render_json

DEFAULT_CONFIG = "saferevoke.json"


@dataclass
class ExternalAnalysis:
    """Factory result: engine inputs plus optional verified evidence and resource cleanup."""
    lab: Lab
    adapter: ApplicationAdapter
    evidence: Callable[[], dict] = field(default=lambda: {})
    close: Callable[[], None] = field(default=lambda: None)


def _inside(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("Connector and report paths must be relative to the configuration folder")
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Connector and report paths must stay inside the configuration folder")
    return path


def configuration(filename=None, project=".") -> dict:
    path = Path(filename).resolve() if filename else (Path(project) / DEFAULT_CONFIG).resolve()
    if not path.is_file():
        raise ValueError(f"No external connector configuration: {path}. See 'saferevoke connector --help'.")
    if path.stat().st_size > 65536:
        raise ValueError("Connector configuration exceeds 64 KiB")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Connector configuration requires schema_version: 1")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ValueError("Connector configuration requires a name")
    if not isinstance(data.get("options", {}), dict):
        raise ValueError("Connector options must be an object")
    root = path.parent
    module = _inside(root, data.get("module"))
    if module.suffix != ".py" or not module.is_file():
        raise ValueError("Connector module must be an existing local .py file")
    reports = _inside(root, data.get("reports", "reports/saferevoke"))
    return {**data, "path": path, "root": root, "module_path": module, "report_root": reports}


def _load(config):
    if config.get("test_environment") is not True:
        raise ValueError("Connector commands require explicit test_environment: true; never connect production data")
    name = "_saferevoke_connector_" + hashlib.sha256(str(config["module_path"]).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, config["module_path"])
    if spec is None or spec.loader is None:
        raise ValueError("Could not load connector module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def describe(config):
    return {"name": config["name"], "configuration": str(config["path"]),
            "module": str(config["module_path"]), "test_environment": config.get("test_environment") is True,
            "reports": str(config["report_root"]), "module_executed": False}


def control(config, action, subject, permission=None):
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("A nonempty subject is required")
    if action not in {"permissions", "revoke", "grant", "restore"}:
        raise ValueError("Unknown permission control")
    if action != "permissions" and (not isinstance(permission, str) or not permission.strip()):
        raise ValueError("A nonempty permission is required")
    module = _load(config)
    handler = getattr(module, "control", None)
    if not callable(handler):
        raise ValueError("This connector does not implement control(action, subject, permission, root, options)")
    return handler("restore" if action == "grant" else action, subject, permission,
                   config["root"], dict(config.get("options", {})))


def analyze(config, *, baseline_only=False, max_targets=10):
    if max_targets < 1:
        raise ValueError("--max-targets must be positive")
    module = _load(config)
    factory = getattr(module, "create_analysis", None)
    if not callable(factory):
        raise ValueError("Connector must implement create_analysis(root, output, options)")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = config["report_root"] / run_id
    output.mkdir(parents=True, exist_ok=False)
    plan = factory(config["root"], output, dict(config.get("options", {})))
    if not isinstance(plan, ExternalAnalysis):
        raise ValueError("Connector factory must return saferevoke.external.ExternalAnalysis")
    try:
        if not isinstance(plan.lab, Lab) or not plan.lab.workflows:
            raise ValueError("Connector must supply a Lab with at least one workflow")
        if len(plan.lab.grants) > max_targets:
            raise ValueError("Configured grants exceed --max-targets; no workflows were executed")
        print(f"SafeRevoke {__version__}: {Path(__file__).resolve()}", flush=True)
        print(f"External connector: {config['name']} ({config['module_path']})", flush=True)
        engine = SafeRevokeEngine(plan.lab, plan.adapter)
        report = ({"baseline": engine.baseline(), "result": "Configured baseline workflows passed"}
                  if baseline_only else engine.analyze())
        evidence = plan.evidence()
        if not isinstance(evidence, dict):
            raise ValueError("Connector evidence must be an object")
        report["integration"] = {"connector": config["name"], "library_version": __version__,
                                 "configuration": str(config["path"]), "evidence": evidence}
    finally:
        # Do not publish a completed report if restoration/resource cleanup fails.
        plan.close()
    (output / "report.json").write_text(render_json(report), encoding="utf-8")
    if not baseline_only:
        (output / "report.html").write_text(render_html(report), encoding="utf-8")
    completed = {"kind": "baseline" if baseline_only else "analysis", "json": "report.json",
                 "html": None if baseline_only else "report.html"}
    (output / "complete.json").write_text(json.dumps(completed), encoding="utf-8")
    print("JSON report: " + str(output / "report.json"), flush=True)
    if not baseline_only:
        print("Findings: " + json.dumps(report["summary"]), flush=True)
        print("HTML report: " + str(output / "report.html"), flush=True)
    return report


def latest_report(config, *, open_browser=False):
    # No connector import, application access or permission mutation here.
    candidates = []
    for marker in config["report_root"].glob("*/complete.json"):
        folder = marker.parent.resolve()
        if not folder.is_relative_to(config["report_root"]):
            continue
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        if metadata.get("kind") == "analysis" and (folder / "report.html").is_file() and (folder / "report.json").is_file():
            candidates.append(marker)
    if not candidates:
        raise ValueError("No completed external analysis report. Run 'saferevoke test' first.")
    folder = max(candidates, key=lambda p: p.stat().st_mtime_ns).parent.resolve()
    result = {"html": str(folder / "report.html"), "json": str(folder / "report.json")}
    if open_browser:
        result["browser_open_requested"] = webbrowser.open((folder / "report.html").as_uri())
    return result
