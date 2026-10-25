"""Load data-only JSON configurations using explicitly registered workflow code."""
from __future__ import annotations

import json
from pathlib import Path

from saferevoke.model import Grant, Lab, Workflow, WorkflowRunner


def load_lab(path: str | Path, runners: dict[str, WorkflowRunner]) -> Lab:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Configuration must specify schema_version: 1")
    grants = [Grant(**item) for item in data["grants"]]
    if len({grant.id for grant in grants}) != len(grants):
        raise ValueError("Grant IDs must be unique")
    for grant in grants:
        if grant.principal_type not in {"identity", "role"}:
            raise ValueError(f"Invalid principal_type for {grant.id}")
        if not all(isinstance(value, str) and value for value in vars(grant).values()):
            raise ValueError("Every grant field must be a nonempty string")
    workflows = []
    for item in data["workflows"]:
        runner_id = item["runner"]
        if runner_id not in runners:
            raise ValueError(f"Workflow runner is not registered: {runner_id}")
        workflows.append(Workflow(
            item["id"], item["name"], item.get("description", ""), runners[runner_id],
            item.get("expected_output"), item.get("expected_side_effects", {}),
        ))
    if not workflows or len({item.id for item in workflows}) != len(workflows):
        raise ValueError("At least one workflow with a unique ID is required")
    capabilities = {tuple(item) for item in data["capability_universe"]}
    if any(len(item) != 2 or not all(isinstance(v, str) for v in item) for item in capabilities):
        raise ValueError("Capabilities must be [resource, action] pairs")
    weights = data.get("action_weights", {"read": 1, "write": 3, "delete": 5, "admin": 8})
    if any(type(value) is not int or value < 0 for value in weights.values()):
        raise ValueError("Action weights must be nonnegative integers")
    return Lab(
        {grant.id: grant for grant in grants},
        {identity: set(roles) for identity, roles in data.get("roles", {}).items()},
        {workflow.id: workflow for workflow in workflows}, set(), capabilities, weights, {},
    )
