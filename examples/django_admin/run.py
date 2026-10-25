"""Run with: python -m examples.django_admin.run --output reports/django-admin"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def setup():
    selected_settings = os.environ.setdefault("DJANGO_SETTINGS_MODULE", "examples.django_admin.settings")
    if selected_settings != "examples.django_admin.settings":
        raise RuntimeError("Run this isolated demonstration in a fresh process with its own settings")
    import django
    django.setup()
    from django.conf import settings
    if settings.DATABASES["default"]["NAME"] != ":memory:":
        raise RuntimeError("This demonstration requires its disposable in-memory database")
    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)


def build_integration():
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from django.test import Client
    from saferevoke.adapters.django import DjangoAdapter, discover_lab
    from saferevoke.engine import SafeRevokeEngine
    from saferevoke.model import Workflow, WorkflowRun

    users = get_user_model()
    alice, _ = users.objects.get_or_create(username="alice", defaults={"is_staff": True})
    bob, _ = users.objects.get_or_create(username="bob", defaults={"is_staff": True})
    operators, _ = Group.objects.get_or_create(name="operators")
    auditors, _ = Group.objects.get_or_create(name="auditors")
    view_users = Permission.objects.get(content_type__app_label="auth", codename="view_user")
    view_groups = Permission.objects.get(content_type__app_label="auth", codename="view_group")
    add_group = Permission.objects.get(content_type__app_label="auth", codename="add_group")
    operators.permissions.add(view_users)
    auditors.permissions.add(view_groups)
    alice.groups.add(operators, auditors)
    bob.groups.add(operators)
    alice.user_permissions.add(view_groups, add_group)

    def list_page(identity, model):
        def run(ctx):
            # A fresh request and user prevent stale Django permission caches.
            client = Client()
            client.force_login(users.objects.get(username=identity))
            response = client.get(f"/admin/auth/{model}/")
            allowed = response.status_code == 200
            output = f"{model}:listed" if allowed else f"HTTP:{response.status_code}"
            return WorkflowRun(ctx.workflow_id, allowed, output, ctx.events,
                               f"Django admin returned HTTP {response.status_code}.")
        return run

    def add_group_page(ctx):
        client = Client()
        client.force_login(users.objects.get(username="alice"))
        # The standard Django test client omits CSRF enforcement. Authorization
        # still runs in the unmodified upstream admin view.
        response = client.post("/admin/auth/group/add/", {"name": "workflow_created_group"})
        created = Group.objects.filter(name="workflow_created_group").count()
        success = response.status_code == 302 and created == 1
        return WorkflowRun(ctx.workflow_id, success, "group:created" if success else f"HTTP:{response.status_code}",
                           ctx.events, f"Django admin returned HTTP {response.status_code}.",
                           side_effects={"groups_created": created})

    workflows = [
        Workflow("alice_list_users", "Alice lists user accounts", "Existing Django admin user list.", list_page("alice", "user"), "user:listed"),
        Workflow("bob_list_users", "Bob lists user accounts", "Same shared role, separate staff identity.", list_page("bob", "user"), "user:listed"),
        Workflow("alice_list_groups", "Alice lists groups", "Direct and group-based view permissions overlap.", list_page("alice", "group"), "group:listed"),
        Workflow("alice_add_group", "Alice creates a group", "POST to Django's original group-add view.", add_group_page, "group:created", {"groups_created": 1}),
    ]
    lab, bindings = discover_lab(["alice", "bob"], workflows)
    adapter = DjangoAdapter(lab, bindings)
    return SafeRevokeEngine(lab, adapter)


def collect_results(engine):
    from django.contrib.auth.models import Group
    from saferevoke.adapters.django import discover_lab

    before, _ = discover_lab(["alice", "bob"], list(engine.lab.workflows.values()))
    report = engine.analyze()
    by_description = {item.description: item.id for item in engine.lab.grants.values()}
    shared_id = next(value for key, value in by_description.items() if key.startswith("operators:"))
    direct_id = next(value for key, value in by_description.items() if key.startswith("alice: auth.view_group"))
    add_id = next(value for key, value in by_description.items() if key.startswith("alice: auth.add_group"))
    demonstrations = {
        "shared_group_permission": engine.simulate_grant(shared_id),
        "duplicate_direct_permission": engine.simulate_grant(direct_id),
        "required_write_permission": engine.simulate_grant(add_id),
    }
    after, _ = discover_lab(["alice", "bob"], list(engine.lab.workflows.values()))
    restored = before.grants == after.grants and before.roles == after.roles
    no_leftover_write = not Group.objects.filter(name="workflow_created_group").exists()
    if not restored or not no_leftover_write:
        raise RuntimeError("The integration did not restore its database")
    return {
        "application": "Django built-in administration application",
        "authorization": "Actual Django ModelBackend and ORM permission records",
        "scope": "Controlled test accounts against upstream admin views; not an independent storefront or a vulnerability finding.",
        "permissions_restored": restored,
        "workflow_writes_rolled_back": no_leftover_write,
        "analysis": report,
        "demonstrations": demonstrations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/django-admin")
    args = parser.parse_args()
    setup()
    engine = build_integration()
    results = collect_results(engine)
    import django
    results["django_version"] = django.get_version()
    from saferevoke.report import render_html, render_json
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "evidence.json").write_text(render_json(results), encoding="utf-8")
    (destination / "report.html").write_text(render_html(results["analysis"]), encoding="utf-8")
    summary = {
        "django_version": django.get_version(),
        "shared_permission_affected_tasks": results["demonstrations"]["shared_group_permission"]["affected_workflows"],
        "shared_permission_failed_tasks": [
            item["id"] for item in results["demonstrations"]["shared_group_permission"]["workflows"]
            if item["outcome"] == "FAILED"
        ],
        "direct_permission_result": results["demonstrations"]["duplicate_direct_permission"]["classification"],
        "write_permission_result": results["demonstrations"]["required_write_permission"]["classification"],
        "permissions_restored": results["permissions_restored"],
        "workflow_writes_rolled_back": results["workflow_writes_rolled_back"],
        "output": str(destination.resolve()),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
