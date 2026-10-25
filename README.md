# SafeRevoke

Licensed under the [MIT License](LICENSE).

Version [0.1.0a1 is published on PyPI](https://pypi.org/project/saferevoke/0.1.0a1/)
under the MIT License. Install the experimental Django/pytest integration with:

```shell
pip install saferevoke
```

See [publishing instructions](docs/publishing.md) for future releases.

SafeRevoke is a software-only research prototype for testing permission removal before a change reaches production. It includes a synthetic company portal, fake identities and data paths, an execution-based classifier, and an adaptive removal-order planner.

## What is implemented

- **Policy mutation:** disable one access grant in a fresh in-memory policy snapshot.
- **Runtime provenance comparison:** compare identity, resource, action and grant source before and after the mutation.
- **Computed privilege scope:** derive each identity's reachable resource/action set and calculate impact from that effective scope; grants no longer carry hand-assigned risk scores.
- **Semantic trace alignment:** match protected operations by workflow checkpoint, resource, action and occurrence, tolerating denied retries and event reordering.
- **Five cautious outcomes:** safe in tested flows, required, unsafe fallback, partial removal, delayed removal, plus unknown when coverage is insufficient.
- **Adaptive interaction discovery:** test two-grant removal orders only when a single-grant experiment exposes a fallback or residual access path.
- **Sequence planning:** test both discovered removal orders and reject a final removal when a least-privilege replacement is still required.
- **Comparative benchmark:** run three independent synthetic applications and compare SafeRevoke with policy-only request replay and exhaustive ordered-pair testing. It measures planted-interaction recall and experiment reduction; the result is synthetic evidence, not a general performance claim.

The included benchmark plants five interactions across a company portal, incident-response console and publishing service. SafeRevoke reruns application behavior after each mutation, while the control only rechecks requests present in the baseline trace. This isolates the proposed advantage: a policy-only replay can detect overlapping grants but cannot observe a different identity selected by application fallback logic after denial.

The research contribution to investigate is the combination of runtime fallback discovery with adaptive, sequence-aware permission-removal experiments. The implementation is a prototype, not evidence that the mechanism is patentable.

## Run your existing Django tests with permission removal

The repository now builds an installable Python package with an opt-in pytest
plugin. Install locally with `python -m pip install .`. Ordinary test
runs remain unchanged. To repeat selected tests under a real group-grant removal:

```powershell
python -m pytest tests/test_refunds.py --ds=myproject.test_settings --saferevoke --saferevoke-deny group:refund_operators:orders.approve_refund
```

Replace the illustrative test path, settings module and grant with your project's
own values. Test functions use their existing fixtures and assertions; they do
not need SafeRevoke workflow wrappers. HTML/JSON reports show baseline results,
failed assertions, remaining access and permission traces.

See the [pytest integration guide](docs/pytest-integration.md) for a runnable
four-test example, installation, report interpretation and current limitations.

Add `--saferevoke-selection affected` to build a fresh baseline permission-to-test
map and omit unrelated mutation variants before fixture setup. The admin example
executes 13 test bodies instead of 16 while retaining the same three detected
failures. Empty/uncertain traces stay selected. Full mode remains the default;
selection only covers observed baseline paths, not all possible dependencies.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open <http://localhost:5000>.

## SDK foundations and shared-access demonstration

The engine now accepts an `ApplicationAdapter`, data-only JSON configuration,
owner-defined output/side-effect checks, baseline coverage and HTML/JSON exports.
These are local integration foundations; an installable distribution and adapters
for external authorization systems are still future work.

To show one permission affecting two different services, stop the existing server,
then run in PowerShell:

```powershell
$env:SAFEREVOKE_CONFIG = "examples/shared_access.json"
.\.venv\Scripts\python.exe app.py
```

Select `g_inventory_read` and simulate denial. Both **Check product stock** and
**Check shipping availability** fail because their identities inherit the same
`stock_reader` permission. **Save order** remains successful. Its order write
also demonstrates state restoration: each experiment creates exactly one order,
then restores the initial state so subsequent tests start cleanly.

To return to the original company demo, stop the server and run:

```powershell
Remove-Item Env:SAFEREVOKE_CONFIG -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe app.py
```

After **Analyze all permissions**, coverage and report download links appear.
Direct download endpoints: `/api/report/html` and `/api/report/json`. Each download
runs a fresh analysis; JSON contains the baseline and per-mutation workflow traces.

For a Python integration, register approved workflow functions explicitly:

```python
from saferevoke.config import load_lab
from saferevoke.engine import SafeRevokeEngine
from saferevoke.report import render_html
from saferevoke.shared_example import RUNNERS

lab = load_lab("examples/shared_access.json", RUNNERS)
report = SafeRevokeEngine(lab).analyze()
print(report["coverage"])
```

See [integration guide](docs/integration.md) for the adapter contract and limits.

## Real Django authorization integration

An optional Django adapter now discovers actual user/group grants, removes real
permission assignments, traces Django's backend decisions and rolls back the
database after each workflow. Its demonstration exercises Django's unmodified
built-in admin views using controlled staff accounts and an in-memory SQLite DB.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-django.txt
.\.venv\Scripts\python.exe -m examples.django_admin.run --output reports/django-admin
```

Open `reports/django-admin/report.html` for the report; `evidence.json` includes
before/after traces. Verified outcomes include a shared permission blocking two
staff users, remaining group access after direct-grant removal, blocked group
creation, and database restoration even on workflow exceptions. This integration
does not yet validate a credential fallback in an independent business application.
See [Django integration instructions and compatibility](docs/django-integration.md).

## Run with Docker

```powershell
docker compose up --build
```

The container is capped at 384 MB. Open <http://localhost:5000>. Stop it with `docker compose down`.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Why the included site is enough

The demo portal is the system under test. It intentionally contains four realistic authorization behaviors: a privileged fallback, a genuinely required permission, duplicate direct/role access, and a queued operation that outlives revocation. This is safer and more reproducible than probing a public website.

The adapter interface now defines snapshot, deny, run and restore operations.
The included adapter implements these for in-memory permissions and Python data.
Adapters for databases, cloud IAM and external application state still need to be
implemented and validated before those systems can be tested.

## Research foundations

- NIST combinatorial testing and sequence-covering arrays motivate reducing a large interaction space to selected combinations and orders.
- Access-control mutation testing motivates injecting authorization changes and checking enforcement behavior.
- Delta debugging motivates isolating small failure-causing change sets.

SafeRevoke does not copy a research implementation; these ideas shape the experiment strategy. A professional patent search and legal review are still required before making novelty claims.

The completed preliminary search and claim comparison are in [`docs/prior-art-search.md`](docs/prior-art-search.md). Its conclusion is that broad policy-testing claims are crowded, while the narrow runtime fallback-edge feedback loop remains a research candidate rather than a confirmed patentable invention.
