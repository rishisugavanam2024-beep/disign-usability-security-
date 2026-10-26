"""Docker lifecycle contracts plus explicitly opt-in real database checks."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from saferevoke.docker_database import DatabaseConnection, DockerDatabase, DockerDatabaseError


class FakeDocker:
    """A deterministic Docker CLI contract double, not a real SQL server."""

    def __init__(self):
        self.calls = []
        self.exists = False
        self.name = self.owner = None
        self.fail_start = self.fail_seed = self.fail_remove = self.foreign = False
        self.fail_info = self.fail_ready = False
        self.container_id = "a" * 64
        self.context = "unix:///var/run/docker.sock"

    def __call__(self, command, **kwargs):
        args = command[1:]
        self.calls.append((args, kwargs))
        code, output = 0, ""
        if args[0] == "context":
            output = json.dumps(self.context)
        elif args[0] == "info":
            code = 1 if self.fail_info else 0
            output = "linux\n"
        elif args[0] == "create":
            self.exists = True
            self.name = args[args.index("--name") + 1]
            self.owner = args[args.index("--label") + 1].split("=", 1)[1]
            output = self.container_id
        elif args[0] == "inspect":
            output = json.dumps([{"Id": self.container_id, "Name": "/" + self.name,
                "Config": {"Labels": {"saferevoke.owner": "someone-else" if self.foreign else self.owner}},
                "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54321"}],
                                              "3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "54322"}]}}}])
        elif args[0] == "start":
            code = 1 if self.fail_start else 0
        elif args[0] == "exec":
            code = 1 if self.fail_seed and kwargs.get("input") != "SELECT 1;" else 0
            if self.fail_ready:
                code = 1
            output = "1\n" if code == 0 else ""
        elif args[0] == "ps":
            output = self.container_id if self.exists and not self.foreign else ""
        elif args[0] == "rm":
            code = 1 if self.fail_remove else 0
            if code == 0:
                self.exists = False
        else:
            raise AssertionError("Unexpected Docker command")
        return subprocess.CompletedProcess(command, code, stdout=output, stderr="sensitive details omitted")


class DockerContractTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeDocker()
        self.patches = [patch("saferevoke.docker_database.shutil.which", return_value="docker"),
                        patch("saferevoke.docker_database.subprocess.run", side_effect=self.backend),
                        patch.dict(os.environ, {"DOCKER_HOST": ""})]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_both_engines_start_seed_and_remove_only_owned_containers(self):
        for engine in ("postgres", "mysql"):
            with self.subTest(engine=engine):
                with DockerDatabase(engine) as database:
                    self.assertEqual(database.execute("CREATE TABLE demo (id INTEGER);"), "1\n")
                    self.assertEqual(database.connection.host, "127.0.0.1")
                    self.assertNotIn(database.connection.password, repr(database.connection))
                    self.assertIn("saferevoke_test", database.connection.url)
                    password = database.connection.password
                self.assertFalse(self.backend.exists)
                with self.assertRaises(DockerDatabaseError):
                    database.connection
                create = [args for args, kwargs in self.backend.calls if args[0] == "create"][-1]
                self.assertIn("--pull=never", create)
                self.assertIn("512m" if engine == "postgres" else "1024m", create)
                self.assertIn("127.0.0.1::" + str(DockerDatabase.PORTS[engine]), create)
                self.assertIn("--tmpfs", create)
                self.assertTrue(all(password not in " ".join(args) for args, kwargs in self.backend.calls))
                removes = [args for args, kwargs in self.backend.calls if args[0] == "rm"]
                self.assertEqual(removes[-1], ["rm", "--force", "--volumes", self.backend.container_id])

    def test_application_exception_still_cleans_up(self):
        with self.assertRaisesRegex(ValueError, "business failure"):
            with DockerDatabase():
                raise ValueError("business failure")
        self.assertFalse(self.backend.exists)

    def test_partial_start_and_seed_failures_remove_created_container(self):
        for failure in ("fail_start", "fail_seed"):
            with self.subTest(failure=failure):
                setattr(self.backend, failure, True)
                try:
                    with self.assertRaises(DockerDatabaseError):
                        DockerDatabase().start(seed_sql="CREATE TABLE demo (id INTEGER);")
                    self.assertFalse(self.backend.exists)
                finally:
                    setattr(self.backend, failure, False)

    def test_cleanup_failure_is_not_suppressed(self):
        self.backend.fail_remove = True
        with self.assertRaises(DockerDatabaseError):
            with DockerDatabase():
                pass
        self.assertTrue(self.backend.exists)

    def test_foreign_container_is_never_deleted(self):
        self.backend.foreign = True
        with self.assertRaisesRegex(DockerDatabaseError, "ownership"):
            DockerDatabase().start()
        self.assertFalse(any(args[0] == "rm" for args, kwargs in self.backend.calls))

    def test_remote_context_is_rejected_before_creation(self):
        self.backend.context = "ssh://remote.example"
        with self.assertRaisesRegex(DockerDatabaseError, "not local"):
            DockerDatabase().start()
        self.assertFalse(any(args[0] == "create" for args, kwargs in self.backend.calls))

    def test_missing_docker_and_daemon_failures_do_not_run_tests(self):
        with patch("saferevoke.docker_database.shutil.which", return_value=None):
            with self.assertRaisesRegex(DockerDatabaseError, "not installed"):
                DockerDatabase().start()
        self.assertFalse(self.backend.calls)
        self.backend.fail_info = True
        with self.assertRaises(DockerDatabaseError):
            DockerDatabase().start()
        self.assertFalse(any(args[0] == "create" for args, kwargs in self.backend.calls))

    def test_readiness_timeout_removes_the_partial_environment(self):
        self.backend.fail_ready = True
        with self.assertRaisesRegex(DockerDatabaseError, "deadline"):
            DockerDatabase(startup_timeout=0.01).start()
        self.assertFalse(self.backend.exists)

    def test_connection_env_contains_only_ephemeral_database_credentials(self):
        connection = DatabaseConnection("mysql", 54322, "temporary-test-secret")
        self.assertEqual(connection.environment()["DATABASE_URL"], connection.url)
        self.assertEqual(connection.environment()["SAFEREVOKE_DB_NAME"], "saferevoke_test")
        self.assertNotIn("temporary-test-secret", repr(connection))

    def test_cli_passes_database_only_to_child_and_preserves_test_exit_status(self):
        from saferevoke.__main__ import main
        real_backend = self.backend

        def execute(command, **kwargs):
            if command[0] == "docker":
                return real_backend(command, **kwargs)
            self.assertEqual(command, ["test-runner", "tests/"])
            self.assertIn("DATABASE_URL", kwargs["env"])
            self.assertFalse(kwargs["shell"])
            return subprocess.CompletedProcess(command, 1)

        initial = os.environ.get("DATABASE_URL")
        with patch("saferevoke.docker_database.subprocess.run", side_effect=execute):
            self.assertEqual(main(["database", "postgres", "--command", "test-runner", "tests/"]), 1)
        self.assertEqual(os.environ.get("DATABASE_URL"), initial)
        self.assertFalse(self.backend.exists)

    def test_short_database_command_preserves_child_arguments_and_exit_code(self):
        from saferevoke.__main__ import main
        real_backend = self.backend

        def execute(command, **kwargs):
            if command[0] == "docker":
                return real_backend(command, **kwargs)
            self.assertEqual(command, ["test-runner", "tests/", "--", "-x"])
            self.assertFalse(kwargs["shell"])
            return subprocess.CompletedProcess(command, 7)

        for options in (["db", "postgres", "--", "test-runner", "tests/", "--", "-x"],
                        ["database", "postgres", "--command", "test-runner", "tests/", "--", "-x"]):
            with self.subTest(options=options), patch("saferevoke.docker_database.subprocess.run", side_effect=execute):
                self.assertEqual(main(options), 7)
                self.assertFalse(self.backend.exists)


@unittest.skipUnless(os.environ.get("SAFEREVOKE_DOCKER_LIVE") == "1", "Set SAFEREVOKE_DOCKER_LIVE=1 with a running Docker engine and cached images")
class DockerLiveTests(unittest.TestCase):
    def test_real_postgres_and_mysql_seed_query_and_cleanup(self):
        seed = (Path(__file__).resolve().parents[1] / "examples" / "docker_database" / "schema.sql").read_text()
        for engine in ("postgres", "mysql"):
            with self.subTest(engine=engine):
                database = DockerDatabase(engine)
                try:
                    database.start(seed_sql=seed)
                    self.assertEqual(database.execute("SELECT COUNT(*) FROM orders;").strip(), "1")
                finally:
                    database.close()


if __name__ == "__main__":
    unittest.main()
