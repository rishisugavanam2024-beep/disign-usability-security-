# Automatic discovery and setup

See [short terminal commands](commands.md) to use `saferevoke inspect`,
`saferevoke setup` and `saferevoke test` after installing the local source.

These are local source additions, not a new published package version. They reduce
setup for supported applications. A developer still connects the actual test
permission store once; the SDK cannot infer arbitrary database write operations.

## Inspect and generate setup

```bash
python -m saferevoke inspect PATH_TO_PROJECT
python -m saferevoke setup PATH_TO_PROJECT
```

`inspect` prints JSON and writes nothing. `setup` creates a fresh
`saferevoke-setup/` with discovery evidence, a configuration plan, instructions and
an example Flask fixture. It refuses to overwrite that directory and never edits
the application's conftest.py. The example is a template, not a working connection
to an unknown permission store.

Scanning finds framework imports/dependency hints, test candidates, scoped pytest
fixtures, literal SDK grant declarations and Django settings hints. It reads
source without importing it, reading .env files, accessing databases, running
tests or installing dependencies. Hidden files, dependency/build/cache folders
are excluded. Defaults: 3,000 files, 1 MB per file, 10 MB total. Incomplete scans
report warnings. Dynamic or conflicting grants require runtime verification.
Static findings are hints, not proof of effective permissions or pytest collection.
For mixed projects, choose a narrower component directory or pass `--framework`
with `flask`, `django` or `fastapi` to inspect/setup.

## Connect a Flask test store once

```python
app.config.update(TESTING=True, SAFEREVOKE_TEST_ENVIRONMENT=True)
app.extensions["saferevoke"] = test_permission_store
```

The explicitly registered store implements `inventory()` returning `Grant`
objects, `snapshot()`, `remove_grants(ids)`, `restore(snapshot)` and
`matches_snapshot(snapshot)` returning a boolean. Optional `user_roles()`,
`capability_universe()` and `action_weights()` supply privilege metadata. The SDK
wires these methods automatically; no manually assembled Lab is needed. The
application's real permission checks still need the `record_access` observation
hook. Snapshots must include business writes and caches, not only permission rows.

Then add one fixture to the application's root conftest.py:

```python
import pytest
from saferevoke.flask_testing import FlaskTestIntegration

@pytest.fixture
def saferevoke_flask(app):
    return FlaskTestIntegration.from_registered_store(app)
```

Alternatively call `FlaskTestIntegration.from_store(app, test_store)`. Required
methods and test-app flags are checked before reading the registered inventory.
These flags cannot prove isolation; the app must use disposable test data.

## Discover and test permissions automatically

```bash
python -m saferevoke test PATH_TO_FLASK_PROJECT
```

This command executes existing tests in the configured isolated environment. It
finds test files, runs baseline-only discovery, selects permissions actually used
by those baselines and reruns the tests with removal variants. It stops before
removal if baseline assertions, trace attribution or cleanup verification fail.
Reports and summary JSON go into a new `reports/saferevoke-auto/` directory.
Unexercised grants are listed separately; they are not claimed safe.

The automatic runner currently supports Flask only. Django retains its existing
runtime inventory and explicit selectors; FastAPI still uses the engine API.
Use `--framework flask` for a mixed project. Defaults: at most 10 selected grants
and 120 seconds per pytest subprocess, configurable with `--max-targets` and
`--timeout`. A timeout kills the subprocess and marks state unverified: reset the
disposable environment before retrying. No shell is used. All selected tests run
for every selected grant; affected-test filtering is not implemented here.

Try the included demo from the SDK repository root:

```bash
python -m saferevoke inspect examples/flask_pytest
python -m saferevoke test examples/flask_pytest
```

Expected: four baseline cases pass; `g_orders` and `g_refund` are selected while
`g_service` remains unexercised. Removal finds two order-access failures and an
`UNSAFE_FALLBACK` during refunds. Exit code 1 reflects the two failing application
assertions. Findings can also accompany passing assertions: inspect the summary's
`findings_summary`. A separate policy-based CI security gate is not implemented.

## SQLite test-data reset helper

```python
from saferevoke.adapters.sqlite import SQLiteTestState

database = SQLiteTestState(
    test_database_path, test_root=dedicated_test_directory,
    remove_grants=test_permission_store.remove_grants,
    test_environment=True,
)
# FlaskTestIntegration(..., hooks=database.hooks,
#                      verify_restored=database.matches_snapshot)
```

This supplies backup, restore and verification for one explicitly selected,
quiescent SQLite test database, covering permission rows, business writes and
schema changes. It refuses files outside the declared test root, symlink files,
wrong-owner/closed snapshots and oversized databases. Defaults: 32 MB and a
five-second backup/restore deadline. It never creates a missing database.

Close application transactions and stop background writers before using this
helper. It does not infer schemas, reset Python caches/tokens, undo external
network/queue effects, or restore PostgreSQL/MySQL. Supply the real permission
mutation callback and combine other application state hooks where necessary.
Any failed restoration requires resetting the disposable test environment.

For non-SQLite applications, optional [Docker test databases](docker-test-databases.md)
can now provision fresh PostgreSQL or MySQL instances. The application still
supplies migrations, fixture data, permission hooks and between-test reset logic.
