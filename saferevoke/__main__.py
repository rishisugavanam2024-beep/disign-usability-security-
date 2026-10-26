"""Short terminal commands; python -m saferevoke remains supported."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from saferevoke.setup_assistant import inspect_project, setup_plan, write_setup


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="saferevoke", description="SafeRevoke local integration setup assistant")
    # Split the child command before argparse so even a child-owned `--` or
    # option named `--command` is forwarded exactly, without shell parsing.
    child_arguments = None
    if argv and argv[0] in {"database", "db"}:
        boundaries = [argv.index(marker) for marker in ("--", "--command") if marker in argv]
        if boundaries:
            separator = min(boundaries)
            child_arguments = argv[separator + 1:]
            argv = [*argv[:separator], "--command", "__child_command__"]
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "setup"):
        command = commands.add_parser(name)
        command.add_argument("project", nargs="?", default=".")
        command.add_argument("--framework", choices=("flask", "django", "fastapi"))
    test = commands.add_parser("test", help="Run isolated Flask baselines, discover exercised grants and test their removal")
    test.add_argument("project", nargs="?", default=".")
    test.add_argument("--framework", choices=("flask",), help="Resolve mixed-project detection explicitly")
    test.add_argument("--max-targets", type=int, default=10)
    test.add_argument("--timeout", type=float, default=120)
    database = commands.add_parser("database", aliases=["db"], help="Run a test command with a fresh Docker PostgreSQL/MySQL database")
    database.add_argument("engine", choices=("postgres", "mysql"))
    database.add_argument("--seed", help="Explicit test schema/fixture SQL file")
    database.add_argument("--pull", action="store_true", help="Permit downloading a missing official database image")
    database.add_argument("--startup-timeout", type=float, default=90)
    database.add_argument("--command-timeout", type=float, default=120)
    database.add_argument("--command", dest="test_command", nargs=argparse.REMAINDER, required=True,
                          help="Executable and test arguments, without a shell")
    args = parser.parse_args(argv)
    if child_arguments is not None:
        args.test_command = child_arguments
    try:
        if args.command in {"database", "db"}:
            from saferevoke.docker_database import DockerDatabase, DockerDatabaseError
            if not args.test_command or args.command_timeout <= 0:
                raise ValueError("Provide a test command and a positive command timeout")
            seed = None
            if args.seed:
                path = Path(args.seed)
                if path.stat().st_size > 5_000_000:
                    raise ValueError("Test seed SQL must be at most 5 MB")
                seed = path.read_text(encoding="utf-8-sig")
            with DockerDatabase(args.engine, pull=args.pull, startup_timeout=args.startup_timeout) as instance:
                if seed:
                    instance.execute(seed)
                environment = dict(os.environ)
                environment.update(instance.connection.environment())
                print(f"Disposable {args.engine} test database ready on loopback port {instance.connection.port}", flush=True)
                try:
                    return subprocess.run(args.test_command, env=environment, shell=False,
                                          timeout=args.command_timeout).returncode
                except subprocess.TimeoutExpired:
                    raise DockerDatabaseError("Test command timed out; resetting the disposable database") from None
        elif args.command == "test":
            from saferevoke.auto_testing import run_auto_tests
            status, summary = run_auto_tests(args.project, framework=args.framework,
                                            max_targets=args.max_targets, timeout=args.timeout)
            print(json.dumps(summary, indent=2))
            return status
        elif args.command == "inspect":
            report = inspect_project(args.project)
            print(json.dumps({"discovery": report, "plan": setup_plan(report, args.framework)}, indent=2))
        else:
            destination, plan = write_setup(args.project, framework=args.framework)
            print(json.dumps({"output": str(destination), "plan": plan}, indent=2))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"SafeRevoke setup: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
