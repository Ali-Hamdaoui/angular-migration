# Shared API Contracts

The backend's Pydantic v2 source of truth is
`backend/app/domain/contracts.py`. The Control Tower, orchestrator, agents, and
future generated TypeScript client must use the vocabulary exposed by the
FastAPI OpenAPI document rather than creating local status values.

## Contract families

- `MigrationRunDto` is the backend-owned aggregate read model. It separates
  `status` from `run_phase` and stores source/target version families apart
  from detected or resolved exact versions.
- `MigrationStageDto` and `StageStepDto` expose stage and deterministic-step
  status separately from run status.
- `AgentExecutionDto`, `ValidationGateDto`, and `ApprovalEventDto` represent
  agent visibility, validation evidence, and human decision points.
- `ArtifactRefDto`, `CommandRequestDto`, `CommandResultDto`, `WorkerLeaseDto`,
  `PatchLedgerEntryDto`, `RepairAttemptDto`, `DeliveryManifestDto`, and
  `LlmUsageRecordDto` represent auditable evidence and proposed/executed work.
- `MigrationEventDto` carries a typed `WorkflowEventType` and is the SSE payload
  for the `GET /migrations/{runId}/events` stream.
- `AgentInputEnvelope` and `AgentOutputEnvelope` define the common agent
  contract. Every mock or real agent receives the input envelope and returns
  the output envelope; the orchestrator records each call as an
  `AgentExecutionDto` and emits corresponding SSE events.

All DTOs require stable identifiers and timestamps where the record is created,
requested, checked, started, finished, or observed. Contracts reject unknown
fields and invalid enum values.

## Status vocabulary

`RunStatus` is intentionally small and run-level only:

```text
CREATED, RUNNING, WAITING, CANCELLING, CANCELLED, COMPLETED, FAILED,
DIAGNOSTIC_HOLD
```

`RunPhase` captures macro workflow position:

```text
PREFLIGHT_SNAPSHOT, DISCOVERY_BASELINE, FEASIBILITY_PLANNING,
STAGED_MIGRATION, FINAL_ASSURANCE, DELIVERY_REPORTING
```

`StageStatus` and `StepStatus` are separate. Stage statuses are:

```text
PENDING, RUNNING, WAITING_APPROVAL, REPAIRING, PASSED, FAILED, ROLLED_BACK,
CANCELLED, DIAGNOSTIC_HOLD
```

Step statuses are:

```text
PENDING, QUEUED, RUNNING, PASSED, FAILED, BLOCKED, WAITING_APPROVAL, SKIPPED,
MANUAL, DEFERRED, ACCEPTED_RISK, CANCELLED
```

Overlapping global states such as `BUILD_RUNNING`, `VALIDATION_RUNNING`, and
`WAITING_PLAN_APPROVAL` are not part of the canonical run-status vocabulary.
Use run status plus phase, stage status, step status, gates, and events instead.

Validation state values intentionally use the lower-case policy vocabulary:
`passed`, `failed`, `not_configured`, `manual_validation_required`,
`deferred_company_tool_required`, `blocked_by_environment`, `accepted_risk`,
and `skipped_not_applicable`.

`StructuredCommandRequest` is represented by `CommandRequestDto`: it contains an
executable and argument list, uses `shell=false`, and does not accept raw shell
command strings.

## OpenAPI

Run the backend and inspect `/openapi.json` or `/docs`. The mock-state response
nests every Sprint 0 DTO, allowing AMF-S0-07 to derive or synchronize frontend
types without contract drift. These contracts describe data only; they do not
authorize commands, mutations, approvals, or workflow transitions.
## Authoritative Sprint 1 dimensions

Sprint 1 extends the read model with independent `phase_status`, `approval_status`, and `repair_status` fields. The run state vocabulary includes the source-intake, baseline, analysis, planning, stage-execution, recovery, delivery, and cleanup states defined in `docs/mvp_overview.md` section 15. Legacy Sprint 0 coarse values remain readable only for migration compatibility.

Stage outcomes include `preparing`, `passed_with_known_baseline_failures`, and `passed_with_manual_items`. Approval and repair statuses are separate from run and stage status.

Production auto-approval is disabled. Requests that attempt to enable it return `AUTO_APPROVAL_NOT_ALLOWED`; automatic approval remains available only to isolated mock fixtures used by tests.
## S1-F12 baseline validation matrix

The backend exposes the baseline target inventory and validation operations under `/api/v1/runs/{runId}`:

- `GET /baseline/targets`
- `GET /baseline/{kind}` where kind is `build`, `test`, or `lint`
- `POST /baseline/builds`, `/baseline/tests`, or `/baseline/lint`
- `POST /baseline/{kind}/cancel`

