"""Short terminal commands; python -m saferevoke remains supported."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from saferevoke.setup_assistant import inspect_project, setup_plan, write_setup
from saferevoke import __version__


def build_parser():
    parser = argparse.ArgumentParser(
        prog="saferevoke",
        description="Test what changes when an application's test permission is removed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick start (inside your application folder):
  saferevoke inspect             Detect frameworks and existing tests; no app execution.
  saferevoke setup               Generate setup templates without overwriting files.
  saferevoke test                Test a configured external connector or Flask app.
  saferevoke connector           Describe saferevoke.json without running its code.
  saferevoke permissions USER    Show permissions through the configured connector.
  saferevoke revoke USER PERM    Revoke a test permission through that connector.
  saferevoke grant USER PERM     Restore a previously available test permission.
  saferevoke baseline            Run external workflows without removing permissions.
  saferevoke report --open       Open the latest completed external analysis report.
  saferevoke --help-all          Show every command, option and example together.

Django testing uses pytest separately, for example:
  python -m pytest tests/ --saferevoke --saferevoke-deny user:alice:auth.view_user

Reports: test runs write HTML/JSON files and print their location.
External connectors are trusted local Python code configured in saferevoke.json.
Installing the package alone does not connect an application or grant permissions.
Use 'saferevoke COMMAND --help' for command-specific details.""")
    parser.add_argument("--version", action="version", version=f"SafeRevoke {__version__}")
    parser.add_argument("--help-all", action="store_true",
                        help="Show detailed help and examples for all commands, then exit")
    commands = parser.add_subparsers(dest="command", title="commands", metavar="COMMAND")
    details = []
    for name in ("inspect", "setup"):
        summary = ("Detect frameworks, test files and configuration hints without running the app"
                   if name == "inspect" else "Generate setup instructions and an integration template")
        explanation = ("Read project source and print JSON discovery evidence. This does not import\n"
                       "the application, execute tests, install dependencies or change permissions."
                       if name == "inspect" else
                       "Create saferevoke-setup/ containing a plan, discovery evidence and a Flask\n"
                       "fixture example. Existing configuration is never overwritten. The template\n"
                       "still needs a connection to the application's actual test permission store.")
        command = commands.add_parser(
            name, help=summary, description=explanation,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"Examples:\n  saferevoke {name}\n  saferevoke {name} my-app --framework flask")
        command.add_argument("project", nargs="?", default=".", metavar="PROJECT",
                             help="Application folder (default: current directory)")
        command.add_argument("--framework", choices=("flask", "django", "fastapi"),
                             help="Choose a framework for mixed projects; otherwise detect it automatically")
        details.append((name, command))
    test = commands.add_parser(
        "test", help="Analyze permission removal through an external connector or Flask tests",
        description="Use saferevoke.json when present, or run configured Flask tests otherwise.\n"
                    "External connectors supply a Lab and adapter; SafeRevoke runs its analysis engine.\n"
                    "Requires an isolated test app, a saferevoke_flask fixture, permission tracing\n"
                    "and reliable state-reset hooks. Unexercised access remains unknown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  saferevoke test
  saferevoke test my-app --max-targets 5 --timeout 180
  saferevoke test --connector saferevoke.json

Results: new reports/saferevoke-auto/ folders contain summary.json and HTML/JSON
reports. Permission-dependent assertion failures return a nonzero exit status.
Automatic framework discovery targets Flask; Java/Node/custom apps use explicit
external connectors. Django also supports its pytest flags.""")
    test.add_argument("project", nargs="?", default=".", metavar="PROJECT",
                      help="Application/configuration folder (default: current directory)")
    test.add_argument("--connector", metavar="JSON_FILE", help="Explicit external connector configuration; otherwise detect PROJECT/saferevoke.json")
    test.add_argument("--framework", choices=("flask",),
                      help="Explicitly select Flask if the project contains multiple framework hints")
    test.add_argument("--max-targets", type=int, default=10, metavar="COUNT",
                      help="Grant limit: configured external grants or exercised Flask grants (default: %(default)s)")
    test.add_argument("--timeout", type=float, default=120, metavar="SECONDS",
                      help="Flask pytest subprocess timeout; external connectors own their timeouts (default: %(default)s seconds)")
    details.append(("test", test))
    summaries = {
        "connector": "Describe the external connector configuration without executing it",
        "permissions": "List a subject's permissions through the external test connector",
        "revoke": "Remove a subject's test permission through the external connector",
        "grant": "Restore a subject's test permission (alias: restore)",
        "baseline": "Validate external workflows and cleanup without removing permissions",
        "report": "Locate or open the latest completed external HTML/JSON analysis report",
    }
    for name, summary in summaries.items():
        aliases = ["restore"] if name == "grant" else []
        command = commands.add_parser(name, aliases=aliases, help=summary, description=summary,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""Examples:
  saferevoke connector --connector saferevoke.json
  saferevoke permissions alice
  saferevoke revoke alice EXPORT_INVOICE
  saferevoke grant alice EXPORT_INVOICE
  saferevoke baseline
  saferevoke report --open

External commands use trusted application-owned Python hooks. Configuration:
  {"schema_version": 1, "name": "my-app", "test_environment": true,
   "module": "connector.py", "reports": "reports/saferevoke", "options": {}}
The module implements create_analysis(root, output, options) and optionally
control(action, subject, permission, root, options). See docs/external-connectors.md.
Permission commands change only the configured test target; installing SafeRevoke
does not discover credentials or connect arbitrary applications.""")
        command.add_argument("--connector", metavar="JSON_FILE", help="Connector configuration (default: ./saferevoke.json)")
        if name in {"permissions", "revoke", "grant"}:
            command.add_argument("subject", help="Application-specific test user or subject identifier")
        if name in {"revoke", "grant"}:
            command.add_argument("permission", help="Application-specific permission identifier")
        if name == "baseline":
            command.add_argument("--max-targets", type=int, default=10, help="Maximum configured grants (default: %(default)s)")
        if name == "report":
            command.add_argument("--open", action="store_true", dest="open_browser", help="Open the completed HTML report in your browser")
        details.append((name + (" (alias: restore)" if aliases else ""), command))
    database = commands.add_parser(
        "database", aliases=["db"], help="Run a test command with a disposable PostgreSQL or MySQL database",
        usage="%(prog)s {postgres,mysql} [options] -- COMMAND [ARGS ...]",
        description="Start a fresh Docker test database, optionally load test SQL, run your test\n"
                    "command, then clean up the owned container. Requires a running local Docker\n"
                    "engine in Linux-container mode. Your app must use the supplied DATABASE_URL\n"
                    "or SAFEREVOKE_DB_* variables and provide its schema and reset hooks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples (place database options before --):
  saferevoke db postgres -- pytest tests/
  saferevoke db mysql --pull -- pytest tests/
  saferevoke db postgres --seed test-schema.sql -- pytest tests/

The database is disposable; it is not a copy of production data. The test command
runs without a shell. 'database' and 'db' are the same command; the older
'--command EXECUTABLE ...' spelling is also supported.""")
    database.add_argument("engine", choices=("postgres", "mysql"), help="Database server to provision for the test command")
    database.add_argument("--seed", metavar="SQL_FILE", help="Load this test schema/fixture SQL file before tests (maximum 5 MB)")
    database.add_argument("--pull", action="store_true", help="Allow a missing official image to download; otherwise require a cached image")
    database.add_argument("--startup-timeout", type=float, default=90, metavar="SECONDS",
                          help="Time limit for database readiness (default: %(default)s seconds)")
    database.add_argument("--command-timeout", type=float, default=120, metavar="SECONDS",
                          help="Time limit for the child test command (default: %(default)s seconds)")
    database.add_argument("--command", dest="test_command", nargs=argparse.REMAINDER, required=True,
                          help="Legacy spelling for -- COMMAND [ARGS ...]; pass the executable and its arguments")
    details.append(("database (alias: db)", database))
    return parser, details


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser, details = build_parser()
    # Preserve child-owned options verbatim, including --help-all and --.
    child_arguments = None
    if argv and argv[0] in {"database", "db"}:
        boundaries = [argv.index(marker) for marker in ("--", "--command") if marker in argv]
        if boundaries:
            separator = min(boundaries)
            child_arguments = argv[separator + 1:]
            argv = [*argv[:separator], "--command", "__child_command__"]
    args = parser.parse_args(argv)
    if args.help_all:
        parser.print_help()
        for name, command in details:
            print(f"\nDetailed help: {name}\n")
            command.print_help()
        return 0
    if args.command is None:
        parser.error("Choose a command, or use --help-all to see every command and example")
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
            from saferevoke import external
            if args.connector or (not args.framework and (Path(args.project) / external.DEFAULT_CONFIG).is_file()):
                if args.framework:
                    raise ValueError("Choose either --connector or --framework, not both")
                external.analyze(external.configuration(args.connector, args.project), max_targets=args.max_targets)
                return 0
            from saferevoke.auto_testing import run_auto_tests
            status, summary = run_auto_tests(args.project, framework=args.framework,
                                            max_targets=args.max_targets, timeout=args.timeout)
            print(json.dumps(summary, indent=2))
            return status
        elif args.command in {"connector", "permissions", "revoke", "grant", "restore", "baseline", "report"}:
            from saferevoke import external
            config = external.configuration(args.connector)
            if args.command == "connector":
                print(json.dumps(external.describe(config), indent=2))
            elif args.command == "baseline":
                external.analyze(config, baseline_only=True, max_targets=args.max_targets)
            elif args.command == "report":
                print(json.dumps(external.latest_report(config, open_browser=args.open_browser), indent=2))
            else:
                result = external.control(config, args.command, args.subject, getattr(args, "permission", None))
                print(json.dumps(result, indent=2))
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
