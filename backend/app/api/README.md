# API

Owns FastAPI routers, request validation, response shaping, dependency wiring,
and error-envelope adaptation.

Routers must delegate workflow, persistence, execution, artifact, approval, and
assistant behavior to application services. They must not implement state-machine
logic, call repositories directly, execute commands, or infer workflow progress.

## S1-F06 authoritative runs

The versioned `/api/v1/runs` routes expose the real run lifecycle:

- `POST /api/v1/runs` creates exactly one run from an approved, current G01
  preflight and returns its setup artifacts and graph thread ID.
- `POST /api/v1/runs/{runId}/start` performs the guarded source-intake handoff.
- `GET /api/v1/runs/{runId}/state` returns the durable authoritative snapshot.
- `GET /api/v1/runs/{runId}/events` replays ordered events for SSE clients and
  honors `Last-Event-ID`.

The router only maps DTOs and stable domain errors. Run creation, leases,
artifact evidence, transitions, and graph handoff belong to
`MigrationRunService`; an unconfigured graph fails closed rather than falling
back to a mock.

## S2-F04 Analysis and G04 evidence

The versioned Analysis routes expose only registered artifact IDs and checksums:

- `POST /api/v1/runs/{runId}/analysis` persists the sanitized input manifest,
  validated structured response, human-readable analysis, usage/cost record,
  G04 package, invocation provenance, and a pending checksum-bound G04 gate.
- `GET /api/v1/runs/{runId}/analysis` returns the authoritative analysis and
  gate snapshot.
- `POST /api/v1/runs/{runId}/approvals/G04/decisions` appends a decision bound
  to the active state version, gate version, artifact-set checksum, plan
  version, and workspace fingerprint.

Analysis and G04 state changes use the Transition Service and emit durable
`ANALYSIS_AGENT_*` and `G04_*` events. Raw model input, repository content,
provider errors, and unsafe filesystem paths are not exposed by these routes.

## S2-F06 MigrationPlan and StageExecutionPlan evidence

The versioned planning routes expose immutable, checksum-bound plan evidence:

- `POST /api/v1/runs/{runId}/plans` generates the family route and exact first
  StageExecutionPlan from validated inputs, with the observed state version,
  idempotency key, actor, and correlation metadata.
- `GET /api/v1/runs/{runId}/plan` and
  `GET /api/v1/runs/{runId}/stages/{stageId}/plan` return the registered plan,
  stage contract, artifact IDs/checksums, and ordered event metadata.

The service persists artifacts before the state transitions and emits
`MIGRATION_PLAN_CREATED` followed by `STAGE_PLAN_CREATED`. Reads re-check
artifact registration and content checksums; authorization, stale versions,
unsupported builders, malformed structured commands, and provider failures
fail closed with stable error codes and correlation IDs. No route executes a
command, approves a plan, or accepts arbitrary artifact paths.

## S2-F07 plan review and G06 evidence

The versioned planning-review routes persist immutable revisions and the
checksum-bound Planning review chain:

- `POST /api/v1/runs/{runId}/plan/revisions` creates a new plan and stage-plan
  version, records the deterministic diff, updates the active pointer, and
  marks dependent approvals stale.
- `POST /api/v1/runs/{runId}/plan/explanation` persists the Planning proposer,
  reviewer, explanation, usage/cost, and pending G06 evidence package.
- `POST /api/v1/runs/{runId}/approvals/G06/decisions` appends an approval,
  rejection, or modification request bound to the current package, plan,
  stage-plan, state version, and workspace fingerprint.
- `GET /api/v1/runs/{runId}/plan/review` returns the latest persisted review
  projection and registered artifact links.

Artifacts are finalized and checksum-registered before completion events are
committed. The routes accept artifact IDs and checksums, never arbitrary paths;
revisions are idempotent and stale or tampered bindings fail closed.
