"""A test-only application with permission data owned by the app, not the SDK."""
from flask import Flask, jsonify, request

from saferevoke.adapters.web import record_access
from saferevoke.model import Grant


GRANTS = [
    Grant("g_orders", "staff", "role", "alice", "orders", "read", "Staff order access"),
    Grant("g_refund", "alice", "identity", "alice", "refunds", "approve", "Approve refunds"),
    Grant("g_service", "service", "identity", "service", "*", "*", "Broad service privileges"),
]
ROLES = {"alice": {"staff"}, "bob": {"staff"}}


def create_app(state):
    app = Flask(__name__)
    app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)

    def check(identity, resource, action):
        sources = [grant.id for grant in GRANTS
                   if grant.id in state["grants"]
                   and ((grant.principal_type == "identity" and grant.principal == identity)
                        or (grant.principal_type == "role" and grant.principal in ROLES.get(identity, set())))
                   and grant.resource in (resource, "*") and grant.action in (action, "*")]
        return record_access(identity, resource, action, bool(sources), sources)

    @app.get("/orders")
    def orders():
        # This header is solely a fixture identity mechanism for this local demo.
        identity = request.headers.get("X-Test-User", "")
        if not check(identity, "orders", "read"):
            return jsonify(error="forbidden"), 403
        return jsonify(orders=2)

    @app.post("/refund")
    def refund():
        identity = request.headers.get("X-Test-User", "")
        # Intentionally unsafe application behavior to make the evidence visible.
        if not check(identity, "refunds", "approve") and not check("service", "refunds", "approve"):
            return jsonify(error="forbidden"), 403
        state["refunds"].append("refund-1")
        return jsonify(approved=True)

    @app.get("/health")
    def health():
        return jsonify(healthy=True)

    return app
