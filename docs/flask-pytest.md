# Use existing Flask tests with SafeRevoke

This local source addition reduces integration work: keep ordinary synchronous
pytest tests and assertions, add a fixture describing the application's permission
inventory/reset hooks, and rerun those tests under permission removal. You do not
need to rewrite them as SDK workflow runners. This feature is not published yet.

The [automatic setup and test command](automatic-setup.md) can now discover test
fixtures and exercised grants, then run these variants without typed target IDs.

## Try the complete local example

Activate the repository's virtual environment. Install the local source and Flask
if needed, then run the ordinary tests:

```bash
pip install -e .
pip install "Flask>=3.1,<4"
python -m pytest -p saferevoke.flask_pytest examples/flask_pytest -q
```

Expected: **4 passed**. Run the same tests with two permission-removal targets:

```bash
python -m pytest -p saferevoke.flask_pytest examples/flask_pytest --saferevoke-flask --saferevoke-flask-deny g_orders --saferevoke-flask-deny g_refund
```

Expected: **2 failed, 10 passed**. The two failures are deliberately detected
permission dependencies, not SDK test failures. The terminal and HTML/JSON report
explain them:

- Removing `g_orders` breaks Alice's and Bob's order-list assertions.
- Removing `g_refund` leaves refund approval working by switching to the broader
  service account. The trace produces `UNSAFE_FALLBACK` despite passing assertions.
- Unexercised targets, such as the health endpoint's permissions, produce
  `UNKNOWN`; lack of failure is not proof of safe removal.
- All variants restore the example's permission set and refund writes before
  fixture teardown. The example's teardown assertions verify that too.

Reports default to `reports/pytest-saferevoke-flask/report.json` and `report.html`.
Choose a different location with `--saferevoke-flask-output PATH`. Pytest retains
its normal exit behavior: a failing mutation assertion returns a nonzero status.
Passing assertions alone do not mean the report contains no security finding.

## Connect your application

First use an isolated test app with `TESTING=True` and
`SAFEREVOKE_TEST_ENVIRONMENT=True`. These flags are opt-in guards, not isolation
mechanisms. Use test users, test credentials and a resettable test database.

Observe the application's real permission function using `record_access` from
`saferevoke.adapters.web`. The application decides whether access is allowed;
the hook only records the actual identity, operation and granting permission IDs.
Supply those grants using the existing `Grant` model. Grant IDs must match actual
permission sources, including role grants and fallback/service identities.

Add a `saferevoke_flask` fixture to your root `conftest.py`:

```python
import pytest
from saferevoke.adapters.callback import StateHooks
from saferevoke.flask_testing import FlaskTestIntegration

pytest_plugins = ["saferevoke.flask_pytest"]

@pytest.fixture
def saferevoke_flask(app, permission_store, test_state):
    hooks = StateHooks(
        snapshot=test_state.snapshot,
        deny=permission_store.remove_grants,
        restore=test_state.restore,
    )
    return FlaskTestIntegration(
        app, grants=permission_store.inventory(), hooks=hooks,
        verify_restored=test_state.matches_snapshot,
        roles=permission_store.user_roles(),
        capabilities=permission_store.capability_universe(),
        action_weights={"read": 1, "approve": 3, "delete": 5},
    )
```

This is a wiring example: `permission_store` and `test_state` are application-owned
fixtures/methods, not SDK-provided services. Inventory returns `Grant` objects;
`user_roles()` maps identity strings to sets of role names. The snapshot must cover
permissions, business data, sessions, caches, queues and external effects reached
by the selected tests. `matches_snapshot(snapshot)` must return exactly `True`
only after verifying the actual covered state. Provision appropriate capability
metadata for privilege comparisons; an incomplete inventory limits the analysis.

With the root plugin declaration, the command becomes:

```bash
python -m pytest tests/ --saferevoke-flask --saferevoke-flask-deny YOUR_GRANT_ID
```

For a self-contained dictionary-backed app, `FlaskTestIntegration.for_dictionary`
provides deep-copy snapshot, restore and equality verification. Supply the real
application denial callback. See `examples/flask_pytest/conftest.py` for a runnable
example. This helper does not restore databases or external effects. References
held outside the dictionary to removed/replaced objects are not covered.

Existing tests can keep their ordinary `client`, `app`, user and data fixtures.
All application fixtures are initialized before removal. Each test body runs once
as a baseline and once per selected grant, then restoration runs before fixture
teardown, even after an assertion failure or a partially failed denial callback.
Exclude unsupported tests using `@pytest.mark.saferevoke_flask_skip`; they retain
ordinary pytest behavior and their own cleanup responsibilities.

## Result boundaries

- Inconsistent fixture inventories, incomplete source attribution, skipped/xfail
  cases and failed baseline/cleanup produce `INCONCLUSIVE`.
- A target missing from a fixture inventory is `NOT_APPLICABLE`.
- If the target continues authorizing access, the result is
  `ACCESS_STILL_OBSERVED`, rather than a safe-removal claim. Check the mutation
  callback and the application's caches/tokens.
- `NO_FAILURE_OBSERVED` means only that covered assertions passed. This is not a
  recommendation to remove production access.
- Failed cleanup stops further variants. Reset that environment before retrying.

Use synchronous pytest functions/classes with serial execution. Async functions,
`unittest.TestCase` tests, xdist, and simultaneous Django/Flask mutation runs are
not supported by this initial runner. Isolate tests with other plugins yourself.
The runner observes test-body permission hooks, not fixture setup checks, spawned
processes or uninstrumented background jobs. HTTP bodies and side effects are
checked only by existing assertions; unlike engine workflows, this runner does not
automatically compare response bodies or database contents between test variants.
There is no automatic affected-test filtering yet: all configured variants run.

Terminal security findings may accompany passing assertions. Inspect the report
in CI; a separate policy-based security gate has not been added. JSON reports
contain configured identities, resources and grant sources; assertion traceback
text is deliberately not copied into the report. HTML escapes report values.
