# External application commands

SafeRevoke 0.1.0a4 adds native CLI commands for explicitly configured Java, Node,
FastAPI and other application connectors. The library owns the CLI, baseline
validation, analysis engine and report rendering. Application code supplies its
permission inventory, workflows, observations and reset/control hooks.

```shell
saferevoke --help
saferevoke --help-all
saferevoke connector
saferevoke permissions alice
saferevoke revoke alice WRITE
saferevoke grant alice WRITE
saferevoke baseline
saferevoke test
saferevoke report
saferevoke report --open
```

`restore` is an alias for `grant`. These controls call the configured application's
test permission API; they are not a new authorization server. Restoration semantics
belong to the connector (for Dibsly it removes a per-account restriction and cannot
add permissions outside the user's role). Controls persist until restored; analysis
trials instead use the adapter's snapshot/restore lifecycle.

## Configuration

Create `saferevoke.json` in the application's folder:

```json
{
  "schema_version": 1,
  "name": "my-application",
  "test_environment": true,
  "module": "testing/connector.py",
  "reports": "reports/saferevoke",
  "options": {}
}
```

Module/report paths must stay inside this folder. `--connector path/to/config.json`
selects another configuration explicitly. `saferevoke test PROJECT` uses that
project's configuration when present, otherwise retains the Flask flow. Invalid
external configuration fails; it never silently falls back to a different test.
`--framework flask` explicitly selects Flask and cannot be combined with
`--connector`. Existing Django pytest options and Docker commands remain available.

The module is **trusted executable Python**, not a sandbox. Only use configurations
and hooks you own/trust, with isolated test data and explicit authorization. The
`test_environment` flag is an opt-in, not proof of isolation. The connector must
validate its target and credentials, confine permission changes, enforce timeouts,
and restore database/session/external effects. Never configure production data.
Do not put credentials in committed JSON; use the application's normal secret flow.

## Connector contract

```python
from saferevoke.external import ExternalAnalysis

def create_analysis(root, output, options):
    # Build the existing Lab and ApplicationAdapter for your application.
    # The adapter owns snapshot(), deny(grant_ids), run(workflow), restore(snapshot).
    lab, adapter = make_test_application(root, output, options)
    return ExternalAnalysis(lab, adapter, evidence=verified_evidence, close=close_resources)

def control(action, subject, permission, root, options):
    # action is permissions, revoke, or restore. grant maps to restore.
    # Authenticate/authorize through the target's normal test management API.
    # Return a JSON-serializable result only after verifying the target state.
    return manage_test_permission(action, subject, permission)
```

`root` and `output` are absolute Paths; `options` is the JSON options object.
`evidence()` returns a dictionary added to the report. `close()` is called even
when engine execution or validation fails; cleanup failures propagate. Factories
must clean up their own resources if they fail before returning ExternalAnalysis.
The library executes every configured workflow through the existing engine.
Baseline checks verify expected outputs/effects and fail before removal analysis
if the application does not pass. `--max-targets` bounds configured external grants
(default 10); external connectors own their subprocess/network timeouts.

Each run gets a unique output directory. Only runs whose engine, evidence and
cleanup succeed receive a completion marker. `report` locates the most recent
completed full analysis, excluding incomplete and baseline-only runs. `--open`
opens its local HTML file explicitly. Help, `connector`, and `report` do not import
the connector module or access the target application. An analysis report describes
only the configured coverage; UNKNOWN is not proof that removal is safe.
