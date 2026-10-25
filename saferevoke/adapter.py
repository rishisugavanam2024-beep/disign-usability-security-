"""Application boundary: adapters own permission changes, traces and state reset."""
from __future__ import annotations

from typing import Any, Protocol
from copy import deepcopy

from saferevoke.model import ExecutionContext, Lab, Policy, Workflow, WorkflowRun


class ApplicationAdapter(Protocol):
    def snapshot(self) -> Any: ...
    def deny(self, grant_ids: set[str]) -> None: ...
    def run(self, workflow: Workflow) -> WorkflowRun: ...
    def restore(self, snapshot: Any) -> None: ...


class InMemoryAdapter:
    """Reset policies and Python application data; external adapters reset real stores."""

    def __init__(self, lab: Lab, initial_state: dict | None = None):
        self.lab = lab
        self.removed: set[str] = set()
        self.state = deepcopy(initial_state or {})

    def snapshot(self) -> dict:
        return {"removed": set(self.removed), "state": deepcopy(self.state)}

    def deny(self, grant_ids: set[str]) -> None:
        unknown = grant_ids - self.lab.grants.keys()
        if unknown:
            raise ValueError(f"Unknown grants: {sorted(unknown)}")
        self.removed = set(grant_ids)

    def run(self, workflow: Workflow) -> WorkflowRun:
        context = ExecutionContext(workflow.id, Policy(self.lab, self.removed))
        context.state = self.state
        return deepcopy(workflow.runner(context))

    def restore(self, snapshot: dict) -> None:
        self.removed = set(snapshot["removed"])
        self.state = deepcopy(snapshot["state"])
