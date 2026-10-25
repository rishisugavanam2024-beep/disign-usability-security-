# Django admin integration

## What is being tested

This integration runs Django's installed, unmodified administration application:
the account list, group list and group-creation views from `django.contrib.admin`.
Permissions are read from and removed from Django's actual database tables.
`TracingModelBackend` subclasses the standard Django authorization backend and
records its decisions without replacing those decisions with SafeRevoke's policy.

The accounts and group assignments are controlled test fixtures. This is a real
framework integration; it is not a separately maintained shopping application,
production validation, or evidence of a newly discovered Django vulnerability.
The authorization outcomes below are expected Django behavior.

## Run in VS Code

From the SafeRevoke project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-django.txt
.\.venv\Scripts\python.exe -m examples.django_admin.run --output reports/django-admin
```

No server, Docker, database service or downloaded customer database is required.
The harness creates and migrates a fresh in-memory SQLite database. It sends
requests through Django's test client into the real admin views, prints results
and writes `reports/django-admin/report.html` and `evidence.json`.

The test client logs in fixture identities using `force_login`; this tests
authorization rather than password login. Its default CSRF checks are disabled
for the test POST. The integration therefore makes no claim about login or CSRF.

## Verified scenarios

| Change | Observed result |
|---|---|
| Remove `operators` group's `auth.view_user` | Both Alice and Bob receive HTTP 403 when opening the admin user list. |
| Same removal, Alice opens the group list | HTTP 200 remains; permission checks for navigation change. SafeRevoke reports a changed path. |
| Remove Alice's direct `auth.view_group` | Group-list access remains through `auditors`; classified as partial removal. |
| Remove Alice's `auth.add_group` | Admin group creation is blocked; classified as required access. |
| Restore after every workflow | Permission assignments return and the test-created group does not remain. |
| Raise an exception after a database write | Both the write and permission mutation roll back, and a subsequent baseline passes. |

The first verified run used Django 5.2.18. These tests do not demonstrate a
privileged credential fallback in upstream Django. That mechanism remains
demonstrated by the synthetic labs until exercised in an independent application
that actually contains such behavior.

## Reuse in another Django project

The reusable code is `saferevoke/adapters/django.py`. In the project's isolated
test settings, configure:

```python
AUTHENTICATION_BACKENDS = ["saferevoke.adapters.django.TracingModelBackend"]
SAFEREVOKE_TEST_ENVIRONMENT = True
```

Once Django has been initialized and the test database prepared:

```python
from saferevoke.adapters.django import discover_lab, DjangoAdapter
from saferevoke.engine import SafeRevokeEngine

# Supply Workflow instances that drive your application's own views and check
# outputs and side effects. Each must return a WorkflowRun.
lab, bindings = discover_lab(["your_test_employee"], your_workflows)
report = SafeRevokeEngine(lab, DjangoAdapter(lab, bindings)).analyze()
```

Permission IDs, principals and group membership are discovered from the selected
users' real records. Workflow definitions are the application-specific part.
For example, a shop may provide a refund workflow and a school may provide an
edit-grade workflow. Both can reuse the same direct/group permission inventory,
mutation, tracing and database rollback adapter if they use the supported backend.

## Current compatibility boundary

- Supports synchronous code, standard Django `ModelBackend`, active non-superuser
  identities, direct permissions and Django group permissions on the default DB.
- Permission checks must reach the tracing backend. Superuser shortcuts, custom
  backends, object-level access libraries and async authorization are not covered.
  The inventory rejects selected superusers; workflows must not switch to an
  unselected superuser or bypass the backend.
- Workflow requests must load fresh users after permission changes. Django caches
  permissions on user instances; the included harness uses fresh request clients.
- A transaction rolls back the default database on the same thread/connection.
  It does not restore email, uploads, background workers, other database aliases,
  external services or cached model instances. Disable or separately isolate those
  side effects in an integration test environment.
- Do not commit the adapter's enclosing transaction from a workflow. Each workflow
  runs independently and returns evidence before rollback.
- Permission scope scoring covers the inventoried capabilities and configured
  identities. It is not an exhaustive inventory of all authorization paths.

## Sources

- [Django permissions and permission caching](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
- [Django database transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
- [Django source repository](https://github.com/django/django)
