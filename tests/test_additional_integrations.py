"""Application execution, cleanup, provider contracts, and cross-runtime checks."""
from copy import deepcopy
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import shutil
import sys
from threading import Thread
import unittest

from saferevoke.adapters.callback import CallbackAdapter, StateHooks
from saferevoke.adapters.command import CommandAdapter
from saferevoke.adapters.http import HTTPAdapter, decode_run
from saferevoke.adapters.providers import (
    Auth0PermissionBinding, Auth0PermissionStore, KeycloakRoleBinding, KeycloakRoleStore,
)
from saferevoke.adapters.web import record_access
from saferevoke.engine import SafeRevokeEngine
from saferevoke.model import AccessEvent, Grant, Lab, Workflow, WorkflowRun


def simple_lab():
    grant = Grant("g_orders", "alice", "identity", "alice", "orders", "read", "Read orders")
    workflow = Workflow("read_orders", "Orders", "", lambda ctx: None)
    return Lab({grant.id: grant}, {}, {workflow.id: workflow}, set(), {("orders", "read")}, {"read": 1}, {})


class CallbackTests(unittest.TestCase):
    def test_partial_mutation_failure_restores_real_state(self):
        lab = simple_lab()
        state = {"allowed": True, "orders": []}

        def deny(removed):
            state["allowed"] = False
            state["orders"].append("partial write")
            raise RuntimeError("injected failure")

        def restore(snapshot):
            state.clear()
            state.update(snapshot)

        hooks = StateHooks(lambda: deepcopy(state), deny, restore)
        adapter = CallbackAdapter(lab, hooks, lambda workflow: None, test_environment=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            SafeRevokeEngine(lab, adapter)._run_all({"g_orders"})
        self.assertEqual(state, {"allowed": True, "orders": []})

    def test_unknown_grant_rejected_before_application_changes(self):
        calls = []
        hooks = StateHooks(lambda: None, lambda removed: calls.append(removed), lambda snapshot: None)
        adapter = CallbackAdapter(simple_lab(), hooks, lambda workflow: None, test_environment=True)
        with self.assertRaisesRegex(ValueError, "Unknown grants"):
            adapter.deny({"typo"})
        self.assertEqual(calls, [])

    def test_test_environment_opt_in_required(self):
        hooks = StateHooks(lambda: None, lambda removed: None, lambda snapshot: None)
        with self.assertRaises(ValueError):
            CallbackAdapter(simple_lab(), hooks, lambda workflow: None)

    def test_unobserved_access_is_noop_and_not_a_permission_override(self):
        self.assertFalse(record_access("alice", "orders", "read", False))
        self.assertTrue(record_access("alice", "orders", "read", True))


class FrameworkTests(unittest.TestCase):
    def check_framework(self, framework):
        from examples.multi_framework.run import build_demo
        engine, state = build_demo(framework)
        original = deepcopy(state)
        shared = engine.simulate_grant("g_orders")
        outcomes = {item["id"]: item["outcome"] for item in shared["workflows"]}
        self.assertEqual(outcomes, {"orders_alice": "FAILED", "orders_bob": "FAILED", "refund": "UNCHANGED"})
        self.assertEqual(shared["classification"], "REQUIRED_ACCESS")
        fallback = engine.simulate_grant("g_refund")
        self.assertEqual(fallback["classification"], "UNSAFE_FALLBACK")
        refund = next(item for item in fallback["workflows"] if item["id"] == "refund")
        self.assertEqual(refund["outcome"], "FALLBACK")
        self.assertTrue(any(event["identity"] == "service" and event["allowed"] for event in refund["after"]["events"]))
        self.assertEqual(state, original)
        self.assertEqual(engine.analyze(), engine.analyze())
        self.assertEqual(state, original)

    @unittest.skipUnless(importlib.util.find_spec("flask"), "Flask not installed")
    def test_flask_application_shared_users_fallback_and_reset(self):
        self.check_framework("flask")

    @unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"), "FastAPI/httpx not installed")
    def test_fastapi_application_shared_users_fallback_and_reset(self):
        self.check_framework("fastapi")

    @unittest.skipUnless(importlib.util.find_spec("flask"), "Flask not installed")
    def test_flask_exception_resets_trace_and_application_data(self):
        from examples.multi_framework.run import build_demo
        engine, state = build_demo("flask")
        original = deepcopy(state)

        def crash(ctx):
            ctx.client.post("/refund")
            raise RuntimeError("application crash")

        engine.lab.workflows = {"crash": Workflow("crash", "Crash", "", crash)}
        with self.assertRaisesRegex(RuntimeError, "application crash"):
            engine._run_all({"g_refund"})
        self.assertEqual(state, original)
        # No workflow may inherit this failed workflow's active trace.
        self.assertTrue(record_access("alice", "orders", "read", True))

    @unittest.skipUnless(importlib.util.find_spec("flask"), "Flask not installed")
    def test_flask_rejects_missing_test_flag_and_unattributed_access(self):
        from flask import Flask
        from saferevoke.adapters.flask import FlaskAdapter
        app = Flask(__name__)
        lab = simple_lab()
        hooks = StateHooks(lambda: None, lambda removed: None, lambda snapshot: None)
        with self.assertRaises(ValueError):
            FlaskAdapter(app, lab, hooks)
        app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)

        @app.get("/orders")
        def orders():
            record_access("alice", "orders", "read", True)
            return {"orders": 2}

        lab.workflows["read_orders"] = Workflow("read_orders", "Orders", "", lambda ctx: ctx.response(ctx.client.get("/orders")))
        with self.assertRaisesRegex(ValueError, "Baseline workflows must pass"):
            SafeRevokeEngine(lab, FlaskAdapter(app, lab, hooks)).analyze()


