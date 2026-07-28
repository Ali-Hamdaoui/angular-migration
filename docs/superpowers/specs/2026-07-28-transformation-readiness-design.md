# Transformation readiness completion design

## Scope

Complete the confirmed S2-F06/S2-F07 transformation-readiness gaps from the
code-truth audit, while preserving the existing uncommitted planning document.
The work is delivered as independently testable changes in dependency order;
it does not start an Angular transformation, change approval-gate semantics,
or mutate an external source workspace.

## Architecture

### 1. Planning review reachability

The default governed prompt registry will define `planning_agent_v1` for
`PLAN_RATIONALE` and `planning_reviewer_v1` for `PLANNING_REVIEW`. Planning
review continues to use the Azure gateway and its existing structured schemas.
Failure evidence will retain safe gateway classification metadata (stage,
subtype, retryability, provider request identifier, and transport-started
state) without persisting secrets or raw provider payloads.

### 2. Single command authority

A shared, immutable transformation command catalogue will own each command's
identifier, template identifier, executable, exact argument contract, timeout,
and network profile. The planner produces references from this catalogue; the
database command-template seed and worker registry derive from the same data.
The worker receives only the stage's approved mutable workspace aliases, with
the logical stage alias bound to a contained sandbox path. This preserves
policy enforcement and removes planner/policy/worker drift.

### 3. Safe, durable stage preparation

After validating a current approved G06, protected stage start prepares a
temporary sibling sandbox under the registered root, fingerprints it, and only
then atomically finalizes the sandbox and persists the authoritative stage/step
rows, distinct immutable preparation-report and workspace-fingerprint
artifacts, a stage-specific alias binding, and ordered completion transitions.
The first planned command is authorized or queued exactly once only after that
durable preparation boundary. Source-equal,
descendant/ancestor, escaping, and unsafe-symlink copy topologies fail before
copying. Filesystem work occurs outside database transactions; failed copies
leave no success state and are cleaned up or recorded as quarantined residue,
including failures after copying but before persistence. Idempotent replay
returns the same durable preparation and continuation result.

### 4. Project and runtime correctness

Project resolution facts (selected build/test/lint targets, package scripts,
and npm configuration) become immutable plan inputs and drive generated
commands. The compatibility catalogue specifies each stage's valid Node/npm/CLI
profile, so Angular 20 and 21 cannot reuse Node 20.11.1. Exact package pins
remain deterministic but are explicitly supported by catalogue evidence.

## Delivery order

1. Prompt governance and safe diagnostic evidence.
2. Shared command catalogue, alias binding, and generated-plan policy/worker
   contract tests.
3. Sandbox containment and negative topology tests.
4. Stage-preparation vertical slice and idempotency/compensation tests.
5. Project-aware command generation and stage-specific runtime catalogue tests.
6. G05-to-G06-to-first-authorized-command dry run using real persistence,
   command-policy authorization, worker validation, alias binding, and stage
   artifacts, followed by relevant backend and frontend regression checks.

## Testing

Focused tests will prove production prompt request construction, every
generated command's database-policy and worker acceptance, alias confinement,
sandbox failure topology and post-copy compensation, durable
stage/step/artifact/alias creation, ordered transitions, exactly-once first
command continuation, replay safety, project-target propagation, and runtime
compatibility. The final dry run uses real persistence and artifact services
with a controlled gateway transport; it does not execute transformation
commands against an external source.

## Risks and boundaries

The external Angular workspace is not present, so source-specific scripts and
package availability cannot be claimed as runtime-proven. Full-suite/frontend
collection or dependency failures remain explicitly reported rather than
masked. No commits are made without separate user authorization.
