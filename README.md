# SafeRevoke

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

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open <http://localhost:5000>.

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

An eventual staging-system adapter would need to supply: a permission mutation interface, approved workflow scripts, an execution trace collector, output checks and a reset operation. Production mutation is intentionally outside this prototype.

## Research foundations

- NIST combinatorial testing and sequence-covering arrays motivate reducing a large interaction space to selected combinations and orders.
- Access-control mutation testing motivates injecting authorization changes and checking enforcement behavior.
- Delta debugging motivates isolating small failure-causing change sets.

SafeRevoke does not copy a research implementation; these ideas shape the experiment strategy. A professional patent search and legal review are still required before making novelty claims.

The completed preliminary search and claim comparison are in [`docs/prior-art-search.md`](docs/prior-art-search.md). Its conclusion is that broad policy-testing claims are crowded, while the narrow runtime fallback-edge feedback loop remains a research candidate rather than a confirmed patentable invention.
