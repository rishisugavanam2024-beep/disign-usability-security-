"""Validate against a separately checked-out, pinned official Flaskr tutorial."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


UPSTREAM_COMMIT = "2c1b30d0503cfb064f1cb252e6614a06915a362a"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/upstream-flaskr"))
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve(strict=True)
    project = Path(__file__).resolve().parents[2]
    revision = subprocess.run(["git", "-c", f"safe.directory={checkout.as_posix()}", "rev-parse", "HEAD"],
                              cwd=checkout, capture_output=True, text=True, check=True).stdout.strip()
    if revision != UPSTREAM_COMMIT:
        raise ValueError("Use the pinned Flask 3.1.2 source commit for this validation")
    unchanged = subprocess.run(["git", "-c", f"safe.directory={checkout.as_posix()}", "diff", "--quiet", "HEAD", "--", "examples/tutorial"], cwd=checkout)
    if unchanged.returncode:
        raise ValueError("Upstream tutorial source and assertions must remain unchanged")
    tutorial = checkout / "examples" / "tutorial"
    output = args.output.resolve()
    environment = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    environment.pop("PYTEST_ADDOPTS", None)
    environment["PYTHONPATH"] = os.pathsep.join([str(project), str(tutorial)])
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-p", "saferevoke.flask_pytest",
        "-p", "examples.upstream_flaskr.integration", "-c", str(project / "pyproject.toml"),
        str(tutorial / "tests" / "test_blog.py") + "::test_update",
        str(tutorial / "tests" / "test_blog.py") + "::test_delete",
        "--saferevoke-flask", "--saferevoke-flask-deny", "flaskr:post:1:author:test",
        "--saferevoke-flask-output", str(output), "--tb=short", "-q",
    ], cwd=project, env=environment, timeout=90)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    evidence = {"repository": "https://github.com/pallets/flask", "commit": revision,
                "application": "Official Flaskr tutorial (Flask 3.1.2)",
                "scope": "Original upstream update/delete tests, explicit ownership instrumentation; not full application validation",
                "original_assertions_unchanged": True,
                "required_access_findings": sum(item["classification"] == "REQUIRED_ACCESS" for item in report["findings"]),
                "all_database_states_restored": all(item["state_restored"] for item in report["runs"]),
                "baseline_failures": report["baseline_failures"], "pytest_exit": result.returncode}
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if (result.returncode != 1 or evidence["required_access_findings"] != 2
            or not evidence["all_database_states_restored"] or evidence["baseline_failures"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
