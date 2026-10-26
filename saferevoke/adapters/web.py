"""Request execution and tracing shared by Flask and FastAPI connectors."""
from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
import json

from saferevoke.adapters.callback import CallbackAdapter, StateHooks
from saferevoke.model import AccessEvent, WorkflowRun


_active: ContextVar["WebContext | None"] = ContextVar("saferevoke_web", default=None)


def record_access(identity: str, resource: str, action: str, allowed: bool,
                  grant_ids=(), *, checkpoint: str | None = None) -> bool:
    """Observe the application's real authorization decision; never override it.

    Call immediately after the real permission check, including denied checks.
    Outside a SafeRevoke workflow this is a no-op returning the same decision.
    """
    if type(allowed) is not bool:
        raise TypeError("Authorization decision must be a boolean")
    context = _active.get()
    if context is not None:
        sources = list(grant_ids) if allowed else []
        for grant_id in sources:
            grant = context.lab.grants.get(grant_id)
            if grant is None or grant.resource not in (resource, "*") or grant.action not in (action, "*"):
                raise ValueError("Access trace references an unknown or mismatched grant")
            if not ((grant.principal_type == "identity" and grant.principal == identity)
                    or (grant.principal_type == "role" and grant.principal in context.lab.roles.get(identity, set()))):
                raise ValueError("Access trace grant does not belong to this identity")
        if allowed and not sources:
            context.errors.add("Allowed access has no inventoried grant source")
        context.events.append(AccessEvent(
            context.workflow_id, identity, resource, action, allowed, sources,
            checkpoint or f"{resource}:{action}", len(context.events),
            note="Observed application authorization decision.",
        ))
    return allowed


class WebContext:
    """A workflow receives a real test client, not a replacement policy engine."""

    def __init__(self, workflow_id, lab, client):
        self.workflow_id, self.lab, self.client = workflow_id, lab, client
        self.events: list[AccessEvent] = []
        self.errors: set[str] = set()

    def response(self, response, *, expected_status=200, output=None,
                 side_effects=None) -> WorkflowRun:
        if output is None:
            text = response.get_data(as_text=True) if hasattr(response, "get_data") else response.text
            try:
                output = json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
            except (ValueError, TypeError):
                output = text
        return WorkflowRun(
            self.workflow_id, response.status_code == expected_status, str(output),
            deepcopy(self.events), f"HTTP:{response.status_code}",
            deepcopy(side_effects if side_effects is not None else {}),
        )


class WebAdapter(CallbackAdapter):
    def __init__(self, lab, hooks: StateHooks, client_factory, *, test_environment):
        self.client_factory = client_factory
        super().__init__(lab, hooks, self._execute, test_environment=test_environment)

    def _execute(self, workflow):
        # ContextVar values propagate into FastAPI's TestClient worker thread.
        with self.client_factory() as client:
            context = WebContext(workflow.id, self.lab, client)
            token = _active.set(context)
            try:
                result = workflow.runner(context)
            finally:
                _active.reset(token)
            if not isinstance(result, WorkflowRun):
                raise TypeError("Web workflow must return context.response(...) or WorkflowRun")
            result = deepcopy(result)
            result.events = deepcopy(context.events)
            result.validation_errors.extend(sorted(context.errors))
            if context.errors:
                result.success = False
            return result
