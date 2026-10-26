# SafeRevoke

**Experimental permission-removal testing for application developers.**

SafeRevoke helps developers investigate what changes when an access grant is
removed. Its integrations reuse existing test fixtures and assertions, record
authorization decisions, and generate HTML/JSON findings.

Version **0.1.0a3** is an experimental alpha under MIT. Django and Flask have
existing-test integrations; other stacks require explicit connectors. Installing
the library does not connect arbitrary websites or enable permission mutation.

## Install

Install the experimental release from PyPI:

```shell
pip install saferevoke
saferevoke --help
```

For development from the repository:

```shell
python -m pip install -e .
```

This installs Django, pytest and pytest-django automatically. The older
`saferevoke[pytest]` form remains compatible. Flask is an optional `web` extra;
`[test]` supplies Flask/FastAPI clients for the SDK verification suite. Docker is
optional and installed separately.

The plugin registers automatically. Permission mutation is disabled until
`--saferevoke` is supplied; installing it does not enable mutation in ordinary tests.

## Short commands and Flask testing

```shell
saferevoke inspect
saferevoke setup
saferevoke test
```

The current directory is used unless a project path is supplied. `inspect` reads
source without importing the app; `setup` generates a new configuration template
directory without overwriting existing files. Static hints require verification.

Automatic `test` currently targets Flask applications with an explicitly connected
test permission store and observation hook. It discovers exercised grant IDs,
checks passing baselines and state restoration, then runs removal variants using
existing assertions. Unexercised grants remain unknown. A registered-store helper,
dictionary reset helper and explicitly scoped SQLite backup reduce setup work.
The report is a local HTML/JSON file; no browser or web server opens automatically.

## Optional Docker test databases

```shell
saferevoke db postgres -- pytest tests/
```

Use `mysql` for MySQL. Images must be cached unless `--pull` is supplied before
`--`. Docker must run locally in Linux-container mode. The helper creates a fresh
database with random credentials, loopback ports and resource limits, passes
connection variables only to the test command and cleans up its owned container.
The application still supplies migrations, fake data, drivers, permission hooks
and between-test reset logic, and must actually use the supplied test connection.
This does not copy production databases or isolate external network/queue effects.
Real Docker-server validation is separate from the deterministic CLI contract
tests; review the release validation evidence for the optional Docker feature.

## Other connectors and verification scope

- FastAPI uses its real TestClient with explicit permission/state hooks.
- Custom Python apps can use callback workflows; Node.js/Java and other languages
  can provide a test command or loopback HTTP harness. These are bridges, not
  automatic Express/Spring adapters or published npm/Maven SDKs.
- Keycloak direct user-role and Auth0 direct-permission stores have API contract
  tests; live provider-account verification remains pending.
- An independent integration harness reuses the official Flaskr tutorial's
  original edit/delete tests at a pinned Flask 3.1.2 source revision. It observes
  the original ownership decisions and resets the real SQLite test database,
  without editing upstream assertions. This covers two upstream workflows, not
  an entire production application.

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

- [Short terminal commands](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/commands.md)
- [Automatic setup and Flask tests](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/automatic-setup.md)
- [Docker test databases](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/docker-test-databases.md)

- [Installation, runnable example and compatibility](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/pytest-integration.md)
- [Django adapter](https://github.com/rishisugavanam2024-beep/disign-usability-security-/blob/main/docs/django-integration.md)
- [Source and issue tracker](https://github.com/rishisugavanam2024-beep/disign-usability-security-)
