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