# Demonstrate Dibsly with the published SafeRevoke CLI

Use the native `saferevoke` commands below. Dibsly remains an independent Java application; its executable contains neither SafeRevoke nor the external connector. The Python library owns CLI dispatch, analysis and reporting. Application-owned hooks connect its generic API to Dibsly.

## 1. Run the website before installing the library

```powershell
cd 'D:\OneDrive\Documents\ChatGPT\safe revoke\dibsly'
.\presentation.ps1 start
python tools/verify-library-artifact.py
```

Show http://localhost:8093. The PowerShell launcher here starts Java only. Show the zero embedded SafeRevoke/connector entries from the actual JAR inspection. Client and freelancer logins are `client.demo` and `freelancer.demo`, both with `DibslyDemo2026!`; use separate browser sessions. Admin is `admin` / `DibslyAdmin2026!`.

## 2. Show the library source and published package, then install it

Source: https://github.com/rishisugavanam2024-beep/disign-usability-security-
Release: https://pypi.org/project/saferevoke/0.1.0a4/

Only claim the new version is published after this release page and pip serve it. The existing developer environment is separate from this presentation environment. Do not describe an already-installed environment as a fresh install.

```powershell
python -m venv .local/presentation/python
.\.local\presentation\python\Scripts\Activate.ps1
pip install --upgrade saferevoke==0.1.0a4
pip show saferevoke
saferevoke --version
saferevoke --help
```

`--help` lists all commands/aliases, independent of the connected application. `--help-all` shows every command's options/examples. `python -m saferevoke` uses the same implementation if the executable is not on PATH. Installing the library does not inject it into Java or automatically connect arbitrary sites.

## 3. Show the explicit application connection

```powershell
saferevoke connector
```

Point to `saferevoke.json` and `integrations/saferevoke-python/connector.py`. The JSON identifies trusted application-owned hooks. `connector` reads configuration without executing those hooks. It reports the separate report folder and explicit test-environment opt-in. The library is generic; these hooks supply Dibsly-specific inventory, controls, workflows, observations and reset logic.

## 4. Change the live site's permissions from native library commands

As client, publish a new project. As freelancer, open that project's form, fill a valid pitch and leave it unsubmitted. Keep that session signed in.

```powershell
saferevoke permissions freelancer.demo
saferevoke revoke freelancer.demo SUBMIT_PROPOSAL
```

The second command must report REVOKED. Submit the already-open browser form: Dibsly rejects it with HTTP 403 and saves no pitch. The library CLI invokes the connector, which uses the site's normal authenticated administrator API/forms. Dibsly enforces the stored restriction.

```powershell
saferevoke grant freelancer.demo SUBMIT_PROPOSAL
saferevoke permissions freelancer.demo
```

`grant` (alias `restore`) removes the restriction; it does not add a permission outside the user's role. Return to the project and submit again without logging in. It succeeds. Use a new project on repeat demonstrations to avoid duplicate-pitch validation.

## 5. Run the actual library analysis

```powershell
saferevoke test
```

The published CLI reads the external configuration, calls the connector factory, and runs `SafeRevokeEngine` itself. It prints the loaded library version/path and each workflow/removed-grant combination. Four baselines plus four workflows under each of five removals produce 24 real HTTP trials. This takes several minutes. `saferevoke baseline` is an optional shorter baseline-only run; `test` already includes baselines.

The connector runs disposable instances of the same Dibsly JAR with fresh in-memory databases. It does not mutate the live presentation database. Trials prepare real forms, change permissions after login, submit in the same session, inspect actual HTTP/database outcomes and verify complete reset. It provides no fabricated failure/classification results.

## 6. Open the library-generated report

```powershell
saferevoke report
saferevoke report --open
```

The first prints the latest completed analysis's HTML/JSON paths; the second opens its HTML file. Incomplete runs and baseline-only reports are not presented as completed analysis. No localhost report server is needed.

Expected findings: `client_post`, `talent_pitch`, `client_hire`, and `talent_withdraw` are REQUIRED_ACCESS for their tested workflows. `client_manage` is UNKNOWN because closing/completing a project is not covered. Required access is a dependency, not a security defect; unknown is not safe removal.

Expand full execution evidence. `integration.evidence.connector_trials` contains the 24 actual runs, including denied events, HTTP 403, unchanged business counts, session continuity, and verified cleanup. Generic renderer benchmark counters are model counters, not production performance measurements. The report covers these configured workflows, not every application branch.

## Finish

```powershell
.\presentation.ps1 stop
```

This stops only the presentation server and preserves its data. The installed Python environment is also preserved. Manual revoke/grant commands persist until changed; the automated analysis separately restores each disposable trial.
