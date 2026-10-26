# 0.1.0a3 release validation

This candidate remains experimental. Publication is separate from local checks.

## Local evidence

- Windows/Python 3.14: 89 checks collected, 88 passed; the opt-in live Docker
  check was skipped because the local engine could not be reached.
- A built wheel installed with declared dependencies in a new temporary virtual
  environment outside the repository. `pip check`, the installed console command,
  current-directory inspection and package/version imports passed.
- Wheel and source archive passed strict Twine validation. Archive inspection
  confirmed generated reports were excluded and SQL/Java/Node example assets
  and the wheel-check script were present.
- Source YAML parsed with the release gates required by the build job.

## Independently maintained application

The official [Flaskr tutorial](https://github.com/pallets/flask/tree/3.1.2/examples/tutorial)
was checked out at `2c1b30d0503cfb064f1cb252e6614a06915a362a`.
Its original `test_update` and `test_delete` assertions and application source
were unchanged. A separate integration observes the real `get_post` ownership
check and removes test access by changing the fixture post's author, as an
existing upstream authorization test also does.

Both baselines passed. Both removal variants failed their original assertions,
producing two `REQUIRED_ACCESS` findings. The SQLite helper restored permissions,
post content and deletion state after every run. This is a narrow validation of
two externally maintained workflows; it is not whole-application, production or
universal framework compatibility evidence.

Reproduce after checking out the pinned upstream source:

```bash
python -m examples.upstream_flaskr.run reports/upstream-flask-3.1.2
```

The wrapper returns success only when the expected baseline/mutation results and
restoration checks hold. Pytest's two deliberate removal failures are therefore
expected evidence, not failures of the integration verification.

## Remote release gates

The publishing workflow now requires:

1. Windows and Ubuntu tests on Python 3.10, 3.12 and 3.14, with optional framework
   clients installed and Node/Java runtimes available.
2. Real PostgreSQL/MySQL Docker startup, schema/fixture SQL, query and cleanup.
3. The pinned independent Flaskr test.
4. Distribution build, strict metadata check and clean wheel installation.

Adding these jobs is not evidence that they passed. Inspect the particular
GitHub Actions run for the release commit. The PyPI job only runs after all gates
and an explicitly enabled manual publishing run. For an existing PyPI project,
the trusted publisher must be configured at project level; an account-level
pending publisher does not authorize updates to an existing project.

Live Auth0/Keycloak tenant checks and a large production application's integration
remain outstanding. Docker failure/interruption cleanup and external queues,
files, caches and tokens remain subject to the documented test-environment limits.
