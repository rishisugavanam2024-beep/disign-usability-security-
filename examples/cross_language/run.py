"""python -m examples.cross_language.run node (or java)."""
import json
from pathlib import Path
import shutil
import sys

from saferevoke.adapters.callback import StateHooks
from saferevoke.adapters.command import CommandAdapter
from saferevoke.engine import SafeRevokeEngine
from saferevoke.model import Grant, Lab, Workflow


def build_demo(language):
    folder = Path(__file__).resolve().parent.parent / "cross_language"
    if language == "node":
        executable, filename = shutil.which("node"), "permission-demo.mjs"
    elif language == "java":
        executable, filename = shutil.which("java"), "PermissionDemo.java"
    else:
        raise ValueError("Choose node or java")
    if executable is None:
        raise RuntimeError(f"Install the {language} runtime to run this example")
    grant = Grant("g_orders", "alice", "identity", "alice", "orders", "read", "Read order list")
    workflow = Workflow("read_orders", "Read orders", "Executed in an external runtime", lambda ctx: None)
    lab = Lab({grant.id: grant}, {}, {workflow.id: workflow}, set(), {("orders", "read")}, {"read": 1}, {})
    # The examples have no persistent data; real services must supply real reset hooks.
    hooks = StateHooks(lambda: None, lambda removed: None, lambda snapshot: None)
    adapter = CommandAdapter(lab, [executable, str(folder / filename)], hooks, test_environment=True)
    return SafeRevokeEngine(lab, adapter)


if __name__ == "__main__":
    engine = build_demo(sys.argv[1] if len(sys.argv) > 1 else "node")
    print(json.dumps(engine.simulate_grant("g_orders"), indent=2))
