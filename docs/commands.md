# Short commands

Version 0.1.0a4 installs the `saferevoke` terminal command. Activate your virtual
environment and install or upgrade the published package:

```bash
pip install --upgrade saferevoke
```

Earlier releases need upgrading to obtain the short command. Source development
can alternatively use `pip install -e .` from the repository.

| Command | Action |
| --- | --- |
| `saferevoke inspect` | Read-only discovery in the current directory |
| `saferevoke setup` | Generate setup files in a new saferevoke-setup directory |
| `saferevoke test` | Analyze an external saferevoke.json connector or configured Flask project |
| `saferevoke connector` | Describe external configuration without running the connector |
| `saferevoke permissions USER` | List permissions through the external test connector |
| `saferevoke revoke USER PERMISSION` | Revoke a test permission through the connector |
| `saferevoke grant USER PERMISSION` | Restore a test permission; `restore` is an alias |
| `saferevoke baseline` | Validate external workflows without removals |
| `saferevoke report --open` | Open the latest completed external analysis report |
| `saferevoke --version` | Show the installed library version |
| `saferevoke --help-all` | Show every CLI command, option and example |
| `saferevoke db postgres -- pytest tests/` | Run a test command with a disposable PostgreSQL database |
| `saferevoke db mysql -- pytest tests/` | The same database wrapper for MySQL |
| `saferevoke --help` | Command help |

`inspect`, `setup` and `test` default to the current directory. To select another
project, append its path, for example `saferevoke test examples/flask_pytest`.
Quote paths containing spaces. Ordinary shell quoting rules apply; the SDK does
not invoke a shell or interpret command strings.

The `db` alias accepts a standard `--` separator, followed by the executable and
its exact arguments. Place database options before that separator:

```bash
saferevoke db postgres --pull --seed examples/docker_database/schema.sql -- pytest tests/
```

Docker must be running locally, and the app's test configuration must use the
supplied database environment variables. Test data and permission hooks still
need application configuration. The database wrapper can launch any language's
test executable; automatic framework discovery targets Flask; explicit external connectors support other stacks. Django's
existing pytest permission-removal options remain separate.

The original `python -m saferevoke ...`, `database` subcommand name and
`--command EXECUTABLE ...` syntax are retained. Console and module invocation
use the same implementation. See [external connectors](external-connectors.md) for the native connector commands and security/cleanup contract.
