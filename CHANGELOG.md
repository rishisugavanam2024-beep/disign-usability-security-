# Changelog

## 0.1.0a4 — 2026-10-27

- Native external connector commands: connector, permissions, revoke, grant/restore,
  baseline, test and report, configured with trusted local saferevoke.json hooks.
- External test uses SafeRevokeEngine directly and writes HTML/JSON only after
  successful execution, evidence checks and cleanup; baseline validates without removals.
- Complete command inventory in --help, detailed options/examples in --help-all,
  and --version. Existing inspect/setup, Flask, Django pytest and database/db remain.
- Help and report discovery never import connector code. Configuration paths,
  test opt-in, grant limits and incomplete report handling are validated.

## 0.1.0a3 — 2026-10-26 — published

- Short `saferevoke inspect/setup/test/db` commands and package console entry point.
- Existing Flask pytest baselines, grant-removal variants and cleanup verification.
- Source-only setup discovery, registered-store wiring and exercised-grant selection.
- Generic, Flask/FastAPI, command/HTTP and provider-store connector boundaries.
- SQLite backup/restore and optional disposable Docker database helpers.
- Pinned upstream Flaskr edit/delete validation using original application tests.
- Cross-platform Python CI, live Docker job and clean wheel installation gate.
- Features remain experimental; live provider-account verification is pending.

## 0.1.0a2 — unreleased installation changes (included in 0.1.0a3)

- Install the working Django/pytest integration with `pip install saferevoke`.
- Django, pytest and pytest-django are now default dependencies.
- Preserve `saferevoke[pytest]` as a compatible alias; Flask remains optional.
- The project remains experimental and mutation remains explicitly opt-in.

## 0.1.0a1 — 2026-10-26 — first experimental release

- Core permission mutation and runtime provenance comparison engine.
- Direct/group permission discovery and transaction rollback adapter for Django.
- Opt-in pytest plugin reusing existing test fixtures and assertions.
- Baseline comparison, residual-access and privilege-fallback evidence.
- Optional affected-test selection from fresh baseline permission traces.
- Local JSON/HTML report exports and coverage information.
- Configurable in-memory labs, synthetic benchmarks and Django admin examples.
- MIT licence and installable wheel/source distributions.

Published on PyPI under the MIT License. The release workflow completed
successfully, and the public package metadata serves both wheel and source files.
This remains an alpha; publication does not establish production reliability.
