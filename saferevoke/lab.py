from __future__ import annotations

from saferevoke.model import ExecutionContext, Grant, Lab, Workflow, WorkflowRun


def _sales_report(ctx: ExecutionContext) -> WorkflowRun:
    checkpoint = "sales-report/read-sales"
    if ctx.access("report_user", "sales_db", "read", checkpoint=checkpoint):
        return WorkflowRun("sales_report", True, "sales-total:42000", ctx.events, "Report generated with the dedicated account.")
    if ctx.access(
        "legacy_admin",
        "sales_db",
        "read",
        checkpoint=checkpoint,
        note="Application automatically tried its legacy fallback credential.",
    ):
        return WorkflowRun("sales_report", True, "sales-total:42000", ctx.events, "Report generated through a privileged fallback.")
    return WorkflowRun("sales_report", False, "", ctx.events, "No identity could read sales data.")


def _invoice_export(ctx: ExecutionContext) -> WorkflowRun:
    can_read = ctx.access("billing_user", "invoice_db", "read", checkpoint="invoice-export/read")
    can_write = ctx.access("billing_user", "export_store", "write", checkpoint="invoice-export/write")
    if can_read and can_write:
        return WorkflowRun("invoice_export", True, "invoice-export:12", ctx.events, "Invoice export completed.")
    return WorkflowRun("invoice_export", False, "", ctx.events, "Invoice export is missing a required permission.")


def _audit_view(ctx: ExecutionContext) -> WorkflowRun:
    if ctx.access("analyst_user", "audit_log", "read", checkpoint="audit-view/read"):
        return WorkflowRun("audit_view", True, "audit-events:7", ctx.events, "Audit events displayed.")
    return WorkflowRun("audit_view", False, "", ctx.events, "Audit log access was denied.")


def _customer_sync(ctx: ExecutionContext) -> WorkflowRun:
    if ctx.access("sync_worker", "customer_db", "write", checkpoint="customer-sync/write"):
        return WorkflowRun("customer_sync", True, "customers-updated:3", ctx.events, "Customer sync completed.")
    return WorkflowRun("customer_sync", False, "", ctx.events, "New customer updates are denied.")


def _operations_dashboard(ctx: ExecutionContext) -> WorkflowRun:
    ctx.access(
        "dashboard_user",
        "metrics_store",
        "read",
        checkpoint="operations-dashboard/optional-metrics",
        note="Optional enrichment; the approved dashboard result does not depend on it.",
    )
    return WorkflowRun("operations_dashboard", True, "service-status:healthy", ctx.events, "Operations dashboard displayed.")


def build_lab() -> Lab:
    grants = [
        Grant("g_report_read", "report_user", "identity", "report_user", "sales_db", "read", "Dedicated report reader"),
        Grant("g_admin_all", "legacy_admin", "identity", "legacy_admin", "*", "*", "Legacy administrator wildcard"),
        Grant("g_invoice_read", "billing_user", "identity", "billing_user", "invoice_db", "read", "Read invoices"),
        Grant("g_export_write", "billing_user", "identity", "billing_user", "export_store", "write", "Create invoice exports"),
        Grant("g_audit_direct", "analyst_user", "identity", "analyst_user", "audit_log", "read", "Direct audit permission"),
        Grant("g_audit_role", "security_analyst", "role", "analyst_user", "audit_log", "read", "Inherited audit permission"),
        Grant("g_sync_write", "sync_worker", "identity", "sync_worker", "customer_db", "write", "Authorize customer update jobs"),
        Grant("g_optional_metrics", "dashboard_user", "identity", "dashboard_user", "metrics_store", "read", "Optional dashboard enrichment"),
        Grant("g_unused_archive", "former_intern", "identity", "former_intern", "archive", "read", "Old access not exercised by a known workflow"),
    ]
    workflows = [
        Workflow("sales_report", "Daily sales report", "Reads sales data; contains an unsafe legacy-admin fallback.", _sales_report),
        Workflow("invoice_export", "Invoice export", "Requires both invoice read and export write access.", _invoice_export),
        Workflow("audit_view", "Audit viewer", "Has the same effective access through a direct grant and a role.", _audit_view),
        Workflow("customer_sync", "Customer sync", "Represents a queued operation authorized before revocation.", _customer_sync),
        Workflow("operations_dashboard", "Operations dashboard", "Uses optional metrics access while preserving its approved output without it.", _operations_dashboard),
    ]
    return Lab(
        grants={grant.id: grant for grant in grants},
        roles={"analyst_user": {"security_analyst"}},
        workflows={workflow.id: workflow for workflow in workflows},
        delayed_grants={"g_sync_write"},
        capability_universe={
            (grant.resource, grant.action)
            for grant in grants
            if grant.resource != "*" and grant.action != "*"
        },
        action_weights={"read": 1, "write": 3, "delete": 5, "admin": 8},
        expected_interactions={
            frozenset(("g_report_read", "g_admin_all")): "runtime-fallback",
            frozenset(("g_audit_direct", "g_audit_role")): "residual-access",
        },
    )