Mutation requests carry `expected_state_version`, `idempotency_key`, `actor`, and optional prerequisite artifact IDs. Results include target inventory, normalized status, exit code, duration, parser summaries, failed tests, warnings, output locations, artifact IDs and SHA-256 checksums, baseline checksum, state version, and event sequence. Missing lint is represented as `skipped_not_configured`; unsupported builders are `blocked`.
## S1-F13 baseline parity evidence

The backend captures checksum-bound baseline parity evidence through `POST /api/v1/runs/{runId}/baseline/parity` with `expected_state_version`, `idempotency_key`, `actor`, and optional prerequisite artifact IDs. The resulting immutable evidence is read through:

- `GET /api/v1/runs/{runId}/baseline/failures`
- `GET /api/v1/runs/{runId}/baseline/routes`
- `GET /api/v1/runs/{runId}/baseline/backend-integration`
- `GET /api/v1/runs/{runId}/baseline/anchors`

Responses include parser/schema versions, confidence labels, source and evidence artifact references, SHA-256 checksums, state version, and event sequence. Capture emits `BASELINE_FAILURES_FINGERPRINTED`, `BASELINE_ROUTE_ANCHOR_CREATED`, and `BASELINE_BACKEND_ANCHOR_CREATED` through the authoritative Transition Service.

Feature 13 capture requests may include prerequisite_artifact_checksums, an artifact-ID-to-SHA-256 map. When prerequisite IDs are supplied, every ID must have an expected checksum and the registered checksum must match before capture proceeds.


## S2-F03 governed LLM gateway

The governed LLM surface is exposed under `/api/v1/llm` and `/api/v1/runs/{run_id}/llm`:

- `GET /llm/readiness` reports Azure configuration and the registered strict structured-output capability.
- `POST /llm/smoke` accepts only `run_id`, `expected_state_version`, `idempotency_key`, and optional correlation metadata. Actor identity is derived from authentication (`X-Authenticated-Actor` in the local control-plane adapter), never from JSON.
- `GET /runs/{run_id}/llm/activity` and `GET /runs/{run_id}/usage` return durable invocation and pricing evidence.

Invocation responses expose prompt, schema, model capability/deployment, pricing, stage, input hashes, redacted failure summary, correlation ID, authorized artifact links, state version, and event sequence. Provider failures retain the correlation ID and a redacted failure artifact.

## S2-F04 Analysis Reviewer chain and G04

The Analysis phase is exposed through `/api/v1/runs/{run_id}`:

- `POST /analysis` accepts registered deterministic artifact IDs/checksums,
  observed state version, and an idempotency key.
- `GET /analysis` returns the authoritative package and G04 state.
- `POST /approvals/G04/decisions` requires the current state/gate version,
  final immutable G04 package checksum, workspace fingerprint, plan version,
  decision, and idempotency key.

Generation is checksum-bound: deterministic input → phase Proposer → immutable
Proposer checksum → phase Reviewer → immutable Reviewer checksum → final reviewed
analysis artifact → G04. The Reviewer returns only an accept, revision request,
rejection, or insufficient-context decision and cannot replace the Proposer
narrative. At most one governed Proposer revision is attempted. If review fails
or is not accepted, the API fails closed and does not create G04.

Responses include both roles' provenance, prompt/schema versions, usage/cost,
revision count, registered artifact links, final package checksum, state version,
and event sequence. Durable `ANALYSIS_AGENT_*`, `ANALYSIS_REVIEWER_*`, and
`G04_*` events are replayed through the run SSE stream. A downstream protected
transition must call the G04 guard and is rejected unless the latest approved
gate still matches its package, workspace, plan, and state bindings.

## S2-F05 Feasibility and G05

The deterministic compatibility evidence surface is exposed under
`/api/v1/runs/{run_id}`:

- `POST /feasibility` accepts the observed state version, idempotency key,
  source Angular version, catalogue and registry snapshot IDs/checksums,
  registered prerequisite artifact IDs/checksums, and observed runtime
  candidates.
- `GET /feasibility` returns the persisted route, support classification,
  exact Stage 1 profile, warnings/blockers, immutable artifact IDs/checksums,
  and current G05 state.
- `POST /approvals/G05/decisions` requires the current state/gate version,
  finalized package checksum, artifact-set checksum, workspace/plan bindings,
  decision, and idempotency key.

The backend finalizes catalogue snapshot, route, support-level, registry
snapshot, Stage 1 profile, and feasibility-package artifacts before recording
`COMPATIBILITY_RESOLUTION_COMPLETED` or `COMPATIBILITY_RESOLUTION_BLOCKED`.
Resolution and G05 transitions are persisted through the Transition Service and
replayed as `COMPATIBILITY_RESOLUTION_*` and `G05_*` events. G05 decisions are
append-only; stale bindings, tampered evidence, unauthorized actors, and
idempotency payload reuse fail with stable error codes.
