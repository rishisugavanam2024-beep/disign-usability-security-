"""Django ModelBackend integration for synchronous workflows in a test database.

Permission decisions are made by Django. This adapter removes real many-to-many
permission records and uses transactions to restore the database after each run.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group, Permission
from django.db import transaction

from saferevoke.model import AccessEvent, ExecutionContext, Grant, Lab, Policy, Workflow, WorkflowRun


@dataclass(frozen=True)
class PermissionBinding:
    grant_id: str
    principal_type: str
    principal_pk: int | str
    permission_pk: int


@dataclass
class TraceSession:
    workflow_id: str
    events: list[AccessEvent]
    bindings: dict[str, PermissionBinding]
    operation_depth: int = 0
    uncertainties: set[str] = field(default_factory=set)


_trace: ContextVar[TraceSession | None] = ContextVar("saferevoke_django_trace", default=None)


class TracingModelBackend(ModelBackend):
    """Observe actual ModelBackend checks without changing their decisions."""

    def has_perm(self, user_obj, perm, obj=None):
        session = _trace.get()
        if session is not None:
            session.operation_depth += 1
        try:
            allowed = super().has_perm(user_obj, perm, obj=obj)
        finally:
            if session is not None:
                session.operation_depth -= 1
        if session is not None:
            matched = []
            permission = Permission.objects.select_related("content_type").filter(
                content_type__app_label=perm.split(".", 1)[0],
                codename=perm.split(".", 1)[-1],
            ).first()
            if permission is not None:
                resource, action = _resource_action(permission)
                for binding in session.bindings.values():
                    if binding.permission_pk != permission.pk:
                        continue
                    if binding.principal_type == "identity":
                        present = binding.principal_pk == user_obj.pk and user_obj.user_permissions.filter(pk=permission.pk).exists()
                    else:
                        present = user_obj.groups.filter(pk=binding.principal_pk, permissions=permission).exists()
                    if present and allowed:
                        matched.append(binding.grant_id)
            else:
                resource, action = perm, "unknown"
                session.uncertainties.add("A permission check could not be mapped to the inventory")
            if obj is not None:
                session.uncertainties.add("Object-level permission check observed")
            if allowed and not matched:
                session.uncertainties.add("An allowed permission had no inventoried grant source")
            session.events.append(AccessEvent(
                session.workflow_id, str(user_obj.get_username()), resource, action,
                allowed, sorted(matched), checkpoint=f"django-permission:{perm}",
                ordinal=len(session.events), note="Observed Django ModelBackend.has_perm decision.",
            ))
        return allowed

    def has_module_perms(self, user_obj, app_label):
        session = _trace.get()
        if session is not None:
            session.operation_depth += 1
        try:
            allowed = super().has_module_perms(user_obj, app_label)
        finally:
            if session is not None:
                session.operation_depth -= 1
        if session is not None:
            self._record_aggregate(user_obj, allowed, session, app_label)
        return allowed

    def get_all_permissions(self, user_obj, obj=None):
        session = _trace.get()
        if session is not None:
            session.operation_depth += 1
        try:
            permissions = super().get_all_permissions(user_obj, obj=obj)
        finally:
            if session is not None:
                session.operation_depth -= 1
        if session is not None and session.operation_depth == 0:
            if obj is not None:
                session.uncertainties.add("Object-level permission enumeration observed")
            self._record_aggregate(user_obj, bool(permissions), session)
        return permissions

    def get_user_permissions(self, user_obj, obj=None):
        permissions = super().get_user_permissions(user_obj, obj=obj)
        session = _trace.get()
        if session is not None and session.operation_depth == 0:
            if obj is not None:
                session.uncertainties.add("Object-level direct permission enumeration observed")
            self._record_aggregate(user_obj, bool(permissions), session, principal_type="identity")
        return permissions

    def get_group_permissions(self, user_obj, obj=None):
        permissions = super().get_group_permissions(user_obj, obj=obj)
        session = _trace.get()
        if session is not None and session.operation_depth == 0:
            if obj is not None:
                session.uncertainties.add("Object-level group permission enumeration observed")
            self._record_aggregate(user_obj, bool(permissions), session, principal_type="role")
        return permissions

    def get_user(self, user_id):
        user = super().get_user(user_id)
        session = _trace.get()
        if session is not None and user is not None and user.is_superuser:
            session.uncertainties.add("Superuser permission shortcuts may bypass tracing")
        return user

    @staticmethod
    def _record_aggregate(user_obj, allowed, session, app_label=None, principal_type=None):
        permissions = Permission.objects.all()
        if app_label is not None:
            permissions = permissions.filter(content_type__app_label=app_label)
        eligible = set(permissions.values_list("pk", flat=True))
        matched = []
        for binding in session.bindings.values():
            if principal_type is not None and binding.principal_type != principal_type:
                continue
            if binding.permission_pk not in eligible:
                continue
            if binding.principal_type == "identity":
                present = binding.principal_pk == user_obj.pk and user_obj.user_permissions.filter(pk=binding.permission_pk).exists()
            else:
                present = user_obj.groups.filter(pk=binding.principal_pk, permissions=binding.permission_pk).exists()
            if present and allowed:
                matched.append(binding.grant_id)
        if allowed and not matched:
            session.uncertainties.add("A permission enumeration had no inventoried source")
        operation = "module_permissions" if app_label is not None else "all_permissions"
        if principal_type is not None:
            operation = "user_permissions" if principal_type == "identity" else "group_permissions"
        session.events.append(AccessEvent(
            session.workflow_id, str(user_obj.get_username()), app_label or "*", operation,
            allowed, sorted(matched), checkpoint=f"django-{operation}:{app_label or '*'}",
            ordinal=len(session.events), phase="dependency",
            note=f"Observed Django ModelBackend.{operation} decision.",
        ))


def _resource_action(permission):
    resource = f"{permission.content_type.app_label}.{permission.content_type.model}"
    suffix = f"_{permission.content_type.model}"
    action = permission.codename.removesuffix(suffix)
    return resource, action


def discover_lab(usernames: list[str], workflows: list[Workflow]) -> tuple[Lab, dict[str, PermissionBinding]]:
    """Inventory direct/group grants for explicitly selected standard Django users."""
    if not usernames or len({item.id for item in workflows}) != len(workflows) or not workflows:
        raise ValueError("Select users and uniquely named workflows")
    users = get_user_model().objects.filter(**{f"{get_user_model().USERNAME_FIELD}__in": usernames})
    if users.count() != len(set(usernames)):
        raise ValueError("One or more selected users do not exist")
    grants = {}
    bindings = {}
    roles = {}
    for user in users:
        if user.is_superuser or not user.is_active:
            raise ValueError("Select active, non-superuser identities for this adapter")
        identity = str(user.get_username())
        roles[identity] = set()
        for permission in user.user_permissions.select_related("content_type"):
            grant_id = f"django:user:{user.pk}:permission:{permission.pk}"
            resource, action = _resource_action(permission)
            grants[grant_id] = Grant(grant_id, identity, "identity", identity, resource, action,
                                     f"{identity}: {permission.content_type.app_label}.{permission.codename} (direct)")
            bindings[grant_id] = PermissionBinding(grant_id, "identity", user.pk, permission.pk)
        for group in user.groups.all():
            role = f"django-group:{group.pk}"
            roles[identity].add(role)
            for permission in group.permissions.select_related("content_type"):
                grant_id = f"django:group:{group.pk}:permission:{permission.pk}"
                resource, action = _resource_action(permission)
                grants.setdefault(grant_id, Grant(grant_id, role, "role", identity, resource, action,
                                                  f"{group.name}: {permission.content_type.app_label}.{permission.codename} (group)"))
                bindings[grant_id] = PermissionBinding(grant_id, "role", group.pk, permission.pk)
    lab = Lab(grants, roles, {item.id: item for item in workflows}, set(),
              {(item.resource, item.action) for item in grants.values()},
              {"view": 1, "add": 3, "change": 3, "delete": 5}, {})
    return lab, bindings


class DjangoAdapter:
    """Rollback adapter for standard Django auth, one synchronous database connection."""

    def __init__(self, lab: Lab, bindings: dict[str, PermissionBinding]):
        if not getattr(settings, "SAFEREVOKE_TEST_ENVIRONMENT", False):
            raise ValueError("Enable SAFEREVOKE_TEST_ENVIRONMENT only in an isolated test environment")
        trace_backend = "saferevoke.adapters.django.TracingModelBackend"
        if settings.AUTHENTICATION_BACKENDS not in (
            [trace_backend], [trace_backend, "django.contrib.auth.backends.ModelBackend"],
        ):
            raise ValueError("Use the tracing backend, optionally followed by standard ModelBackend")
        self.lab = lab
        self.bindings = bindings
        if set(bindings) != set(lab.grants):
            raise ValueError("Every grant must have a Django permission binding")
        self._active_snapshot = None
        self.removed = set()

    def snapshot(self):
        if self._active_snapshot is not None:
            raise RuntimeError("An experiment is already active on this adapter")
        block = transaction.atomic()
        block.__enter__()
        self._active_snapshot = block
        return block

    def deny(self, grant_ids: set[str]) -> None:
        if self._active_snapshot is None:
            raise RuntimeError("Begin a snapshot before changing permissions")
        if grant_ids - self.bindings.keys():
            raise ValueError("Unknown Django permission grant")
        for grant_id in sorted(grant_ids):
            binding = self.bindings[grant_id]
            if binding.principal_type == "identity":
                principal = get_user_model().objects.get(pk=binding.principal_pk)
                principal.user_permissions.remove(binding.permission_pk)
            else:
                Group.objects.get(pk=binding.principal_pk).permissions.remove(binding.permission_pk)
        self.removed = set(grant_ids)

    def run(self, workflow: Workflow) -> WorkflowRun:
        if self._active_snapshot is None:
            raise RuntimeError("Begin a snapshot before running a workflow")
        context = ExecutionContext(workflow.id, Policy(self.lab, self.removed))
        session = TraceSession(workflow.id, context.events, self.bindings)
        token = _trace.set(session)
        try:
            result = workflow.runner(context)
            result.events = list(session.events)
            return result
        finally:
            _trace.reset(token)

    def restore(self, snapshot) -> None:
        if snapshot is not self._active_snapshot or snapshot is None:
            raise RuntimeError("Snapshot does not belong to the active experiment")
        try:
            transaction.set_rollback(True)
            snapshot.__exit__(None, None, None)
        finally:
            self._active_snapshot = None
            self.removed = set()
