# Reuse existing Django tests

SafeRevoke now supplies an opt-in pytest plugin. It repeats the pytest functions
you select with normal permissions and then with each specified grant removed.
The tests' existing assertions become the workflow checks. No `Workflow` wrappers
or calls to the SafeRevoke engine are required in those tests.

This is an early integration for standard, synchronous Django authentication.
Version 0.1.0a1 is published on PyPI under the MIT License:

```shell
python -m pip install --pre "saferevoke[pytest]==0.1.0a1"
```

## Install from the repository

From the project directory, using the Python environment that runs your tests:

```powershell
python -m pip install ".[pytest]"
```

For local development use `python -m pip install -e ".[pytest]"` instead.
The package's `pytest11` entry point registers the plugin automatically.
Installing it does not enable permission mutation: ordinary pytest runs are unchanged.

## Five-minute example

From this checkout:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pytest]"
.\.venv\Scripts\python.exe -m pytest examples/django_pytest --ds=examples.django_pytest.settings -q
```

All four existing-style admin tests should pass normally. Now run:

```powershell
.\.venv\Scripts\python.exe -m pytest examples/django_pytest --ds=examples.django_pytest.settings --saferevoke --saferevoke-deny group:operators:auth.view_user --saferevoke-deny user:alice:auth.view_group --saferevoke-deny user:alice:auth.add_group --tb=short -q
```

This executes 16 variants: four normal tests and twelve mutation variants.
Three mutation variants fail their existing assertions: Alice's and Bob's user-list
tests receive HTTP 403, and Alice's group-creation test receives HTTP 403. The
remaining thirteen variants pass. A pytest exit code of 1 is expected for this
demonstration because those original assertions failed; the plugin preserves the
normal exit status rather than hiding failures.

Open `reports/pytest-saferevoke/report.html` for the summary or `report.json`
for baselines, permission inventories, actual backend traces and findings.
Removing Alice's direct group-view grant leaves her role-based access and is
reported as `PARTIAL_REMOVAL` where the baseline actually uses the selected grant.

## Automatically select relevant mutation tests

Add `--saferevoke-selection affected` to enable selection based on this run's
baseline traces:

```powershell
.\.venv\Scripts\python.exe -m pytest examples/django_pytest --ds=examples.django_pytest.settings --saferevoke --saferevoke-deny group:operators:auth.view_user --saferevoke-deny user:alice:auth.view_group --saferevoke-deny user:alice:auth.add_group --saferevoke-selection affected --saferevoke-output reports/pytest-affected --tb=short -q
```

Every selected test still runs once normally, before the mutation phase. The
plugin builds a fresh mapping from observed permission dependencies to test cases.
It then skips unrelated mutation variants **before fixture setup**, saving the
fixture and test-body work. It does not reuse an older map that may be stale.

For the included Django admin example, full mode executes 16 test bodies; affected
mode executes 13 and omits 3 mutation variants before setup. Both modes detect the
same three failing assertions. That is 25% fewer mutation executions and 18.75%
fewer total test-body executions in this controlled example. These counts are not
a claim of the same percentage reduction in wall time, CPU consumption or memory.

Dependency tracing covers `has_perm`, module access checks, and enumeration of
all, direct or group permissions through the supported Django backend. This keeps
tests that build permission-based menus or inspect a permission set. It also
considers matching denied checks rather than relying only on successful access.

An empty or uncertain trace, a failed/missing baseline or a missing inventory
keeps the mutation candidate for normal execution. Missing grants can still be
reported as not applicable when its fixtures are prepared. To force a particular
test to run every mutation, use `@pytest.mark.saferevoke_full`.

The default `--saferevoke-selection all` remains available and runs all variants.
Trace-based selection assumes equivalent deterministic fixtures and observes only
the baseline paths reached in this run. Direct permission-table queries, custom
authorization code, unobserved branches and untracked external dependencies can
be missed. Use full mode (or the marker) for those tests and for periodic coverage
audits. `NOT_SELECTED` means omitted based on the trace; it does not mean the
permission removal was tested or proven safe.

The HTML/JSON report includes execution/omission counts, selection reasons and
the baseline dependency map. Savings depend on how narrowly tests access
permissions: a test that enumerates every permission may need every mutation.

## Use in your own project

Your application needs its normal pytest-django test settings, fixtures that create
the relevant users/permissions, and pytest functions that exercise the behavior:

```powershell
python -m pytest tests/test_refunds.py --ds=myproject.test_settings --saferevoke --saferevoke-deny group:refund_operators:orders.approve_refund
```

The refund permission in this command is illustrative; replace it with a real
permission and group from your test fixtures. Repeat `--saferevoke-deny` to test
additional grants independently. A selector uses one of these forms:

- `user:USERNAME:app_label.permission_codename` removes a direct user grant.
- `group:GROUP_NAME:app_label.permission_codename` removes a group grant for all
  members in the test's database.

The plugin inventories active non-superuser accounts after fixture setup. Optionally
use `--saferevoke-users alice,bob` to select specific identities; those identities
must exist in each affected test's fixtures. Names containing colons are not
supported in selectors. `--saferevoke-output PATH` changes the report directory.

## Execution and interpretation

1. Pytest creates the test database and prepares the application's regular fixtures.
2. SafeRevoke discovers the prepared direct/group grants. It uses stable selector
   labels, so changing database primary keys do not invalidate comparisons.
3. For a mutation variant, it removes one real grant inside a transaction and
   clears permission caches on user objects supplied in common fixture containers.
4. The existing test function runs. Django's own backend evaluates permission
   checks, which SafeRevoke records.
5. The transaction rolls back, even when the test raises, before fixture teardown.
6. Reports compare each mutation variant with its matching passing baseline.

A failed baseline, failed setup/teardown, expected failure or changed fixture
inventory produces an inconclusive comparison. If the chosen grant does not exist
in a test's fixtures, that mutation is skipped and reported as not applicable.
If the baseline never exercises the selected grant, the result remains unknown
or lacks attribution. Passing assertions produce `NO_FAILURE_OBSERVED`, never a
blanket promise that production removal is safe.

The plugin reuses the engine's trace and privilege-scope comparison. It does not
yet run adaptive removal-order experiments through pytest. A real privileged
fallback must execute and reach the supported permission backend to be observable;
the included admin tests demonstrate task failures and duplicate access.

## Compatibility boundaries

- Supports pytest function tests with pytest-django and Django 5.2's standard
  `ModelBackend`; existing test clients logged in during setup remain usable.
- During the test body it enables the observing backend, preserving the standard
  backend for existing sessions, then restores settings. It does not require a
  permanent authentication configuration change in the application.
- The test database is supplied by pytest-django. Use isolated test settings, and
  avoid external email, files, workers or services that database rollback cannot reset.
- Supports a serial test run and the default database on the current connection.
  Async code, live-server requests, multiple databases, xdist, arbitrary custom
  authorization backends and `unittest.TestCase` reruns are not supported yet.
- It mutates permissions after fixture setup. Authorization exercised only while
  preparing fixtures is outside the observed test body. A test that re-grants a
  permission itself can undo the mutation; inspect the trace and assertions.
- Superuser shortcuts, custom object-level authorization and code paths bypassing
  `has_perm` are not fully observed. Use selected active, non-superuser fixtures.
- Mark an incompatible test with `@pytest.mark.saferevoke_skip` to omit its variants.
- Affected-selection mode runs baselines before all mutations; tests with order
  dependencies should use the default full mode.
- Module/session fixtures and external state must remain deterministic between
  variants. A database transaction cannot reset arbitrary Python objects.

## Verify and build

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip wheel --no-deps . --wheel-dir dist
```

The core package contains the engine and plugin. Flask is an optional `web` extra;
Django/pytest support is the `pytest` extra. The examples and web template files
remain in the repository and are not shipped as library modules in the wheel.

References: [pytest plugin entry points](https://docs.pytest.org/en/stable/how-to/writing_plugins.html)
and [pytest-django database fixtures](https://pytest-django.readthedocs.io/en/latest/database.html).
