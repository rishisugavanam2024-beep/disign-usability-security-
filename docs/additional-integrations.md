# Additional application integrations

These connectors have been added locally to the source tree. They are not yet a
new PyPI release. Existing package metadata and the release workflow were left
unchanged while the current release is being handled separately.

SafeRevoke can now drive several kinds of applications, but installing a package
does not discover an arbitrary application's permissions or business workflows.
The developer still supplies a permission inventory, approved workflows, tracing,
and restoration of test data. Docker is not required by these connectors.

| Connector | What is implemented | Validation |
| --- | --- | --- |
| Generic Python | `CallbackAdapter` and `StateHooks` for application-owned snapshot, deny, execute and restore | Partial-change cleanup and unknown-grant rejection |
| Flask | `FlaskAdapter`, real Flask test client and permission-check observation | Shared permission affecting two users, fallback to a service account, exception cleanup and repeatability |
| FastAPI | `FastAPIAdapter`, real TestClient with application lifespan and trace context propagation | Shared permission, service-account fallback and repeatability |
| Node.js | `CommandAdapter` running an application-owned test command | Actual Node.js process performs a permission check before and after denial |
| Java | The same command protocol, plus a standalone Java example | Actual Java process performs a permission check before and after denial |
| HTTP / other languages | Authenticated loopback `HTTPAdapter` implementing the `saferevoke.v1` test-harness contract | Real local HTTP requests, authentication rejection and cleanup after server errors |
| Keycloak | `KeycloakRoleStore` for selected direct user realm/client-role assignments | API contract tests with simulated responses; no live Keycloak realm tested |
| Auth0 | `Auth0PermissionStore` for selected directly assigned user permissions, including pagination and source checks | API contract tests with simulated responses; no live Auth0 tenant tested |

The Node.js and Java examples are test-command bridges, not published npm or Maven
SDKs and not automatic Express or Spring Security adapters. The framework examples
are small local applications written for these checks, not independent upstream
application validations. These distinctions matter when presenting the project.
The existing `pytest --saferevoke` command still targets Django. Flask now also has
a separate [existing-test runner](flask-pytest.md), loaded with
`-p saferevoke.flask_pytest`. Other new connectors use the Python
`SafeRevokeEngine` API shown below. The Django plugin's behavior is unchanged.

## Run the examples

From the repository root, use an activated Python virtual environment:

```bash
pip install -e .
pip install -r requirements-integrations.txt
python -m examples.multi_framework.run flask
python -m examples.multi_framework.run fastapi
python -m examples.cross_language.run node
python -m examples.cross_language.run java
python -m unittest discover -s tests -p test_additional_integrations.py -v
```

Node.js must be on PATH for its example. Java source-file execution requires a
JDK; the example targets Java 17 or later. Framework and runtime checks skip when
their dependencies are absent, so inspect the test result before claiming they
have been verified. The Flask/FastAPI examples should report `REQUIRED_ACCESS`
for the shared order permission and `UNSAFE_FALLBACK` for the refund permission.
Their `restored_refunds` value must be an empty list after the experiments.

## Flask and FastAPI integration

Each application's existing authorization function keeps making the decision.
Add observation immediately after that check, supplying the grant IDs that
actually allowed the operation. Trace both successful and denied checks:

```python
from saferevoke.adapters.web import record_access

def can_read_orders(user):
    sources = permission_store.actual_sources(user, "orders", "read")
    return record_access(user.username, "orders", "read", bool(sources), sources)
```

This is a hook example: `permission_store` is supplied by the application, not a
SafeRevoke discovery service. IDs must match the configured `Lab`. An allowed
check without grant-source evidence invalidates the baseline rather than being
treated as evidence of safety. Grant ownership and resource/action are checked.
Always use the user returned by the application's actual authentication system.

Connect three application-owned operations through `StateHooks`:

```python
from saferevoke.adapters.callback import StateHooks
from saferevoke.adapters.flask import FlaskAdapter
from saferevoke.engine import SafeRevokeEngine

hooks = StateHooks(snapshot_test_state, remove_test_grants, restore_test_state)
app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)
engine = SafeRevokeEngine(lab, FlaskAdapter(app, lab, hooks))
report = engine.analyze()
```

For FastAPI, set `app.state.saferevoke_test_environment = True` and construct
`FastAPIAdapter(app, lab, hooks)` instead. Importing the generic/HTTP connectors
does not import either framework. Workflow runners receive a context with the
real framework test client:

```python
def refund_workflow(ctx):
    response = ctx.client.post("/refund", headers=test_user_headers)
    return ctx.response(response, expected_status=200,
                        side_effects={"refunds_created": count_test_refunds()})
```

Normalize timestamps, generated IDs and other nondeterministic output yourself.
Include meaningful side effects, not only HTTP status. Snapshot and restore must
cover database writes, permission rows, sessions, caches, queues and any external
effects the selected workflow can reach. Framework test clients are not database
rollback mechanisms or OS sandboxes. The examples reset only their own in-memory
stores. Initialization/lifespan state must also be covered by the application
hooks. Spawned processes/background jobs need their own tracing and reset.