class KeycloakContractTests(unittest.TestCase):
    def setUp(self):
        self.roles = [{"id": "r1", "name": "approver"}, {"id": "other", "name": "unrelated"}]
        self.calls = []

        def request(method, path, body):
            self.calls.append((method, path, deepcopy(body)))
            if method == "GET":
                return deepcopy(self.roles)
            if method == "DELETE":
                self.roles[:] = [role for role in self.roles if role["id"] not in {item["id"] for item in body}]
            elif method == "POST":
                self.roles.extend(deepcopy(body))

        self.request = request
        self.binding = KeycloakRoleBinding("g_refund", "user/1", "r1")

    def test_direct_role_is_removed_then_restored_without_altering_other_roles(self):
        store = KeycloakRoleStore(self.request, "test/realm", [self.binding], test_environment=True)
        original = deepcopy(self.roles)
        snapshot = store.snapshot()
        store.deny({"g_refund"})
        self.assertEqual(self.roles, [{"id": "other", "name": "unrelated"}])
        store.restore(snapshot)
        self.assertCountEqual(self.roles, original)
        self.assertIn("test%2Frealm/users/user%2F1/role-mappings/realm", self.calls[0][1])

    def test_client_roles_use_client_uuid_and_unknown_grants_do_not_mutate(self):
        binding = KeycloakRoleBinding("g_refund", "user", "r1", "client-uuid")
        store = KeycloakRoleStore(self.request, "test", [binding], test_environment=True)
        with self.assertRaises(ValueError):
            store.deny({"unknown"})
        self.assertEqual(self.calls, [])
        store.snapshot()
        self.assertTrue(self.calls[0][1].endswith("/clients/client-uuid"))

    def test_master_realm_and_missing_test_optin_are_rejected(self):
        for realm, enabled in (("master", True), ("test", False)):
            with self.assertRaises(ValueError):
                KeycloakRoleStore(self.request, realm, [self.binding], test_environment=enabled)
        self.assertEqual(self.calls, [])

    def test_restore_attempts_other_bindings_after_one_failure(self):
        calls = []

        def request(method, path, body):
            calls.append(path)
            if "/broken/" in path:
                raise RuntimeError("provider unavailable")
            return [{"id": "r1", "name": "approver"}]

        bindings = [KeycloakRoleBinding("broken", "broken", "r1"), KeycloakRoleBinding("ok", "ok", "r1")]
        store = KeycloakRoleStore(request, "test", bindings, test_environment=True)
        with self.assertRaisesRegex(RuntimeError, "broken"):
            store.restore({"broken": None, "ok": {"id": "r1", "name": "approver"}})
        self.assertTrue(any("/ok/" in path for path in calls))


class Auth0ContractTests(unittest.TestCase):
    def setUp(self):
        self.direct = True
        self.calls = []
        self.binding = Auth0PermissionBinding("g_refund", "auth0|user", "https://orders.example", "approve:refunds")

        def request(method, path, body):
            self.calls.append((method, path, deepcopy(body)))
            if method == "GET":
                sources = [{"source_type": "ROLE", "source_id": "staff"}]
                if self.direct:
                    sources.append({"source_type": "DIRECT"})
                return {"total": 1, "permissions": [{"resource_server_identifier": self.binding.api_identifier,
                    "permission_name": self.binding.permission_name, "sources": sources}]}
            self.direct = method == "POST"

        self.request = request

    def test_remove_only_direct_permission_and_restore_it_when_role_still_grants_access(self):
        store = Auth0PermissionStore(self.request, [self.binding], test_environment=True)
        snapshot = store.snapshot()
        store.deny({"g_refund"})
        self.assertFalse(self.direct)
        store.restore(snapshot)
        self.assertTrue(self.direct)
        deletions = [call for call in self.calls if call[0] == "DELETE"]
        self.assertEqual(deletions[0][2], {"permissions": [{"resource_server_identifier": self.binding.api_identifier,
                                                        "permission_name": "approve:refunds"}]})
        self.assertIn("auth0%7Cuser/permissions", deletions[0][1])

    def test_role_only_permission_is_never_recreated_as_direct_grant(self):
        self.direct = False
        store = Auth0PermissionStore(self.request, [self.binding], test_environment=True)
        snapshot = store.snapshot()
        store.deny({"g_refund"})
        store.restore(snapshot)
        self.assertFalse(self.direct)
        self.assertTrue(all(call[0] == "GET" for call in self.calls))

    def test_pagination_and_missing_source_evidence(self):
        calls = []

        def request(method, path, body):
            calls.append(path)
            item = {"resource_server_identifier": "other", "permission_name": "other"}
            if "page=0&" in path:
                return {"total": 101, "permissions": [item] * 100}
            return {"total": 101, "permissions": [{"resource_server_identifier": self.binding.api_identifier,
                    "permission_name": self.binding.permission_name}]}

        store = Auth0PermissionStore(request, [self.binding], test_environment=True)
        with self.assertRaisesRegex(ValueError, "source evidence"):
            store.snapshot()
        self.assertEqual(len(calls), 2)


