"""Run application-owned Node.js/Java/etc. test commands without a shell."""
from __future__ import annotations

import json
import subprocess

from saferevoke.adapters.callback import CallbackAdapter
from saferevoke.adapters.http import decode_run


class CommandAdapter(CallbackAdapter):
    """Test command arguments: WORKFLOW_ID followed by zero or more GRANT_IDs.

    The command must apply those denials in its own isolated test application,
    run the named workflow, and write exactly one WorkflowRun JSON to stdout.
    This is a subprocess boundary, not an OS sandbox or automatic integration.
    """

    def __init__(self, lab, command, hooks, *, test_environment=False,
                 cwd=None, timeout=30):
        if isinstance(command, str) or not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError("Pass a nonempty argument list, not a shell command")
        if timeout <= 0:
            raise ValueError("Positive command timeout required")
        self.command, self.cwd, self.timeout = list(command), cwd, timeout
        self.removed = set()
        super().__init__(lab, hooks, self._execute, test_environment=test_environment)

    def snapshot(self):
        return self.hooks.snapshot(), set(self.removed)

    def deny(self, grant_ids):
        super().deny(grant_ids)
        self.removed = set(grant_ids)

    def restore(self, snapshot):
        application_state, removed = snapshot
        try:
            self.hooks.restore(application_state)
        finally:
            self.removed = set(removed)

    def _execute(self, workflow):
        try:
            result = subprocess.run(
                [*self.command, workflow.id, *sorted(self.removed)], cwd=self.cwd,
                capture_output=True, text=True, encoding="utf-8", timeout=self.timeout,
                check=False, shell=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Test command timed out; application cleanup is required") from None
        if result.returncode:
            # stderr can contain application credentials; do not copy it to reports.
            raise RuntimeError(f"Test command exited with status {result.returncode}")
        try:
            return decode_run(json.loads(result.stdout), workflow, self.lab)
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError("Test command must return a valid WorkflowRun JSON") from error
