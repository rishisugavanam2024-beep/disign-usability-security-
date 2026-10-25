"""Independent domain example: one stock-reader role supports two business tasks."""
from saferevoke.model import ExecutionContext, WorkflowRun


def check_stock(ctx: ExecutionContext) -> WorkflowRun:
    allowed = ctx.access("shop_service", "inventory", "read", checkpoint="stock/read")
    return WorkflowRun(ctx.workflow_id, allowed, "stock:12" if allowed else "", ctx.events,
                       "Stock checked." if allowed else "Stock access denied.")


def shipping_quote(ctx: ExecutionContext) -> WorkflowRun:
    allowed = ctx.access("shipping_service", "inventory", "read", checkpoint="shipping/stock")
    return WorkflowRun(ctx.workflow_id, allowed, "shipping:available" if allowed else "", ctx.events,
                       "Shipping availability checked." if allowed else "Cannot check shipping availability.")


def save_order(ctx: ExecutionContext) -> WorkflowRun:
    allowed = ctx.access("shop_service", "orders", "write", checkpoint="order/save")
    if allowed:
        ctx.state.setdefault("orders", []).append("order-1")
    return WorkflowRun(ctx.workflow_id, allowed, "order:saved" if allowed else "", ctx.events,
                       "Order saved." if allowed else "Order write denied.",
                       side_effects={"orders_created": len(ctx.state.get("orders", []))})


RUNNERS = {"check_stock": check_stock, "shipping_quote": shipping_quote, "save_order": save_order}
