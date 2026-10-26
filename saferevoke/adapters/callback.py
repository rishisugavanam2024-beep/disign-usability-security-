"""Connect application-owned permission changes, execution, and cleanup."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from saferevoke.model import Lab, Workflow, WorkflowRun


@dataclass(frozen=True)
class StateHooks:
    """Callbacks must cover permissions AND all workflow side effects."""

    snapshot: Callable[[], Any]
    deny: Callable[[set[str]], None]
    restore: Callable[[Any], None]


class CallbackAdapter:
    """An explicit integration boundary for custom Python permission systems.

    The caller supplies real application execution and state restoration. This
    adapter neither discovers arbitrary permissions nor sandboxes the callbacks.
    """

    def __init__(self, lab: Lab, hooks: StateHooks,
                 run: Callable[[Workflow], WorkflowRun], *, test_environment=False):
        if test_environment is not True:
            raise ValueError("Use an isolated test environment and explicitly enable it")
        self.lab, self.hooks, self.runner = lab, hooks, run

    def snapshot(self):
        # Opaque transaction handles remain owned by the application's hooks.
        return self.hooks.snapshot()

    def deny(self, grant_ids: set[str]) -> None:
        unknown = grant_ids - self.lab.grants.keys()
        if unknown:
            raise ValueError(f"Unknown grants: {sorted(unknown)}")
        self.hooks.deny(set(grant_ids))

    def run(self, workflow: Workflow) -> WorkflowRun:
        result = self.runner(workflow)
        if not isinstance(result, WorkflowRun) or result.workflow_id != workflow.id:
            raise ValueError("Runner must return the matching WorkflowRun")
        return deepcopy(result)

    def restore(self, snapshot) -> None:
        self.hooks.restore(snapshot)
