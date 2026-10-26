"""Optional disposable PostgreSQL/MySQL test databases using the Docker CLI.

No existing databases or containers are reused. Application migrations, fixture
data, drivers and between-test reset hooks remain application-owned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from urllib.parse import quote


class DockerDatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseConnection:
    engine: str
    port: int
    password: str = field(repr=False)
    host: str = "127.0.0.1"
    user: str = "saferevoke"
    database: str = "saferevoke_test"

    @property
    def url(self):
        scheme = "postgresql" if self.engine == "postgres" else "mysql"
        return f"{scheme}://{self.user}:{quote(self.password, safe='')}@{self.host}:{self.port}/{self.database}"

    def environment(self):
        return {"DATABASE_URL": self.url, "SAFEREVOKE_DATABASE_URL": self.url,
                "SAFEREVOKE_DB_HOST": self.host, "SAFEREVOKE_DB_PORT": str(self.port),
                "SAFEREVOKE_DB_USER": self.user, "SAFEREVOKE_DB_PASSWORD": self.password,
                "SAFEREVOKE_DB_NAME": self.database}


class DockerDatabase:
    """Context manager for one fresh, locally published test database.

    Images must already be cached unless pull=True. SQL is sent to a client
    inside the new container. Ephemeral credentials are never printed or passed
    as command-line arguments. Docker administrators can inspect container env.
    """

    IMAGES = {"postgres": "postgres:17-alpine", "mysql": "mysql:8.4"}
    PORTS = {"postgres": 5432, "mysql": 3306}
    PATHS = {"postgres": "/var/lib/postgresql/data", "mysql": "/var/lib/mysql"}

    def __init__(self, engine="postgres", *, pull=False, startup_timeout=90,
                 command_timeout=30, memory_mb=None, cpus=1.0, storage_mb=None):
        if engine not in self.IMAGES:
            raise ValueError("Choose postgres or mysql")
        memory_mb = (512 if engine == "postgres" else 1024) if memory_mb is None else memory_mb
        storage_mb = (256 if engine == "postgres" else 512) if storage_mb is None else storage_mb
        if (startup_timeout <= 0 or command_timeout <= 0 or memory_mb < 256
                or cpus <= 0 or storage_mb < 64):
            raise ValueError("Provide positive timeouts/CPU and at least 256 MB memory, 64 MB test storage")
        self.engine, self.pull = engine, pull
        self.startup_timeout, self.command_timeout = startup_timeout, command_timeout
        self.memory_mb, self.cpus, self.storage_mb = memory_mb, cpus, storage_mb
        self.name = "saferevoke-db-" + secrets.token_hex(12)
        self._owner = secrets.token_hex(16)
        self._password = secrets.token_urlsafe(24)
        self._root_password = secrets.token_urlsafe(24)
        self._docker = shutil.which("docker")
        self._attempted = False
        self._closed = False
        self._connection = None

    @property
    def connection(self):
        if self._connection is None or self._closed:
            raise DockerDatabaseError("The disposable database is not running")
        return self._connection

    def _environment(self):
        env = dict(os.environ)
        env.update(POSTGRES_PASSWORD=self._password, MYSQL_PASSWORD=self._password,
                   MYSQL_ROOT_PASSWORD=self._root_password)
        return env

    def _call(self, arguments, *, input=None, check=True):
        if not self._docker:
            raise DockerDatabaseError("Docker is not installed; use an explicit local test database instead")
        try:
            result = subprocess.run([self._docker, *arguments], input=input,
                                    env=self._environment(), capture_output=True,
                                    text=True, encoding="utf-8", timeout=self.command_timeout,
                                    shell=False)
        except subprocess.TimeoutExpired:
            raise DockerDatabaseError("Docker command timed out; container cleanup must be verified") from None
        except OSError:
            raise DockerDatabaseError("Docker could not be executed") from None
        if check and result.returncode:
            # Docker and database stderr may contain SQL or credentials.
            raise DockerDatabaseError("Docker operation failed; verify the daemon, cached image and available resources")
        return result

    def _preflight(self):
        host = os.environ.get("DOCKER_HOST", "")
        if host and not host.startswith(("unix://", "npipe://")):
            raise DockerDatabaseError("Disposable databases require a local Docker engine")
        try:
            context = json.loads(self._call(["context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"]).stdout)
        except (ValueError, TypeError):
            raise DockerDatabaseError("Could not verify the local Docker context") from None
        if not isinstance(context, str) or not context.startswith(("unix://", "npipe://")):
            raise DockerDatabaseError("The selected Docker context is not local")
        if self._call(["info", "--format", "{{.OSType}}"]).stdout.strip() != "linux":
            raise DockerDatabaseError("Use a running local Docker engine configured for Linux containers")

    def _inspect_owned(self):
        try:
            data = json.loads(self._call(["inspect", self.name]).stdout)
            item = data[0]
            owner = item["Config"]["Labels"]["saferevoke.owner"]
            if (item["Name"] != "/" + self.name or owner != self._owner
                    or not isinstance(item["Id"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["Id"])):
                raise ValueError("Ownership mismatch")
            return item
        except (ValueError, TypeError, KeyError, IndexError):
            raise DockerDatabaseError("Container ownership could not be verified; no destructive action was taken") from None

    def start(self, *, seed_sql=None):
        if self._attempted or self._closed:
            raise DockerDatabaseError("Each DockerDatabase instance can be started only once")
        if seed_sql is not None and (not isinstance(seed_sql, str) or len(seed_sql.encode("utf-8")) > 5_000_000):
            raise ValueError("Provide at most 5 MB of test schema/fixture SQL")
        self._preflight()
        arguments = ["create", "--name", self.name, "--label", "saferevoke.owner=" + self._owner,
                     "--pull=" + ("missing" if self.pull else "never"),
                     "--memory", f"{self.memory_mb}m", "--memory-swap", f"{self.memory_mb}m",
                     "--cpus", str(self.cpus), "--pids-limit", "256",
                     "--publish", f"127.0.0.1::{self.PORTS[self.engine]}",
                     "--tmpfs", f"{self.PATHS[self.engine]}:rw,mode=1777,size={self.storage_mb}m"]
        if self.engine == "postgres":
            arguments += ["--env", "POSTGRES_DB=saferevoke_test", "--env", "POSTGRES_USER=saferevoke",
                          "--env", "POSTGRES_PASSWORD"]
        else:
            arguments += ["--env", "MYSQL_DATABASE=saferevoke_test", "--env", "MYSQL_USER=saferevoke",
                          "--env", "MYSQL_PASSWORD", "--env", "MYSQL_ROOT_PASSWORD"]
        arguments.append(self.IMAGES[self.engine])
        self._attempted = True
        try:
            self._call(arguments)
            self._inspect_owned()
            self._call(["start", self.name])
            deadline = time.monotonic() + self.startup_timeout
            while True:
                if self._sql("SELECT 1;", check=False).returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise DockerDatabaseError("Test database did not become ready before its deadline")
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))
            info = self._inspect_owned()
            mappings = info["NetworkSettings"]["Ports"][f"{self.PORTS[self.engine]}/tcp"]
            if len(mappings) != 1 or mappings[0]["HostIp"] != "127.0.0.1":
                raise DockerDatabaseError("Expected a single loopback-only test database port")
            port = int(mappings[0]["HostPort"])
            if not 1 <= port <= 65535:
                raise DockerDatabaseError("Docker returned an invalid database port")
            self._connection = DatabaseConnection(self.engine, port, self._password)
            if seed_sql:
                self.execute(seed_sql)
            return self
        except BaseException:
            self.close()
            raise

    def _sql(self, sql, *, check=True):
        # Fixed container-side scripts read only the new container's own env.
        # The SQL itself travels over stdin, never through a shell expression.
        if self.engine == "postgres":
            script = 'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -h 127.0.0.1 -U saferevoke -d saferevoke_test -v ON_ERROR_STOP=1 -At'
        else:
            script = 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -h 127.0.0.1 -u saferevoke -D saferevoke_test --batch --skip-column-names'
        return self._call(["exec", "-i", self.name, "sh", "-c", script], input=sql, check=check)

    def execute(self, sql):
        self.connection  # Require a started database and invalidate after cleanup.
        if not isinstance(sql, str) or len(sql.encode("utf-8")) > 5_000_000:
            raise ValueError("Provide at most 5 MB of test SQL")
        self._inspect_owned()
        return self._sql(sql).stdout

    def close(self):
        if self._closed or not self._attempted:
            return
        listing = self._call(["ps", "-a", "--filter", "name=^/" + self.name + "$",
                              "--filter", "label=saferevoke.owner=" + self._owner,
                              "--format", "{{.ID}}"])
        if listing.stdout.strip():
            info = self._inspect_owned()
            self._call(["rm", "--force", "--volumes", info["Id"]])
            remaining = self._call(["ps", "-a", "--filter", "label=saferevoke.owner=" + self._owner,
                                    "--format", "{{.ID}}"])
            if remaining.stdout.strip():
                raise DockerDatabaseError("Test container removal could not be verified")
        self._connection = None
        self._closed = True

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
