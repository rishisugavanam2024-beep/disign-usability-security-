# SafeRevoke

**Experimental permission-removal testing for Python and Django applications.**

SafeRevoke helps developers investigate what changes when an access grant is
removed. Its pytest plugin reuses existing Django test fixtures and assertions,
records actual authorization decisions, and generates HTML/JSON findings.

Version **0.1.0a2** is an early alpha. Support currently covers serial, synchronous
pytest-django tests using Django 5.2's standard user/group authorization backend.
Licensed under the MIT License.

## Install

Install the experimental release from PyPI:

```shell
pip install saferevoke
```

For development from the repository:

```shell
python -m pip install -e .
```

This installs Django, pytest and pytest-django automatically. The older
`saferevoke[pytest]` form remains compatible. Flask for the repository's demo
website is a separate optional `web` extra.

The plugin registers automatically. Permission mutation is disabled until
`--saferevoke` is supplied; installing it does not enable mutation in ordinary tests.

## Use your existing Django tests

```shell
python -m pytest tests/test_refunds.py --ds=myproject.test_settings --saferevoke --saferevoke-deny group:refund_operators:orders.approve_refund
```

Replace the illustrative test path, Django settings and permission selector with
values from your application. Fixtures must create the relevant test users and
grants. Test functions do not need SafeRevoke workflow wrappers.

Selectors use `user:USERNAME:app_label.codename` for a direct grant or
`group:GROUP_NAME:app_label.codename` for a group grant. Repeat
`--saferevoke-deny` to test additional grants independently.

To use observed dependencies to skip unrelated mutation variants before fixture
setup, add:

```shell
--saferevoke-selection affected
```

Every selected test still gets a fresh baseline. Empty or uncertain traces keep
their mutation runs. Full mode, `--saferevoke-selection all`, is the default.

## Results

Reports are written to `reports/pytest-saferevoke/report.html` and `report.json`.
They include baselines, permission traces, remaining-access findings, failed
assertions and selection counts. Tests that fail under permission removal retain
pytest's usual failure status and nonzero exit code. This may indicate expected
access enforcement or a broken required workflow; review the evidence.

The engine can also compare observed identities and privilege scope to flag a
more privileged fallback. Such a path must actually execute and reach the
supported permission backend to be detected. Passing tests alone are not proof
that production permission removal is safe.

## Boundaries

- Runs against the test database managed by pytest-django, with database rollback
  after each observed test body.
- Supports standard Django direct/group permissions and active non-superuser
  identities. Custom authorization backends, async/live-server workflows, xdist
  and multiple database aliases are not supported by this alpha.
- Database rollback does not reset files, email, workers or external services.
  Use isolated test settings and deterministic fixtures.
- Dependency selection covers observed baseline paths. Direct permission-table
  queries, custom checks and unobserved branches can be missed. Full mode remains
  available for broader validation.
- The library does not automatically sandbox or copy an entire application.

## Documentation and examples

- [Installation, runnable example and compatibility](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/pytest-integration.md)
- [Django adapter](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/django-integration.md)
- [Source and issue tracker](https://github.com/rishisugavanam2024-beep/disign-usability-security-)
