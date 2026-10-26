# Short commands

The local package now installs a `saferevoke` terminal command. Activate the
virtual environment and install the current repository once:

```bash
pip install -e .
```

These changes are not published to PyPI yet. An older installed release will not
have this command until upgraded to a release containing it.

| Command | Action |
| --- | --- |
| `saferevoke inspect` | Read-only discovery in the current directory |
| `saferevoke setup` | Generate setup files in a new saferevoke-setup directory |
| `saferevoke test` | Discover exercised grants and test removal in a configured Flask project |
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
test executable; automatic `saferevoke test` currently targets Flask only. Django's
existing pytest permission-removal options remain separate.

The original `python -m saferevoke ...`, `database` subcommand name and
`--command EXECUTABLE ...` syntax are retained. Console and module invocation
use the same implementation. No new report-view/open-browser command was added.
