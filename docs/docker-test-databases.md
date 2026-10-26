# Optional disposable Docker test databases

The shorter equivalent is now `saferevoke db postgres -- pytest tests/`.
See [command setup](commands.md) for local installation and aliases.

The local SDK now supplies a Docker database lifecycle helper for PostgreSQL and
MySQL. It works independently of Django or Flask: Python, Java, Node.js, PHP and
other application test commands can receive the new database's connection values.
This feature is not yet published. Docker contract tests are included; real-server
verification remains pending when the local Docker engine is unavailable.

## Run a test command with a fresh database

Docker must be installed, running locally and configured for Linux containers.
With a cached official image:

```bash
python -m saferevoke database postgres --seed examples/docker_database/schema.sql --command python -m pytest tests/
```

To allow downloading a missing official image, add `--pull` before `--command`.
Use `mysql` instead of `postgres` to select MySQL. Images are `postgres:17-alpine`
and `mysql:8.4`; mutable tags are not a reproducibility guarantee. No download,
daemon startup, dependency installation or real database access happens merely
by installing/importing SafeRevoke.

The helper creates a uniquely named container, generates random test credentials,
waits for an authenticated SQL query to succeed and optionally loads the explicit
test schema/fixture SQL. It then runs the command without a host shell and removes
its owned container plus ephemeral storage afterward, including after a failing
test or seed command. Cleanup failure propagates; it is not reported as success.
It never prunes Docker resources, connects to a remote Docker engine, mounts a
host database directory, or deletes an existing application's database/container.

The child receives `DATABASE_URL`, `SAFEREVOKE_DATABASE_URL` and separate
`SAFEREVOKE_DB_HOST`, `SAFEREVOKE_DB_PORT`, `SAFEREVOKE_DB_USER`,
`SAFEREVOKE_DB_PASSWORD`, `SAFEREVOKE_DB_NAME` environment variables. Host process
environment values remain unchanged. Credentials are not printed or included in
command arguments; Docker administrators can still inspect container environment.
Applications must actually read these test connection values. Java apps can use
the separate fields to build their JDBC configuration; the generic DATABASE_URL
is not a JDBC URL. Application database drivers remain application dependencies.

## Fixture use across frameworks

```python
import pytest
from saferevoke.docker_database import DockerDatabase

@pytest.fixture
def database():
    with DockerDatabase("postgres") as database:
        database.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY);")
        yield database.connection

@pytest.fixture
def app(database):
    app = create_test_app(database_url=database.url)
    run_application_migrations_and_seed_fake_users(app)
    yield app
    close_application_connections(app)
```

`create_test_app`, migrations, fake users and connection shutdown above are
application-owned functions. Close app connections before the database fixture
exits. A function-scoped fixture gets a fresh database per pytest variant. The
standalone CLI command creates one database for the whole child command, so
between-test cleanup still belongs to application transactions/reset hooks.
SafeRevoke's permission testing still needs an actual inventory, permission
mutation, observation and state-restoration connection. Docker does not infer
the application's schema, business workflows or authorization behavior.

You can combine this helper with the existing Flask automatic runner once the
app's fixtures read the supplied connection values:

```bash
python -m saferevoke database postgres --command python -m saferevoke test PATH_TO_FLASK_PROJECT
```

Do not seed the same tables twice if application migrations already create them.
The included schema.sql contains synthetic example rows and is not a universal
schema for real applications. Never point the app at a production connection when
these environment variables are missing. An unavailable Docker daemon/image
stops before launching the child command; there is no automatic production fallback.

## Resources and verification

Only loopback ports are published, using a random available host port. Default
limits are one CPU, 512 MB container memory and 256 MB temporary data storage for
PostgreSQL; MySQL uses 1,024 MB memory and 512 MB temporary storage. Docker Desktop
and image cache storage are additional overhead. These defaults suit small test
fixtures, not arbitrary application datasets. Python callers can override limits
through the constructor. Docker is optional; explicitly configured local test
databases and the SQLite helper remain available without it.

Startup waits up to 90 seconds, individual Docker commands up to 30 seconds and
the CLI child command up to 120 seconds. CLI startup/child limits can be set with
`--startup-timeout` and `--command-timeout`. Image downloads are subject to the
Docker command timeout, so cache larger images beforehand. Abrupt process kills,
daemon failures and interrupted creation can prevent confirmed cleanup. Stop and
inspect leftover `saferevoke-db-*` resources before retrying; never prune unrelated
resources. Resource labels and ownership checks limit normal cleanup to this run.
Container execution and loopback binding do not isolate external network effects
or prevent an application from using an unrelated connection it already holds.

Run Docker-independent contract checks:

```bash
python -m unittest discover -s tests -p test_docker_database.py -v
```

The real SQL-server checks are explicitly opt-in, require both cached images, and
actually create/delete containers. For PowerShell:

```powershell
$env:SAFEREVOKE_DOCKER_LIVE = "1"
python -m unittest discover -s tests -p test_docker_database.py -v
Remove-Item Env:SAFEREVOKE_DOCKER_LIVE
```

Command details follow Docker's [container CLI](https://docs.docker.com/reference/cli/docker/container/run/)
and the official [PostgreSQL](https://hub.docker.com/_/postgres) and
[MySQL](https://hub.docker.com/_/mysql) images.
