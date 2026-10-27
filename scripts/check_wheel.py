"""Install an actual wheel into a new venv and exercise it outside the checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTEST_ADDOPTS", None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="saferevoke-wheel-check-") as folder:
        root = Path(folder)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        binaries = root / "venv" / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        command = binaries / ("saferevoke.exe" if os.name == "nt" else "saferevoke")
        subprocess.run([str(python), "-m", "pip", "install", str(wheel)], cwd=root,
                       env=environment, check=True, timeout=240)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=root, env=environment, check=True)
        subprocess.run([str(command), "--help"], cwd=root, env=environment, check=True)
        project = root / "unrelated-application"
        project.mkdir()
        (project / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        result = subprocess.run([str(command), "inspect"], cwd=project, env=environment,
                                capture_output=True, text=True, check=True)
        if json.loads(result.stdout)["discovery"]["root"] != str(project):
            raise RuntimeError("Console entry point did not inspect its actual working directory")
        code = ("from importlib.metadata import version; from pathlib import Path; "
                "import saferevoke; "
                "assert version('saferevoke') == saferevoke.__version__ == '0.1.0a4'; "
                "assert 'site-packages' in str(Path(saferevoke.__file__)); "
                "from saferevoke.docker_database import DockerDatabase; "
                "from saferevoke.adapters.providers import Auth0PermissionStore; "
                "from saferevoke.adapters.sqlite import SQLiteTestState; "
                "from saferevoke.flask_testing import FlaskTestIntegration; "
                "print('Clean wheel installation and console command verified')")
        subprocess.run([str(python), "-I", "-c", code], cwd=project, env=environment, check=True)


if __name__ == "__main__":
    main()
