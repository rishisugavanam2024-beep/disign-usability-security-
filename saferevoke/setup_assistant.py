"""Read-only project discovery and non-overwriting setup generation.

Never imports project modules, invokes package managers, reads .env files,
connects to databases, or executes collected tests.
"""
from __future__ import annotations

import ast
from dataclasses import asdict
import json
import os
from pathlib import Path
import re

from saferevoke.model import Grant


EXCLUDED = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".tox",
            ".pytest_cache", ".mypy_cache", "build", "dist", "reports", ".codex", ".agents",
            "saferevoke-setup"}
FRAMEWORKS = {"django": "django", "flask": "flask", "fastapi": "fastapi"}
PROVIDERS = {"keycloak": "keycloak", "auth0": "auth0"}


def _fixture_name(node, pytest_names, fixture_names):
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        recognized = (isinstance(target, ast.Name) and target.id in fixture_names) or (
            isinstance(target, ast.Attribute) and target.attr == "fixture"
            and isinstance(target.value, ast.Name) and target.value.id in pytest_names)
        if recognized:
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        return keyword.value.value
            return node.name
    return None


def inspect_project(root, *, max_files=3000, max_file_bytes=1_000_000, max_total_bytes=10_000_000):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Select a project directory")
    if max_files <= 0 or max_file_bytes <= 0 or max_total_bytes <= 0:
        raise ValueError("Positive scan limits required")
    report = {"schema_version": 1, "root": str(root), "scan_complete": True,
              "frameworks": [], "providers": [], "evidence": [], "tests": [],
              "fixtures": [], "grants": [], "settings_modules": [], "warnings": [],
              "files_scanned": 0, "bytes_scanned": 0}
    frameworks, providers, settings = set(), set(), set()
    grants, conflicting_ids = {}, set()

    def evidence(name, path, line, kind):
        destination = frameworks if name in FRAMEWORKS.values() else providers
        destination.add(name)
        report["evidence"].append({"component": name, "path": path, "line": line, "kind": kind})

    def directory_error(error):
        report["scan_complete"] = False
        report["warnings"].append("A source directory could not be read")

    for directory, folders, filenames in os.walk(root, followlinks=False, onerror=directory_error):
        folders[:] = sorted(name for name in folders if name not in EXCLUDED
                            and not name.startswith(".") and not (Path(directory) / name).is_symlink())
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            settings_file = filename in {"pytest.ini", "setup.cfg", "tox.ini"}
            manifest = filename == "pyproject.toml" or filename.startswith("requirements") and filename.endswith(".txt")
            if path.suffix != ".py" and not manifest and not settings_file and filename != "package.json":
                continue
            if report["files_scanned"] >= max_files:
                report["scan_complete"] = False
                report["warnings"].append("File-count limit reached; narrow the selected project directory")
                break
            relative = path.relative_to(root).as_posix()
            try:
                size = path.stat().st_size
                if size > max_file_bytes:
                    report["scan_complete"] = False
                    report["warnings"].append(f"Oversized file not scanned: {relative}")
                    continue
                if report["bytes_scanned"] + size > max_total_bytes:
                    report["scan_complete"] = False
                    report["warnings"].append("Total source size limit reached; narrow the selected directory")
                    continue
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                report["scan_complete"] = False
                report["warnings"].append(f"Unreadable source file: {relative}")
                continue
            report["files_scanned"] += 1
            report["bytes_scanned"] += size
            if manifest or settings_file:
                settings.update(re.findall(r"(?m)^\s*DJANGO_SETTINGS_MODULE\s*=\s*['\"]?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", text))
            if settings_file:
                continue
            if manifest:
                # Dependency declarations are hints, not proof of the app's runtime.
                if filename == "pyproject.toml":
                    candidates = re.findall(r'[\"\']([A-Za-z0-9_.-]+)(?:\[[^\"\']*\])?(?:[<>=!~; ][^\"\']*)?[\"\']', text)
                else:
                    candidates = [re.split(r"[\s\[<>=!~;]", line.strip())[0] for line in text.splitlines()
                                  if line.strip() and not line.lstrip().startswith(("#", "-"))]
                for candidate in candidates:
                    name = candidate.lower().replace("-", "_")
                    if name in FRAMEWORKS:
                        evidence(FRAMEWORKS[name], relative, None, "dependency hint")
                continue
            if filename == "package.json":
                try:
                    data = json.loads(text)
                    dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    if "express" in dependencies:
                        report["evidence"].append({"component": "node-express", "path": relative, "line": None, "kind": "dependency hint; custom bridge required"})
                except (ValueError, TypeError, AttributeError):
                    report["warnings"].append(f"Invalid package manifest: {relative}")
                continue
            try:
                tree = ast.parse(text, filename=relative)
            except SyntaxError:
                report["scan_complete"] = False
                report["warnings"].append(f"Python syntax could not be parsed: {relative}")
                continue
            grant_names, pytest_names, fixture_names = set(), set(), set()
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                    pytest_names.update(alias.asname or "pytest" for alias in node.names if alias.name == "pytest")
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                    if node.module == "saferevoke.model":
                        grant_names.update(alias.asname or "Grant" for alias in node.names if alias.name == "Grant")
                    if node.module == "pytest":
                        fixture_names.update(alias.asname or "fixture" for alias in node.names if alias.name == "fixture")
                for name in names:
                    if name in FRAMEWORKS:
                        evidence(FRAMEWORKS[name], relative, node.lineno, "source import")
                    elif name in PROVIDERS:
                        evidence(PROVIDERS[name], relative, node.lineno, "source import")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fixture = _fixture_name(node, pytest_names, fixture_names)
                    if fixture:
                        report["fixtures"].append({"name": fixture, "path": relative, "line": node.lineno})
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in grant_names:
                    try:
                        grant = Grant(*[ast.literal_eval(argument) for argument in node.args],
                                      **{keyword.arg: ast.literal_eval(keyword.value) for keyword in node.keywords})
                        if (grant.principal_type not in {"identity", "role"}
                                or not all(isinstance(value, str) for value in asdict(grant).values())
                                or not all((grant.id, grant.principal, grant.probe_identity, grant.resource, grant.action))):
                            raise ValueError("Invalid literal grant")
                    except (ValueError, TypeError, KeyError):
                        report["warnings"].append(f"Dynamic grant requires runtime inventory: {relative}:{node.lineno}")
                    else:
                        if grant.id in grants and grants[grant.id]["grant"] != asdict(grant):
                            conflicting_ids.add(grant.id)
                        grants[grant.id] = {"grant": asdict(grant), "path": relative, "line": node.lineno,
                                            "basis": "literal source definition; runtime not verified"}
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault"
                        and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == "DJANGO_SETTINGS_MODULE"
                        and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                    settings.add(node.args[1].value)
            if filename.startswith("test_") or filename.endswith("_test.py"):
                functions = []
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                        functions.append({"name": node.name, "line": node.lineno, "async": isinstance(node, ast.AsyncFunctionDef)})
                    elif isinstance(node, ast.ClassDef):
                        functions.extend({"name": node.name + "::" + method.name, "line": method.lineno,
                                          "async": isinstance(method, ast.AsyncFunctionDef)}
                                         for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test"))
                if functions:
                    report["tests"].append({"path": relative, "functions": functions,
                                            "basis": "static candidates; pytest collection may differ"})
        if report["files_scanned"] >= max_files:
            report["scan_complete"] = False
            if not any("File-count limit" in warning for warning in report["warnings"]):
                report["warnings"].append("File-count limit reached; scan completeness is unverified")
            break
    for grant_id in sorted(conflicting_ids):
        grants.pop(grant_id, None)
        report["warnings"].append(f"Conflicting source definitions excluded for grant: {grant_id}")
    report["frameworks"] = sorted(frameworks)
    report["providers"] = sorted(providers)
    report["grants"] = [grants[key] for key in sorted(grants)]
    report["settings_modules"] = sorted(settings)
    return report


def setup_plan(report, framework=None):
    supported = {"flask", "django", "fastapi"}
    if framework is not None and framework not in supported:
        raise ValueError("Choose flask, django or fastapi")
    detected = report["frameworks"]
    selected = framework or (detected[0] if len(detected) == 1 else None)
    blockers = []
    if not report["scan_complete"]:
        blockers.append("Scan incomplete; review warnings and select a narrower source directory")
    if selected is None:
        blockers.append("Choose --framework explicitly; no unique framework was detected")
    if not report["tests"]:
        blockers.append("No test candidates found; add or explicitly select your existing tests")
    if selected == "flask":
        conftests = [item for item in report["fixtures"] if item["name"] == "saferevoke_flask"]
        for test in report["tests"]:
            test_path = Path(test["path"])
            applicable = any(item["path"] == test["path"] or (
                Path(item["path"]).name == "conftest.py" and Path(item["path"]).parent in test_path.parents)
                             for item in conftests)
            if not applicable:
                blockers.append(f"Connect a saferevoke_flask fixture for {test['path']}; see generated example")
        if not report["grants"]:
            blockers.append("No literal grants found; discover the registered store in an isolated test run")
    elif selected == "django":
        blockers.append("Select user/group removal targets after inspecting the test permission inventory")
    elif selected == "fastapi":
        blockers.append("FastAPI currently uses the engine API; connect state hooks and workflows")
    plan = {"schema_version": 1, "root": report["root"], "framework": selected,
            "status": "configuration_detected" if not blockers else "needs_configuration",
            "test_paths": [test["path"] for test in report["tests"]],
            "candidate_grant_ids": [item["grant"]["id"] for item in report["grants"]],
            "blockers": blockers, "runtime_verified": False,
            "note": "Source hints are not permission truth or proof of isolation. No application code or tests were executed."}
    return plan


FLASK_EXAMPLE = '''# Copy into your root conftest.py after connecting an isolated test store.
import pytest
from saferevoke.flask_testing import FlaskTestIntegration

pytest_plugins = ["saferevoke.flask_pytest"]

@pytest.fixture
def saferevoke_flask(app):
    # app must use TESTING=True and SAFEREVOKE_TEST_ENVIRONMENT=True.
    # Register your explicit test permission store once:
    # app.extensions["saferevoke"] = test_permission_store
    return FlaskTestIntegration.from_registered_store(app)

# Required store methods:
# inventory() -> list[Grant]; snapshot(); remove_grants(ids);
# restore(snapshot); matches_snapshot(snapshot) -> bool.
# Optional metadata: user_roles(), capability_universe(), action_weights().
# Snapshot/reset must cover business writes and cached credentials too.
'''


def write_setup(root, *, framework=None):
    report = inspect_project(root)
    plan = setup_plan(report, framework)
    destination = Path(report["root"]) / "saferevoke-setup"
    # A fresh output directory avoids overwriting configuration or following a
    # pre-existing symlink. Existing user files and conftest.py remain untouched.
    destination.mkdir(exist_ok=False)
    files = {"discovery.json": json.dumps(report, indent=2),
             "plan.json": json.dumps(plan, indent=2),
             "flask-conftest.py.example": FLASK_EXAMPLE,
             "README.txt": (
                 "SafeRevoke setup discovery (local source feature)\n\n"
                 "Review plan.json blockers and discovery.json evidence. Files were read, not imported.\n"
                 "No dependencies were installed and no permissions or databases were changed.\n"
                 "The Flask example is a template; copying it alone does not connect your store.\n"
                 "Run existing tests only in your isolated test environment.\n"
                 "Flask: python -m pytest -p saferevoke.flask_pytest TEST_PATH --saferevoke-flask "
                 "--saferevoke-flask-deny GRANT_ID\n"
                 "Django: python -m pytest TEST_PATH --saferevoke --saferevoke-deny "
                 "user:USERNAME:app.codename\n"
                 "Static grant IDs are candidates; verify them against runtime test data.\n")}
    for filename, text in files.items():
        (destination / filename).write_text(text + "\n", encoding="utf-8")
    return destination, plan
