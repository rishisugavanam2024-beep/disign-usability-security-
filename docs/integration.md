# SafeRevoke integration foundations

## Configuration

`load_lab(path, runners)` loads schema-version-1 JSON. The runnable reference is
`examples/shared_access.json`. It specifies grants, identity-to-role membership,
resource/action capability pairs, action weights, and workflows with optional
`expected_output` and `expected_side_effects`. The runner name must be present in
the explicit Python registry supplied by the caller. JSON cannot import modules
or execute code. Permission denial disables an allow grant; it does not add an
overriding deny rule, so equivalent grants can still allow access.

Role grants affect every configured identity with that role. `probe_identity`
selects a representative identity for residual-access policy checks; workflow
execution supplies evidence for the other identities actually exercised.

## Adapter contract

Pass `SafeRevokeEngine(lab, adapter)` an object implementing:

1. `snapshot()` returns enough information to restore permissions and application
   data, including relevant queues, caches and external side effects.
2. `deny(grant_ids)` applies the cumulative set of disabled grants to the test copy.
3. `run(workflow)` executes an approved workflow and returns a `WorkflowRun` with
   identity/resource/action/checkpoint/grant-source events and observed side effects.
4. `restore(snapshot)` restores all affected test state. Restoration must also
   recover from partial failure during `deny` or `run`.

The engine snapshots and restores around **each workflow**, so workflows must be
self-contained. It calls restore in `finally`, propagates restoration failures,
and serializes operations on a single engine instance. Integrations that share an
external environment across engines or processes need their own environment lock.
Snapshots must be stable copies, and returned traces must not alias resettable state.

The included `InMemoryAdapter` deep-copies Python data and resets the in-memory
policy. It cannot restore external databases or cloud systems. An external adapter
must implement and validate that restoration itself. The policy metadata used for
scope scoring must accurately reflect the external environment's effective access.

## Correctness and coverage

Explicit expectations reject incorrect output or side effects even when an app
returns success. Missing expected side-effect keys fail validation. A failing
baseline stops analysis. Mutation results are also compared with baseline output
and observed side effects. Normalize nondeterministic fields in the adapter before
returning results, and capture meaningful side effects rather than only status codes.

Coverage distinguishes permissions whose removal was tested from permissions
actually used in baseline workflows. Baseline-unexercised permissions remain
uncertain. Configured workflow coverage does not establish coverage of all paths,
users, application states or permission combinations.

## Reports and remaining limits

`render_json(report)` and `render_html(report)` return portable report strings.
Reports contain coverage, classifications, trace evidence and removal plans.
HTML escapes application-supplied content. Treat exported traces as application
data when deciding where to share them.

The delayed-revocation example in the original lab remains a planted synthetic
event; it does not measure a real queue or token lifetime. The shared-access
example exercises real Python state writes and reset, but remains synthetic too.
Removal-order testing evaluates cumulative permission states with fresh workflow
data; it does not yet reproduce long-running stateful transactions between changes.
Benchmark numbers apply to the controlled suite, and exhaustive experiment counts
are calculated from the candidate space, not timed production measurements.

The optional [Django adapter](django-integration.md) now exercises the real Django
admin authorization system and database rollback. Packaging this API and validating
against a separately maintained business application remain further milestones.