## Custom Python applications

`CallbackAdapter(lab, hooks, run_workflow, test_environment=True)` calls the
application's `run_workflow(workflow)` and requires a matching `WorkflowRun`.
Callbacks can wrap existing application tests. State reset remains explicit.
The engine invokes restore even when permission removal or execution raises.
Restoration failure stops further testing. An opt-in flag is a configuration
guard; it cannot prove that a callback or database is safe or isolated.

## Node.js and Java commands

`CommandAdapter(lab, [executable, test_runner_path], hooks,
test_environment=True, cwd=..., timeout=30)` executes:

```text
EXECUTABLE TEST_RUNNER_PATH WORKFLOW_ID [REMOVED_GRANT_ID ...]
```

The application-owned runner applies those denials in its isolated permission
store and runs the selected workflow. Its stdout must contain exactly one JSON
object matching `WorkflowRun.to_dict()`. Write diagnostic logging to stderr;
SafeRevoke deliberately does not copy that stream into reports because application
logs may contain secrets. No shell is used. Timeouts and nonzero exit codes stop
the experiment, and the engine invokes the supplied reset hook. Processes or
side effects spawned by the test command remain the application's responsibility.
Python orchestrates the tests; the business permission checks execute in Node.js
or Java. Connectors do not install either runtime.

## Language-neutral HTTP contract

`HTTPAdapter(lab, "http://127.0.0.1:PORT", token=token,
test_environment=True)` requires a separate application-owned test harness with
these endpoints, all protected by `Authorization: Bearer TOKEN`:

| Method and path | Input | Successful JSON response |
| --- | --- | --- |
| `GET /capabilities` | No body | `{"protocol":"saferevoke.v1","test_environment":true}` |
| `POST /snapshot` | `{}` | `{"snapshot":"opaque-id"}` |
| `POST /deny` | `{"grant_ids":["g_orders"]}` | `{}` after application succeeds |
| `POST /run` | `{"workflow_id":"read_orders"}` | A matching `WorkflowRun.to_dict()` object |
| `POST /restore` | `{"snapshot":"opaque-id"}` | `{}` after all covered state is restored |

The harness must implement real mutation, trace capture and state reset. Deny
requests represent cumulative removals, not an overriding global deny. The
harness must lock its environment for the snapshot/deny/run/restore lifecycle
and reject overlapping clients. Do not deploy this control interface publicly.
Only literal loopback addresses are accepted; redirects and environment proxies
are disabled. Request timeouts and response-size limits are enforced. There are
no automatic mutation retries. A lost snapshot response can leave a server-side
snapshot behind: use disposable fixtures and a harness cleanup/expiry policy.
If restoration cannot be confirmed, stop and reset that test environment manually.

## Keycloak and Auth0 stores

These are permission-store connectors, not whole-application adapters. Combine
them with a framework, callback or HTTP-based application runner. Supply your own
authenticated request callable with signature `(method, path, json_body)`, which
returns decoded JSON or `None` after a successful 204 response. It must raise for
HTTP errors and enforce verified TLS, timeouts and the exact expected server.
For the paths below, the callable's base URL is the server origin, not `/api/v2`.

```python
from saferevoke.adapters.providers import KeycloakRoleBinding, KeycloakRoleStore

store = KeycloakRoleStore(request, "saferevoke-test", [
    KeycloakRoleBinding("g_refund", test_user_uuid, approver_role_uuid),
], test_environment=True)
```

A Keycloak binding optionally accepts `client_uuid` for client roles. It removes
and restores only the selected user's direct role assignment. It preserves
unrelated roles. Group and composite-role access are not removed; model those
paths separately in the lab and trace their actual use. The master realm is
rejected. See the [Keycloak Admin REST API](https://www.keycloak.org/docs-api/latest/rest-api/index.html).

```python
from saferevoke.adapters.providers import Auth0PermissionBinding, Auth0PermissionStore

store = Auth0PermissionStore(request, [
    Auth0PermissionBinding("g_refund", test_user_id, api_identifier, "approve:refunds"),
], test_environment=True)
```

Auth0 permission reads are paginated and must identify a `DIRECT` source before
it is mutated. Role-only access is never restored as a newly assigned direct
permission. Missing source evidence or incomplete pagination stops testing. This
connector does not enumerate all group-effective access. See Auth0's
[permission reads](https://auth0.com/docs/api/management/v2/users/get-permissions),
[assignments](https://auth0.com/docs/api/management/v2/users/post-permissions) and
[removals](https://auth0.com/docs/api/management/v2/users/delete-permissions).

Compose provider snapshots with application snapshots; restoring the provider
alone does not undo a workflow's database writes. After mutation and restoration,
refresh the test application's tokens/sessions and clear its permission caches
through your hooks. Existing signed tokens are not rewritten by a management-API
change. Rate limits or eventual consistency can make removal/restore verification
fail; no unverified mutation is silently treated as success. Use dedicated test
identities and serialize access to the test realm or tenant. No live identity
provider or production account was contacted by the validation suite.
