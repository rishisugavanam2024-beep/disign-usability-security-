# Native SafeRevoke CLI connection for Dibsly

The current presentation uses **SafeRevoke 0.1.0a4** with `../../saferevoke.json` and `connector.py`. Follow [the presentation guide](../../PYTHON-LIBRARY-DEMO.md). Run `saferevoke --help` for the complete command list, then use `saferevoke permissions`, `revoke`, `grant`, `baseline`, `test`, and `report --open` directly. The published library owns dispatch, engine execution and report rendering. This connector owns application-specific HTTP permissions, workflow inventory, database assertions and reset.

`connector.py:create_analysis` returns the library's `ExternalAnalysis` contract. It reuses the existing tested Java HTTP harness; it does not classify results or implement a second engine. `control` uses Dibsly's ordinary authenticated administrator forms, restricted to the local presentation target. Native report evidence is nested under `integration.evidence` and includes all 24 trials and verified cleanups.

The older `run_demo.py` / `run-demo.ps1` path below remains a developer compatibility runner. Use the native CLI for the examiner presentation.

# Test Dibsly with the original Python SafeRevoke package

This connector runs the existing packaged Dibsly web application and uses **Python `saferevoke` 0.1.0a3** to analyze permission removal. It adds no test routes, Python imports, fake business results, or classification logic to the marketplace. The connector lives outside the application source and is not included in the application JAR.

For the live install-from-scratch sequence, follow [the presentation guide](../../PYTHON-LIBRARY-DEMO.md). The prepared environment below is only for developer verification.

## Quick verification on this machine

Open PowerShell in the Dibsly folder:

```powershell
cd 'D:\OneDrive\Documents\ChatGPT\safe revoke\dibsly'
.\integrations\saferevoke-python\run-demo.ps1
```

The prepared environment uses the **PyPI distribution**, installed in `.local/python-connector/venv`, rather than importing the original development checkout. The command prints the actual imported package path and version, then the workflow and removed permission for each trial. It finishes with HTML and JSON report paths under `reports/python-saferevoke/<unique-run>/`. Open the HTML file in a browser; no report web server or localhost URL is required.

For a short first step with normal permissions only:

```powershell
.\integrations\saferevoke-python\run-demo.ps1 -BaselineOnly
```

That runs the four real website workflows, checks their HTTP results and database effects, and saves baseline JSON evidence. The full command also reruns baselines before trying each permission removal, so a failing baseline stops the analysis.

## Install externally on another machine

Use Python 3.10+ and a Java 21 JDK. From the Dibsly folder:

```powershell
python -m venv .local/python-connector/venv
.\.local\python-connector\venv\Scripts\python.exe -m pip install saferevoke==0.1.0a3
.\integrations\saferevoke-python\run-demo.ps1 -JavaExecutable 'C:\path\to\jdk-21\bin\java.exe'
```

The prepared environment contains the published package and its declared dependencies; `pip check` passed. This command connector itself uses the standard-library-based engine and does not need Django test execution. No package source was changed.

If the app JAR does not exist, build the existing project first with `mvnw.cmd -f reactor/pom.xml verify`. The runner compiles only the external Java test connector against that JAR, without changing or rebuilding Dibsly itself.

## What is executed

| Workflow | Real application request | Database assertions when allowed |
| --- | --- | --- |
| Client publishes a project | `POST /app/action/request` | One new project; no pitch/contract changes |
| Freelancer submits a pitch | `POST /app/action/proposal` | One new pitch; no project/contract changes |
| Client hires a freelancer | `POST /app/action/accept` | One contract; project BOOKED; pitch ACCEPTED |
| Freelancer withdraws a pitch | `POST /app/action/withdraw` | One pitch becomes WITHDRAWN |

Each workflow uses the real login form, session cookie, CSRF token, JSP form page, servlet, service, and database code from the existing Dibsly JAR. Permissions are removed after login and form preparation. The same session then submits the request. The runner observes the HTTP status, actual authorization audit rows, and database effects. Successful traces identify the effective grant belonging to the authenticated test account; denied traces have no granting source.

Five effective per-user grants are inventoried: client posting, freelancer pitching, client hiring, freelancer withdrawal, and client project management. The last is deliberately outside these four workflows and must be reported as **UNKNOWN**, not safe. The expected four REQUIRED_ACCESS findings establish dependencies; they do not mean the website has an authorization vulnerability. No unsafe fallback has been inserted into Dibsly to manufacture a finding.

## Isolation and restoration

`CommandAdapter` invokes a separate Java process for every baseline/removal workflow. The connector uses a hardcoded in-memory H2 URL, fresh synthetic accounts, and a new loopback-only server on a temporary port. It does not accept a production DB URL or use the preview database. Test data setup uses Dibsly's existing data APIs; every operation being evaluated is performed over HTTP.

Before mutation, the connector snapshots the entire test database using H2 SCRIPT. After execution it closes the HTTP client and server (discarding sessions), restores that snapshot, and checks that a new SCRIPT output matches exactly. A failure stops the experiment. Python removes only the specifically owned per-trial directory under the unique report folder, including Tomcat and application scratch files. The Java process exits, discarding the in-memory database. Every successful report records the number of completed trials and verified cleanups.

This covers the selected marketplace workflows. Dibsly currently has no payment/email/worker integrations in these paths; adding external effects requires explicit isolation and reset work. A subprocess is not an OS sandbox. Do not repurpose the connector against production data.

## Explain the separation accurately

Dibsly uses its own role, ownership, account restriction, transaction, and audit code. It contains no Java Safe Revoke library and no Python package. The original Python SafeRevoke 0.1.0a3 is installed externally: its CommandAdapter, SafeRevokeEngine, and HTML/JSON renderer produce the analysis report.

`manage_permissions.py` is an external terminal client for Dibsly's ordinary authenticated administrator forms. It is application-specific glue, not a feature of the published package. `grant` restores a permission already belonging to the account's role. The published library determines the analysis findings; it does not magically control arbitrary websites after installation.

The live terminal exercise uses the dedicated site on port 8093. Automated analysis launches disposable instances of the same application JAR with synthetic users and data; it does not alter the presentation database. Dibsly remains your marketplace project, not an independently maintained third-party application.

The connector is application-specific integration code: inventory, HTTP workflows, observation, and reset. `pip install` alone cannot discover arbitrary app permissions. Current audit-based tracing covers selected protected writes, not private-read checks, rejected login/CSRF attempts, or every branch. Policy source mapping represents effective per-user grants inherited from Dibsly roles; it does not claim global role mutation.

## Read the report to the examiner

1. Show Dibsly's normal marketplace separately: a project, pitch, and hiring flow.
2. Show the package installation/import path outside the site and the connector folder.
3. Run baselines: all four workflows should pass their HTTP and database assertions.
4. Run the full analysis. For example, removing `talent_pitch` should stop only the pitch workflow, with an actual 403 and no pitch inserted.
5. Open the HTML report. Explain REQUIRED_ACCESS versus UNKNOWN and expand full execution evidence to show baseline/mutated traces, database effects, and restoration counts.
6. State the coverage honestly: four configured workflows, two synthetic users, and five selected grants; no claim that all application branches were tested.

The report renderer is the original library renderer. Generic benchmark counters in its raw evidence are model counters, not measurements of production performance or a planted-vulnerability score for Dibsly.
