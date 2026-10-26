"""Small Flask/FastAPI application with its own authorization and mutable data.

python -m examples.multi_framework.run flask
python -m examples.multi_framework.run fastapi
"""
from __future__ import annotations

from copy import deepcopy
import json
import sys

from saferevoke.adapters.callback import StateHooks
from saferevoke.adapters.web import record_access
from saferevoke.engine import SafeRevokeEngine
from saferevoke.model import Grant, Lab, Workflow


def build_demo(framework):
    # This is application-owned permission data, not SafeRevoke's Policy class.
    state = {"grants": {"g_orders", "g_refund", "g_service"}, "refunds": []}

    def authorized(identity, resource, action):
        sources = []
        if identity in {"alice", "bob"} and resource == "orders" and action == "read" and "g_orders" in state["grants"]:
            sources.append("g_orders")
        if identity == "alice" and resource == "refunds" and action == "approve" and "g_refund" in state["grants"]:
            sources.append("g_refund")
        if identity == "service" and "g_service" in state["grants"]:
            sources.append("g_service")
        return record_access(identity, resource, action, bool(sources), sources)

    def orders(user):
        return ({"orders": 2}, 200) if authorized(user, "orders", "read") else ({"error": "forbidden"}, 403)

    def refund():
        # Deliberately planted unsafe fallback: an app can conceal permission loss.
        if not authorized("alice", "refunds", "approve") and not authorized("service", "refunds", "approve"):
            return {"error": "forbidden"}, 403
        state["refunds"].append("refund-1")
        return {"approved": True}, 200

    if framework == "flask":
        from flask import Flask
        from saferevoke.adapters.flask import FlaskAdapter
        app = Flask(__name__)
        app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)
        app.add_url_rule("/orders/<user>", "orders", orders)
        app.add_url_rule("/refund", "refund", refund, methods=["POST"])
        adapter_class = FlaskAdapter
    elif framework == "fastapi":
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from saferevoke.adapters.fastapi import FastAPIAdapter
        app = FastAPI()
        app.state.saferevoke_test_environment = True

        @app.get("/orders/{user}")
        def order_endpoint(user: str):
            body, status = orders(user)
            return JSONResponse(body, status_code=status)

        @app.post("/refund")
        def refund_endpoint():
            body, status = refund()
            return JSONResponse(body, status_code=status)

        adapter_class = FastAPIAdapter
    else:
        raise ValueError("Choose flask or fastapi")

    def read_orders(ctx, user):
        return ctx.response(ctx.client.get(f"/orders/{user}"))

    def approve_refund(ctx):
        response = ctx.client.post("/refund")
        return ctx.response(response, side_effects={"refunds_created": len(state["refunds"])})

    workflows = [Workflow(f"orders_{user}", f"{user} orders", "Shared permission", lambda ctx, user=user: read_orders(ctx, user))
                 for user in ("alice", "bob")]
    workflows.append(Workflow("refund", "Approve refund", "Fallback evidence", approve_refund))
    grants = [
        Grant("g_orders", "staff", "role", "alice", "orders", "read", "Shared order access"),
        Grant("g_refund", "alice", "identity", "alice", "refunds", "approve", "Direct refund approval"),
        Grant("g_service", "service", "identity", "service", "*", "*", "Overprivileged service account"),
    ]
    lab = Lab({grant.id: grant for grant in grants}, {"alice": {"staff"}, "bob": {"staff"}},
              {workflow.id: workflow for workflow in workflows}, set(),
              {("orders", "read"), ("refunds", "approve"), ("users", "delete")},
              {"read": 1, "approve": 3, "delete": 5}, {})

    def restore(snapshot):
        state.clear()
        state.update(deepcopy(snapshot))

    hooks = StateHooks(lambda: deepcopy(state),
                       lambda removed: state["grants"].difference_update(removed), restore)
    return SafeRevokeEngine(lab, adapter_class(app, lab, hooks)), state


if __name__ == "__main__":
    engine, state = build_demo(sys.argv[1] if len(sys.argv) > 1 else "flask")
    result = engine.analyze()
    print(json.dumps({"summary": result["summary"], "restored_refunds": state["refunds"]}, indent=2))
