from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Grant:
    id: str
    principal: str
    principal_type: str
    probe_identity: str
    resource: str
    action: str
    description: str


@dataclass
class AccessEvent:
    workflow: str
    identity: str
    resource: str
    action: str
    allowed: bool
    grant_ids: list[str] = field(default_factory=list)
    checkpoint: str = ""
    ordinal: int = 0
    phase: str = "request"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkflowRun:
    workflow_id: str
    success: bool
    output: str
    events: list[AccessEvent]
    message: str

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "output": self.output,
            "events": [event.to_dict() for event in self.events],
            "message": self.message,
        }


WorkflowRunner = Callable[["ExecutionContext"], WorkflowRun]


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    description: str
    runner: WorkflowRunner


@dataclass
class Lab:
    grants: dict[str, Grant]
    roles: dict[str, set[str]]
    workflows: dict[str, Workflow]
    delayed_grants: set[str]
    capability_universe: set[tuple[str, str]]
    action_weights: dict[str, int]
    expected_interactions: dict[frozenset[str], str]


class Policy:
    def __init__(self, lab: Lab, removed: set[str] | None = None):
        self.lab = lab
        self.removed = removed or set()

    def grants_for(self, identity: str, resource: str, action: str) -> list[Grant]:
        roles = self.lab.roles.get(identity, set())
        matches: list[Grant] = []
        for grant in self.lab.grants.values():
            if grant.id in self.removed:
                continue
            principal_match = (
                grant.principal_type == "identity" and grant.principal == identity
            ) or (grant.principal_type == "role" and grant.principal in roles)
            resource_match = grant.resource in {resource, "*"}
            action_match = grant.action in {action, "*"}
            if principal_match and resource_match and action_match:
                matches.append(grant)
        return matches

    def privilege_scope(self, identity: str) -> set[tuple[str, str]]:
        return {
            capability
            for capability in self.lab.capability_universe
            if self.grants_for(identity, capability[0], capability[1])
        }

    def scope_metrics(self, identity: str) -> dict:
        capabilities = self.privilege_scope(identity)
        impact_score = sum(
            self.lab.action_weights.get(action, 1)
            for _, action in capabilities
        )
        return {
            "identity": identity,
            "capability_count": len(capabilities),
            "impact_score": impact_score,
            "capabilities": [
                {"resource": resource, "action": action}
                for resource, action in sorted(capabilities)
            ],
        }


class ExecutionContext:
    def __init__(self, workflow_id: str, policy: Policy):
        self.workflow_id = workflow_id
        self.policy = policy
        self.events: list[AccessEvent] = []

    def access(
        self,
        identity: str,
        resource: str,
        action: str,
        checkpoint: str | None = None,
        phase: str = "request",
        note: str = "",
    ) -> bool:
        grants = self.policy.grants_for(identity, resource, action)
        self.events.append(
            AccessEvent(
                workflow=self.workflow_id,
                identity=identity,
                resource=resource,
                action=action,
                allowed=bool(grants),
                grant_ids=[grant.id for grant in grants],
                checkpoint=checkpoint or f"{resource}:{action}",
                ordinal=len(self.events),
                phase=phase,
                note=note,
            )
        )
        return bool(grants)
