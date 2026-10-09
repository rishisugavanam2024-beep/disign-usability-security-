from __future__ import annotations

from saferevoke.model import ExecutionContext, Grant, Lab, Workflow, WorkflowRun


def _incident_triage(ctx: ExecutionContext) -> WorkflowRun:
    checkpoint = "incident-triage/read-alert"
    if ctx.access("responder_bot", "alert_queue", "read", checkpoint=checkpoint):
        return WorkflowRun(
            "incident_triage", True, "incident:contained", ctx.events,
            "The responder used its dedicated alert permission.",
        )
    if ctx.access(
        "break_glass_admin",
        "alert_queue",
        "read",
        checkpoint=checkpoint,
        note="A compatibility handler silently selected the emergency credential.",
    ):
        return WorkflowRun(
            "incident_triage", True, "incident:contained", ctx.events,
            "The responder continued through an emergency credential.",
        )
    return WorkflowRun(
        "incident_triage", False, "", ctx.events, "The alert could not be read."
    )


def _evidence_review(ctx: ExecutionContext) -> WorkflowRun:
    if ctx.access(
        "forensic_user", "evidence_store", "read", checkpoint="evidence-review/read"
    ):
        return WorkflowRun(
            "evidence_review", True, "evidence-items:4", ctx.events,
            "Evidence was displayed.",
        )
    return WorkflowRun(
        "evidence_review", False, "", ctx.events, "Evidence access was denied."
    )


def _case_note(ctx: ExecutionContext) -> WorkflowRun:
    if ctx.access(
        "responder_bot", "case_store", "write", checkpoint="case-note/write"
    ):
        return WorkflowRun(
            "case_note", True, "case-note:saved", ctx.events, "The case note was saved."
        )
    return WorkflowRun(
        "case_note", False, "", ctx.events, "The case note could not be saved."
    )


def build_incident_lab() -> Lab:
    grants = [
        Grant("i_alert_read", "responder_bot", "identity", "responder_bot", "alert_queue", "read", "Read active alerts"),
        Grant("i_breakglass", "break_glass_admin", "identity", "break_glass_admin", "*", "*", "Emergency administrator wildcard"),
        Grant("i_case_write", "responder_bot", "identity", "responder_bot", "case_store", "write", "Write incident case notes"),
        Grant("i_evidence_direct", "forensic_user", "identity", "forensic_user", "evidence_store", "read", "Direct evidence access"),
        Grant("i_evidence_role", "forensics", "role", "forensic_user", "evidence_store", "read", "Forensics-role evidence access"),
    ]
    workflows = [
        Workflow("incident_triage", "Incident triage", "Reads an alert and has a hidden emergency fallback.", _incident_triage),
        Workflow("evidence_review", "Evidence review", "Reads evidence through overlapping grants.", _evidence_review),
        Workflow("case_note", "Case note", "Writes the response record.", _case_note),
    ]
    return Lab(
        grants={grant.id: grant for grant in grants},
        roles={"forensic_user": {"forensics"}},
        workflows={workflow.id: workflow for workflow in workflows},
        delayed_grants=set(),
        capability_universe={
            ("alert_queue", "read"),
            ("case_store", "write"),
            ("evidence_store", "read"),
            ("identity_directory", "admin"),
        },
        action_weights={"read": 1, "write": 3, "delete": 5, "admin": 8},
        expected_interactions={
            frozenset(("i_alert_read", "i_breakglass")): "runtime-fallback",
            frozenset(("i_evidence_direct", "i_evidence_role")): "residual-access",
        },
    )


def _publish_release(ctx: ExecutionContext) -> WorkflowRun:
    checkpoint = "publish-release/write"
    if ctx.access("release_bot", "public_store", "write", checkpoint=checkpoint):
        return WorkflowRun(
            "publish_release", True, "release:v12", ctx.events,
            "The release bot published with its narrow grant.",
        )
    if ctx.access(
        "platform_owner",
        "public_store",
        "write",
        checkpoint=checkpoint,
        note="The deploy library retried with a stored owner credential.",
    ):
        return WorkflowRun(
            "publish_release", True, "release:v12", ctx.events,
            "Publishing continued through the owner credential.",
        )
    return WorkflowRun(
        "publish_release", False, "", ctx.events, "The release could not be published."
    )


def _read_draft(ctx: ExecutionContext) -> WorkflowRun:
    if ctx.access("release_bot", "draft_store", "read", checkpoint="read-draft/read"):
        return WorkflowRun(
            "read_draft", True, "draft:v12", ctx.events, "The release draft was read."
        )
    return WorkflowRun(
        "read_draft", False, "", ctx.events, "The release draft could not be read."
    )


def build_publishing_lab() -> Lab:
    grants = [
        Grant("p_publish_write", "release_bot", "identity", "release_bot", "public_store", "write", "Publish approved releases"),
        Grant("p_owner_all", "platform_owner", "identity", "platform_owner", "*", "*", "Platform owner wildcard"),
        Grant("p_draft_read", "release_bot", "identity", "release_bot", "draft_store", "read", "Read release drafts"),
    ]
    workflows = [
        Workflow("publish_release", "Publish release", "Publishes a release and contains an owner fallback.", _publish_release),
        Workflow("read_draft", "Read draft", "Loads the approved release input.", _read_draft),
    ]
    return Lab(
        grants={grant.id: grant for grant in grants},
        roles={},
        workflows={workflow.id: workflow for workflow in workflows},
        delayed_grants=set(),
        capability_universe={
            ("draft_store", "read"),
            ("public_store", "write"),
            ("public_store", "delete"),
            ("deployment_control", "admin"),
        },
        action_weights={"read": 1, "write": 3, "delete": 5, "admin": 8},
        expected_interactions={
            frozenset(("p_publish_write", "p_owner_all")): "runtime-fallback",
        },
    )
