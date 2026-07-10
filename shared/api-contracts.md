# Shared API Contracts

The backend's Pydantic v2 source of truth is
`backend/app/domain/contracts.py`. The Control Tower, orchestrator, agents, and
future generated TypeScript client must use the vocabulary exposed by the
FastAPI OpenAPI document rather than creating local status values.

## Contract families

- `MigrationRunDto` is the backend-owned aggregate read model.
- `MigrationStageDto`, `AgentExecutionDto`, `ValidationGateDto`, and
  `ApprovalEventDto` represent workflow visibility and human decision points.
- `ArtifactRefDto`, `CommandRequestDto`, `CommandResultDto`,
  `PatchLedgerEntryDto`, `RepairAttemptDto`, and `WorkflowEventDto` represent
  auditable evidence and proposed/executed work.
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

`RunStatus`, `StageStatus`, `AgentStatus`, `ValidationStatus`,
`ApprovalDecision`, `RiskLevel`, `ArtifactType`, and `CommandStatus` are string
enums. Run states use the architecture's uppercase names, including
`WAITING_ANALYSIS_APPROVAL`, `WAITING_PLAN_APPROVAL`, `STAGE_RUNNING`,
`REPAIR_RUNNING`, `WAITING_REPAIR_APPROVAL`, `DIAGNOSTIC_HOLD`, `CANCELLED`,
`COMPLETED_WITH_MANUAL_ITEMS`, and `COMPLETED_WITH_ACCEPTED_RISK`.

Validation state values intentionally use the lower-case policy vocabulary:
`passed`, `failed`, `not_configured`, `manual_validation_required`,
`deferred_company_tool_required`, `blocked_by_environment`, `accepted_risk`,
and `skipped_not_applicable`.

`WorkflowEventType` covers the seven SSE event channels: `run_state_changed`,
`stage_state_changed`, `agent_state_changed`, `validation_gate_changed`,
`artifact_created`, `approval_required`, and `workflow_completed`.

`AllowedAction` enumerates the bounded actions an agent may request:
`read_file`, `run_approved_command`, `request_approval`,
`read_artifact_summary`, and `create_artifact`. Agents never execute
commands directly; they return action requests for the backend to validate.

## OpenAPI

Run the backend and inspect `/openapi.json` or `/docs`. The mock-state response
nests every Sprint 0 DTO, allowing AMF-S0-07 to derive or synchronize frontend
types without contract drift. These contracts describe data only; they do not
authorize commands, mutations, approvals, or workflow transitions.