class ProtocolTests(unittest.TestCase):
    def test_authenticated_http_roundtrip_and_cleanup_after_remote_exception(self):
        lab = simple_lab()
        token = secrets.token_urlsafe(32)
        state = {"allowed": True, "writes": 0}
        snapshots = {}
        crash = [False]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.dispatch()

            def do_POST(self):
                self.dispatch()

            def dispatch(self):
                status, body = 200, {}
                if self.headers.get("Authorization") != "Bearer " + token:
                    status = 401
                elif self.path == "/capabilities":
                    body = {"protocol": "saferevoke.v1", "test_environment": True}
                else:
                    data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    if self.path == "/snapshot":
                        key = secrets.token_urlsafe(16)
                        snapshots[key] = deepcopy(state)
                        body = {"snapshot": key}
                    elif self.path == "/deny":
                        state["allowed"] = "g_orders" not in data["grant_ids"]
                    elif self.path == "/run":
                        state["writes"] += 1
                        if crash[0]:
                            status = 500
                        else:
                            allowed = state["allowed"]
                            body = WorkflowRun("read_orders", allowed, "orders:2" if allowed else "forbidden",
                                [AccessEvent("read_orders", "alice", "orders", "read", allowed,
                                             ["g_orders"] if allowed else [], checkpoint="orders:read")], "ok").to_dict()
                    elif self.path == "/restore":
                        state.clear()
                        state.update(snapshots.pop(data["snapshot"]))
                    else:
                        status = 404
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with self.assertRaisesRegex(RuntimeError, "401"):
                HTTPAdapter(lab, url, token="wrong" * 8, test_environment=True)
            adapter = HTTPAdapter(lab, url, token=token, test_environment=True)
            engine = SafeRevokeEngine(lab, adapter)
            self.assertEqual(engine.simulate_grant("g_orders")["classification"], "REQUIRED_ACCESS")
            self.assertEqual(state, {"allowed": True, "writes": 0})
            crash[0] = True
            with self.assertRaisesRegex(RuntimeError, "500"):
                engine._run_all({"g_orders"})
            self.assertEqual(state, {"allowed": True, "writes": 0})
            self.assertEqual(snapshots, {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_nonlocal_harness_and_missing_test_optin_rejected_before_network(self):
        for url, enabled in (("https://example.com", True), ("http://127.0.0.1:1234", False),
                             ("http://127.0.0.1@example.com", True)):
            with self.assertRaises(ValueError):
                HTTPAdapter(simple_lab(), url, token="x" * 32, test_environment=enabled)

    def test_workflow_and_trace_validation(self):
        lab = simple_lab()
        workflow = lab.workflows["read_orders"]
        result = WorkflowRun(workflow.id, True, "orders:2", [AccessEvent(workflow.id, "alice", "orders", "read", True, ["g_orders"])], "ok").to_dict()
        self.assertTrue(decode_run(result, workflow, lab).success)
        result["events"][0]["grant_ids"] = []
        self.assertFalse(decode_run(result, workflow, lab).success)
        result["events"][0]["grant_ids"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "unknown"):
            decode_run(result, workflow, lab)
        result["workflow_id"] = "different"
        with self.assertRaises(ValueError):
            decode_run(result, workflow, lab)

    def test_command_timeout_still_restores_application(self):
        lab = simple_lab()
        restored = []
        hooks = StateHooks(lambda: "snapshot", lambda removed: None, lambda snapshot: restored.append(snapshot))
        adapter = CommandAdapter(lab, [sys.executable, "-c", "import time; time.sleep(10)"], hooks,
                                 test_environment=True, timeout=0.05)
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            SafeRevokeEngine(lab, adapter)._run_all({"g_orders"})
        self.assertEqual(restored, ["snapshot"])
        self.assertEqual(adapter.removed, set())


class CrossLanguageTests(unittest.TestCase):
    def check_language(self, language):
        from examples.cross_language.run import build_demo
        engine = build_demo(language)
        result = engine.simulate_grant("g_orders")
        self.assertEqual(result["classification"], "REQUIRED_ACCESS")
        self.assertEqual(result["workflows"][0]["before"]["output"], "orders:2")
        self.assertFalse(result["workflows"][0]["after"]["success"])
        self.assertEqual(engine.adapter.removed, set())

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_actual_nodejs_permission_check(self):
        self.check_language("node")

    @unittest.skipUnless(shutil.which("java"), "Java not installed")
    def test_actual_java_permission_check(self):
        self.check_language("java")


if __name__ == "__main__":
    unittest.main()
