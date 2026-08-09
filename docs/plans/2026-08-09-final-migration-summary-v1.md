# Final Migration Summary V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` while implementing and `superpowers:verification-before-completion` before claiming completion. Implement task-by-task; do not use this plan to reimplement Feature 1 Usage or Feature 2 Timing.

**Goal:** Add one compact, backend-authoritative completion view that explains a genuinely completed Angular migration and its final evidence.

**Architecture:** A read-only `FinalMigrationSummaryService` validates persisted workflow completion, projects the small set of workflow facts needed by the UI, and composes the shared Usage and Timing aggregations. A typed FastAPI endpoint exposes the DTO. The existing authoritative run Overview conditionally loads and renders one reusable React component when the completion event or completed run status is present.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, Next.js/React, TypeScript, Vitest, pytest.

## Global constraints

- V1 only: no PDF, run comparison, analytics dashboard, charts, new design system, or summary persistence table.
- Reads must not mutate workflow, artifact, command, repair, approval, or delivery state.
- `migration_runs.status` and its guarded `STAGED_MIGRATION_COMPLETED` transition remain the completion authority.
- Token fields must come from Feature 1's shared run-usage aggregation; this feature must not sum usage rows.
- Timing fields must come from Feature 2's shared run-timing aggregation; this feature must not calculate elapsed time.
- Existing detailed transformation, evidence, LLM diagnostics, and event views remain available.
- A path is labeled as delivered only when publication is authoritatively persisted; a configured future path is not a delivered path.
- No database migration is planned.

---

## 1. Executive verdict

Build this as a small completion-only read model and a card at the top of the existing Overview. Approximately **80% of the required facts already exist as persisted runtime evidence**. What is missing is a compact aggregation boundary, a typed completion endpoint, a lifecycle-aware approval/repair count, clean composition with the parallel Usage and Timing authorities, and the final UI.

A dedicated endpoint is the safest small V1. Adding `summary` to `GET /api/v1/runs/{run_id}/state` would run extra cross-table Usage/Timing/repair/approval aggregation during the dashboard's five-second state polling even for non-final runs. `GET /api/v1/runs/{run_id}/summary` keeps the live projection lean, returns only for completed runs, and can be fetched once when completion is observed.

The repository does **not** currently publish real Transformer output through `DeliveryService`. A real run stores the intended `migrated_app_path`, while the actual final output is the last immutable sealed-stage workspace. V1 must show that sealed workspace as the actual output location and expose the configured delivery path as `planned_delivery_path`; `delivery_path` remains `null` until a real publication authority exists.

Do not report a general `recovered_commands` value. Explicit command retry lineage exists through `command_executions.parent_execution_id`, but repair revalidation and replacement commands are not universally linked back to every historical failed execution. V1 should report `historical_failed` commands and lifecycle-proven `successful` repairs instead.

## 2. V1 objective

For a completed authoritative run, show in one view:

- exact source and final Angular versions;
- `COMPLETED` from workflow authority;
- sealed route stages versus approved route stages;
- final install, build, and tests states;
- repair attempts, applied repairs, and successful repairs;
- accepted human approval count;
- persisted command totals and historical failures;
- total duration and completion timestamps from the Timing authority;
- token totals, LLM calls, and retry calls from the Usage authority;
- actual final sealed workspace, planned delivery location, fingerprint, and seal checksum;
- links back to the detailed pipeline and evidence views.

## 3. Non-goals

- No PDF or downloadable report generation.
- No cross-run comparison or trend analysis.
- No cost dashboard or charts.
- No event-text parsing for facts that have relational authorities.
- No new run state, completion event, delivery lifecycle, or workflow transition.
- No real delivery publication implementation.
- No token or timing calculation in the summary service, router, or frontend.
- No broad claim that every failed command was recovered.
- No replacement of `TransformationPanel`, LLM diagnostics, artifacts, or workflow events.
- No persistence/cache table for the summary.

## 4. Current final-state architecture

The real Transformer path is:

```text
approved MigrationPlan.route
        -> materialized MigrationStage rows
        -> required stage gates and final validation
        -> immutable StageCheckpoint(sealed=true) per route stage
        -> TransformerSealingFlow.complete
        -> StateTransitionService(STAGED_MIGRATION_COMPLETED, RunStatus.COMPLETED)
        -> TransformationContinuation(status=completed, completed_at=...)
```

`TransformerSealingFlow.complete()` is the decisive runtime boundary. Before applying `RunStatus.COMPLETED`, it verifies that every ID in the approved plan route has a `migration_stages.status == "sealed"`, every stage has required approved gates, and no active command, prompt, or repair remains. It then persists `STAGED_MIGRATION_COMPLETED` and completes the durable continuation in the same service flow.

The existing `WorkflowProjectionService` is an Assistant-oriented semantic projection. It is useful evidence that the repository already has a projection pattern, but it is not a safe Final Summary dependency: it omits final validation, all repair/approval/output semantics and currently performs its own token and duration calculations. Reusing those operational-statistic calculations would violate the parallel-session contract. V1 therefore follows the same service-projection convention while using a dedicated compact read model.

The existing transformation route builds a rich current-stage projection, including `route_stages`, `validation_results`, and `sealed_chain_hash`, but that projection is assembled inside `api/routes/transformation.py`, is scoped to the current stage, and contains substantially more data than the summary. Extracting that entire route projection would be a larger refactor than this V1.

## 5. Files inspected

### Repository guidance

- `README.md`
- `backend/README.md`
- `frontend/README.md`
- `backend/app/{api,domain,repositories,services,orchestration,delivery,command_execution,llm_gateway}/README.md`
- `docs/README.md`

### Runtime models and services

- `backend/app/repositories/models/workflow.py`
- `backend/app/repositories/planning_models.py`
- `backend/app/repositories/preflight_models.py`
- `backend/app/repositories/g02_models.py`
- `backend/app/repositories/baseline_g03_models.py`
- `backend/app/repositories/analysis_models.py`
- `backend/app/repositories/compatibility_models.py`
- `backend/app/repositories/planning_review_models.py`
- `backend/app/services/workflow_projection_service.py`
- `backend/app/services/migration_run_service.py`
- `backend/app/services/stage_sealing_service.py`
- `backend/app/services/repair_lifecycle_service.py`
- `backend/app/services/repair_application_service.py`
- `backend/app/services/stage_gate_service.py`
- `backend/app/services/validation_runner.py`
- `backend/app/services/command_executor_service.py`
- `backend/app/services/transformation_continuation_service.py`
- `backend/app/services/llm_evidence_application_service.py`
- `backend/app/delivery/services.py`

### Orchestration, contracts, and routes

- `backend/app/orchestration/transformer_graph.py`
- `backend/app/orchestration/transformer_sealing_flow.py`
- `backend/app/domain/contracts.py`
- `backend/app/domain/planning.py`
- `backend/app/domain/transformation.py`
- `backend/app/api/routes/runs.py`
- `backend/app/api/routes/transformation.py`
- `backend/app/api/routes/compatibility.py`
- `backend/app/api/routes/assistant.py`
- `backend/app/api/routes/llm.py`
- `backend/app/api/router.py`

### Frontend

- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/TransformationPanel.tsx`
- `frontend/src/components/TransformationSections.tsx`
- `frontend/src/components/ReportPanel.tsx`
- `frontend/src/components/LlmUsagePanel.tsx`
- `frontend/src/components/control-tower/*`
- `frontend/src/api/runs.ts`
- `frontend/src/api/transformation.ts`
- `frontend/src/api/llm.ts`
- `frontend/src/types/generated/api.ts`
- `frontend/src/types/transformation.ts`
- `frontend/src/hooks/useAuthoritativeRun.ts`
- `frontend/src/app/migrations/[runId]/page.tsx`

## 6. Existing UI/API functionality we can reuse

- `GET /api/v1/runs/{run_id}/state` already exposes run status, persisted paths, timestamps, events, and artifacts.
- `GET /api/v1/runs/{run_id}/transformation` already proves the UI conventions for route stages, final validation labels, repair details, and seal evidence.
- `GET /api/v1/runs/{run_id}/usage` already proves a governed run-scoped Usage endpoint, although Feature 1 must become the reusable authority for the summary.
- `AuthoritativeRunDashboard` defaults to `overview`, already has a completion-friendly top summary region, and owns navigation callbacks for Pipeline and Files & Artifacts.
- `TransformationSections.ValidationEvidence` and `SealAndRoute` remain the detailed evidence destinations; do not duplicate their full data.
- `ControlTowerShell.module.css` already provides `panel`, `metricList`, `metadataGrid`, `note`, and action-link styles sufficient for V1.
- The legacy `ReportPanel` and `LlmUsagePanel` are for the mock `MigrationRunDto` shell and are not the correct authoritative-run placement.
- The FastAPI router already includes `runs_router` beneath `/api/v1`, so no router registration file needs to change.

## 7. Summary field authority matrix

| Desired field | Authoritative source | Current model/table/artifact | Current backend service | Current API exposure | Current frontend exposure | New aggregation? |
|---|---|---|---|---|---|---|
| 1. Run status | Guarded workflow state | `migration_runs.status`; `STAGED_MIGRATION_COMPLETED` event | `StateTransitionService`; `TransformerSealingFlow.complete` | Run state and events | Header/Overview | No; validate exact `COMPLETED` |
| 2. Source Angular version | First approved route stage exact input | First route `migration_stages.source_version_detected`; fallback consistency check with run source exact | Planning/materialization services | Run source exact; transformation stage families | Execution profile/current transformation | Yes, select first approved route stage |
| 3. Target Angular version | Last approved route stage exact resolved target | Last route `migration_stages.target_version_resolved` | Next-stage materializer/sealing flow | Transformation current stage; not run state | Transformation stage summary | Yes, select last approved route stage |
| 4. Route/stage count | Active approved plan route | `active_plan_versions(scope="migration")` -> `migration_plans.plan.route` | Planning evidence/review services | Plan endpoint and transformation route list | Migration plan and transformation | Yes, compact count |
| 5. Sealed stages | Immutable seal records restricted to approved route | `stage_checkpoints.sealed=true`, plus route membership | `StageSealingService` / sealing flow | Transformation route status and latest seal only | Transformation route | Yes, count route IDs with seals |
| 6. Final install status | Final-stage approved validation policy and current step/execution evidence | Last stage plan; `stage_steps final_install-*`; `command_executions` | `ValidationRunner` | Transformation `validation_results.npm_ci` for current stage | Validation Evidence | Add reusable read-only validation summary |
| 7. Final build status | Same | Last stage plan; `stage_steps builds-*`; command evidence | `ValidationRunner` | Transformation current-stage projection | Validation Evidence | Same |
| 8. Final tests status | Same; `not_required` only if policy omits test | Last stage plan; `stage_steps tests-*`; command evidence | `ValidationRunner` | Transformation current-stage projection | Validation Evidence | Same |
| 9. Repair attempts | Governed repair attempt ledger | All run-scoped `repair_attempts` | `RepairApplicationService` / `RepairLifecycleService` | Latest attempt only in transformation API | Latest repair details | Yes, lifecycle aggregate |
| 10. Successful repairs | Terminal lifecycle plus complete bound evidence | `repair_attempts.status=validation_passed` with proposal/review/apply/validation/fingerprint/G10 evidence | `RepairLifecycleService` | Not aggregated | Not aggregated | Yes; reuse lifecycle proof |
| 11. Human approvals | Persisted accepted decision rows, not event text | G01 `user_decisions`; G02-G05 approval-decision rows; `g06_decisions`; `stage_gate_decisions.accepted` | Individual gate services | Per-gate APIs/projections | Per-gate panels | Yes, cross-gate decision count |
| 12. Total commands | Run-scoped execution ledger | `command_executions` | `CommandExecutorService` | Command list endpoint; Assistant stats | Command panels / Assistant | Yes, compact status counts |
| 13. Failed commands | Historical terminal failure statuses | `command_executions.status` in `failed`, `timed_out`, `interrupted` | `CommandExecutorService` | Command list; Assistant stats | Detailed command list | Yes, preserve history |
| 14. Recovered commands | Only explicit retry lineages are provable | `parent_execution_id` and successor status; incomplete for general repair recovery | Retry execution path | Not aggregated | Not exposed | **Do not claim in V1** |
| 15. Total duration | Feature 2 Timing authority | Its persisted-event/timestamp inputs and `RunTimingDto` | `RunTimingService.build()` (Feature 2) | Planned run timing endpoint | Not in final view | Compose only; never recalculate |
| 16. LLM tokens | Feature 1 Usage authority | Governed invocation/usage records behind `LlmUsageTotals`/the shared aggregate | Feature 1 session-scoped helper in `llm_evidence_application_service.py` | Extended existing usage endpoint | LLM diagnostics only | Compose only; never recalculate |
| 17. LLM calls | Feature 1 Usage authority | Invocation count behind shared DTO | Same | Existing `invocation_count` | LLM diagnostics | Compose only |
| 18. Final workspace path | Last approved route stage immutable seal | Final `stage_checkpoints.workspace_path` where `sealed=true` | `StageSealingService` | Not directly in run state | Not in compact view | Yes, select final route seal |
| 19. Migrated/delivery path | Actual publication manifest when one exists; otherwise configured future path | No real persisted delivery manifest for Transformer; `migration_runs.migrated_app_path` is planned path | `DeliveryService` is not wired into real completion | Run state exposes planned path | Run context target only | Expose `planned_delivery_path`; actual `delivery_path=null` |
| 20. Completion timestamp | Feature 2 `finished_at`, aligned with completion event | `STAGED_MIGRATION_COMPLETED.occurred_at`; continuation `completed_at` | Timing authority / sealing flow | Events only | Workflow events | Compose from Timing |
| 21. Output fingerprint/checksum | Final immutable seal | Final sealed checkpoint `workspace_fingerprint` and `manifest_checksum` | `StageSealingService` | Latest seal checksum in transformation API | Seal & Route | Yes, select final route seal |

## 8. Completion authority

Choose **A: the endpoint is available only for completed runs**.

`FinalMigrationSummaryService.get_completed_summary(run_id)` must first load `MigrationRunModel`. It returns:

- `404 RUN_NOT_FOUND` when the run does not exist;
- `409 FINAL_SUMMARY_NOT_READY` unless `run.status == RunStatus.COMPLETED.value`;
- `409 FINAL_SUMMARY_EVIDENCE_INCOMPLETE` if the run claims completion but the active approved route, its stages, their immutable seals, final validation, or final Timing/Usage aggregates are inconsistent.

Do not add `is_final=false` lifecycle behavior. The normal run state and transformation projection already cover in-progress runs. The summary endpoint is a final read model; `completed: true` is retained as explicit client copy but is never independently inferred.

Completion proof is the conjunction of:

1. persisted `migration_runs.status == "COMPLETED"`;
2. an active migration plan and non-empty approved `route`;
3. every route stage has a sealed checkpoint;
4. the existing completion transition/event is present;
5. Feature 2 returns a non-null `finished_at` for the completed run.

The service does not re-run the completion algorithm. Checks 2-5 are fail-closed consistency checks protecting a demo/reporting read from corrupt or partial historical state.

## 9. Validation authority

Add a read-only method beside the execution logic that already owns validation semantics:

```python
ValidationRunner.summarize_final_validation(
    session,
    *,
    stage_id: str,
    stage_plan: StageExecutionPlanModel,
) -> FinalValidationSummary
```

Exact rules:

- `install`: required unconditionally from `final_install-*` references.
- `build`: required only when `build` is in `stage_plan.stage_plan.validation_policy.required_checks`; otherwise `not_required`.
- `tests`: required only when `test` is in the policy; otherwise `not_required`.
- A required group is `passed` only when every command reference has a matching `StageStepModel` in `PASSED`, a bound `CommandExecutionModel` in `succeeded` with exit code `0`, and finalized command-log/result artifact IDs—the same evidence requirements enforced by `advance_group()` and `aggregate()`.
- A required group is `failed` when any current step/execution is terminal non-success.
- Missing/in-flight evidence on a run marked completed is not converted to `failed`; it raises `FINAL_SUMMARY_EVIDENCE_INCOMPLETE` because completion and validation evidence disagree.

The summary reads only the final route stage. Earlier stage validation stays in the detailed Transformation view.

## 10. Repair-count semantics

Add `RepairLifecycleService.summarize_run(session, run_id) -> RepairLifecycleCounts` with:

```python
@dataclass(frozen=True)
class RepairLifecycleCounts:
    attempts_total: int
    applied: int
    successful: int
```

Exact semantics:

- `attempts_total`: all run-scoped `RepairAttemptModel` rows. This represents governed attempts, including rejected, superseded, or failed attempts.
- `applied`: rows with both `apply_ledger_checksum` and `post_fingerprint`. Do not infer application solely from a transient status string.
- `successful`: rows whose current lifecycle status is `validation_passed` and whose complete replacement evidence passes the existing lifecycle proof (proposal, review, approved non-stale G10, apply ledger, post-fingerprint, validation summary, and completion time).
- `superseded`, `evidence_frozen`, `proposed`, `review_accepted`, `waiting_g10`, `approved_pending_execution`, `apply_failed`, `validation_failed`, and similar non-terminal-success rows do not count as successful.

Use the existing `_has_complete_replacement_evidence` logic as the single proof source; make it public or call it from the new aggregate instead of copying it into the summary service.

The headline UI renders `Repairs: {successful} successful / {attempts_total} attempts`. `applied` remains in the DTO and can appear in accessible detail text without becoming another large dashboard metric.

## 11. Human-approval semantics

Count accepted persisted human decisions, never event names. The V1 formula is the sum of:

1. G01 `UserDecisionModel` rows for `run.preflight_id` with decision `approved` or `approved_with_comment`.
2. G02 `G02ApprovalModel` decision rows for the run with decision/status accepted (`approved` or `approved_with_comment`), excluding pending and stale package-only rows.
3. G03 `G03ApprovalModel` decision rows with decision `approved`.
4. G04 `G04ApprovalModel` decision rows whose status is `approved` and decision is present.
5. G05 `G05ApprovalModel` decision rows whose status is `approved` and decision is `approve` or `approve_with_comment`.
6. G06 append-only `G06DecisionModel` rows with decision `approve` or `approve_with_comment` and approved status.
7. G07-G12 `StageGateDecisionModel` rows for the run with `accepted is true`.

Count rows, not distinct gate IDs: the metric means accepted human decisions that occurred. Idempotency constraints prevent replay duplication. A later stale/superseded approval remains a historical human action and is counted if the authoritative decision row itself remains accepted. Do not count package creation, command authorization audits, prompt choices, automatic orchestration actions, or event-text matches.

If a future auto-approval path writes the same decision tables, it must persist an explicit decision origin before this metric can continue to be labeled “human.” The current production plan policy is `mandatory-human-v1`, and stage decisions are accepted through authenticated decision APIs.

## 12. Command-count semantics

Use all run-scoped `CommandExecutionModel` rows; preserve historical executions and retries as separate rows.

```text
total             = count(all command_executions for run)
succeeded         = count(status == "succeeded")
historical_failed = count(status in {"failed", "timed_out", "interrupted"})
cancelled         = count(status == "cancelled")
rejected          = count(status == "rejected")
```

A completed run must have no `queued`, `pending`, or `running` executions because the existing completion invariant blocks active command work. If such a row exists, fail the summary as inconsistent instead of silently omitting it.

Do not implement `recovered_commands = failed_commands`. Explicit retry successors have `parent_execution_id`, but not every repair/revalidation command is linked to the command whose failure motivated the repair. A future narrowly named metric could count `recovered_retry_lineages` where a failed lineage root has a terminal successful descendant; that is outside V1. For now the safe pair is `commands.historical_failed` plus `repairs.successful`.

## 13. Usage integration contract

Feature 1 owns and tests the reusable authority in `backend/app/services/llm_evidence_application_service.py`. Its plan keeps `LlmEvidenceApplicationService.usage()` as the endpoint owner and adds a session-scoped aggregation helper. Standardize that helper name during integration as `aggregate_run_llm_usage` (or adapt only the import if Feature 1 lands another name):

```python
aggregate_run_llm_usage(
    session,
    run_id: str,
) -> LlmUsageResponse

class LlmUsageTotals(ContractModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_calls: int

# Feature 1's full aggregate/endpoint DTO also contains:
# LlmUsageResponse.retry_calls: int
```

Feature 1 deliberately defines `LlmUsageTotals` as the reusable four-field subset. Final Summary also needs the expected `retry_calls` field, so it consumes that value from the same `LlmUsageResponse` aggregate result; it does not run another query.

Rules for this feature:

- inject the Feature 1 session-scoped helper into `FinalMigrationSummaryService`;
- copy `input_tokens`, `output_tokens`, `total_tokens`, `llm_calls`, and `retry_calls` from that one aggregate result unchanged;
- never query `LlmInvocationModel`, `UsageCostRecordModel`, or `LlmUsageRecordModel` from the summary service;
- never use `WorkflowProjectionService.operational_statistics` for summary tokens;
- never let the frontend add per-record tokens;
- treat zero calls/tokens as a valid authoritative result, not unavailable data.

## 14. Timing integration contract

Feature 2 owns and tests the reusable authority in `backend/app/services/run_timing_service.py`. Final Summary consumes its declared interface directly:

```python
RunTimingService.build(
    session: Session,
    run_id: str,
    *,
    as_of: datetime | None = None,
) -> RunTimingDto
```

`RunTimingDto` also carries activity, phase, stage, coverage, `llm_seconds`, `command_seconds`, and `human_wait_seconds` data owned by Feature 2. The compact final DTO copies only non-null `total_duration_seconds`, `started_at`, and `finished_at`; it does not duplicate stage/phase detail. `completed_at` is the same `finished_at` value. A completed run with any of those three fields unavailable fails closed as inconsistent. The service must not subtract timestamps, sum command durations, or calculate human wait independently.

## 15. Gaps

- No compact final-summary DTO, service, route, client, or component exists.
- `WorkflowProjectionService` currently has independent token and duration calculations; those are not suitable authorities for this feature and should eventually consume the shared services under the Usage/Timing work, not this plan.
- No existing service aggregates heterogeneous G01-G12 accepted decisions.
- Repair rows need lifecycle-aware aggregation; raw row count is insufficient for success.
- Final validation semantics exist in `ValidationRunner` but have no reusable read-only compact projector.
- Real Transformer completion does not invoke `DeliveryService`; `migrated_app_path` is an intended location, not proof of publication.
- Broad recovered-command semantics are not authoritatively available.
- The authoritative frontend has no Reports destination; only the mock shell has a placeholder `ReportPanel`.

## 16. Proposed V1 architecture

```text
Persisted workflow/completion/route/seal/decision/command facts
        + ValidationRunner final-validation projection
        + RepairLifecycleService run counts
        + Feature 1 aggregate_run_llm_usage helper
        + RunTimingService.build (Feature 2)
                         |
                         v
           FinalMigrationSummaryService
                         |
                         v
 GET /api/v1/runs/{run_id}/summary (typed, read-only)
                         |
                         v
 FinalMigrationSummary in AuthoritativeRunDashboard Overview
```

The API route performs dependency injection and error mapping only. It must not query repositories or calculate metrics. The service executes in one read transaction, calls Feature 1's session-scoped helper with that session, and calls `RunTimingService.build(session, run_id)`.

Do not make `WorkflowProjectionService` a dependency. Its Assistant-specific DTO, excess queries, and current duplicate Usage/Timing logic make composition less safe than the bounded final read model.

## 17. Proposed DTO/API

Create `backend/app/domain/final_summary.py`:

```python
FinalValidationState = Literal["passed", "failed", "not_required"]

class FinalMigrationVersionsDto(ContractModel):
    source_angular: str
    target_angular: str
    stages_completed: int = Field(ge=0)
    stages_total: int = Field(ge=1)

class FinalValidationSummaryDto(ContractModel):
    install: FinalValidationState
    build: FinalValidationState
    tests: FinalValidationState

class FinalRepairSummaryDto(ContractModel):
    attempts: int = Field(ge=0)
    applied: int = Field(ge=0)
    successful: int = Field(ge=0)

class FinalCommandSummaryDto(ContractModel):
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    historical_failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    rejected: int = Field(ge=0)

class FinalTimingSummaryDto(ContractModel):
    total_duration_seconds: float = Field(ge=0)
    started_at: datetime
    finished_at: datetime

class FinalLlmUsageSummaryDto(ContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    retry_calls: int = Field(ge=0)

class FinalOutputSummaryDto(ContractModel):
    workspace_path: str
    delivery_path: str | None
    planned_delivery_path: str | None
    workspace_fingerprint: str
    seal_checksum: str

class FinalMigrationSummaryDto(ContractModel):
    run_id: str
    status: Literal["COMPLETED"]
    completed: Literal[True]
    completed_at: datetime
    migration: FinalMigrationVersionsDto
    validation: FinalValidationSummaryDto
    repairs: FinalRepairSummaryDto
    human_approvals: int = Field(ge=0)
    commands: FinalCommandSummaryDto
    timing: FinalTimingSummaryDto
    llm_usage: FinalLlmUsageSummaryDto
    output: FinalOutputSummaryDto
```

Endpoint:

```http
GET /api/v1/runs/{run_id}/summary
```

Responses:

- `200 FinalMigrationSummaryDto` for a complete, internally consistent run;
- `404 RUN_NOT_FOUND`;
- `409 FINAL_SUMMARY_NOT_READY` for a non-completed run;
- `409 FINAL_SUMMARY_EVIDENCE_INCOMPLETE` for contradictory/missing final evidence.

Use `response_model=FinalMigrationSummaryDto` so FastAPI validates, documents, serializes, and filters the response to the compact schema.

## 18. Proposed frontend placement

Add `FinalMigrationSummary` as the first content in the existing `overview` section of `AuthoritativeRunDashboard` when either:

```ts
state.status === "COMPLETED" || has("STAGED_MIGRATION_COMPLETED")
```

The component calls `getFinalMigrationSummary(runId)` on mount and when the authoritative completion event first appears. Backend completion validation remains decisive; the event only triggers the read.

Reuse existing styles from `ControlTowerShell.module.css`; do not create a new style system or sidebar item. Provide two callbacks:

```ts
onViewPipeline={() => setActiveSection("transformation")}
onViewEvidence={() => setActiveSection("evidence")}
```

The summary should precede, not remove, the existing Overview cards. The Transformation and Files & Artifacts sections remain the detailed evidence views.

## 19. Example JSON

```json
{
  "run_id": "run-20260809-demo",
  "status": "COMPLETED",
  "completed": true,
  "completed_at": "2026-08-09T14:47:32Z",
  "migration": {
    "source_angular": "18.2.3",
    "target_angular": "21.0.4",
    "stages_completed": 3,
    "stages_total": 3
  },
  "validation": {
    "install": "passed",
    "build": "passed",
    "tests": "passed"
  },
  "repairs": {
    "attempts": 6,
    "applied": 4,
    "successful": 3
  },
  "human_approvals": 22,
  "commands": {
    "total": 43,
    "succeeded": 34,
    "historical_failed": 9,
    "cancelled": 0,
    "rejected": 0
  },
  "timing": {
    "total_duration_seconds": 2852.0,
    "started_at": "2026-08-09T14:00:00Z",
    "finished_at": "2026-08-09T14:47:32Z"
  },
  "llm_usage": {
    "input_tokens": 120450,
    "output_tokens": 18420,
    "total_tokens": 138870,
    "llm_calls": 24,
    "retry_calls": 2
  },
  "output": {
    "workspace_path": "C:\\migration-output\\.migration-factory\\runs\\run-20260809-demo\\stage-sandboxes\\stage-21-sealed",
    "delivery_path": null,
    "planned_delivery_path": "C:\\migration-output\\migrated-app",
    "workspace_fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "seal_checksum": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

## 20. Example UI

```text
Angular 18.2.3 -> 21.0.4                         COMPLETED

Duration          47m 32s      LLM Tokens        138,870
LLM Calls              24      Repairs      3 / 6 attempts
Human approvals        22      Commands                43
Stages              3 / 3      Failed historically      9

Final validation
Install              PASS      Build                 PASS
Tests                PASS

Output workspace
C:\migration-output\.migration-factory\runs\...\stage-21-sealed

Planned delivery
C:\migration-output\migrated-app (not yet published)

[View detailed pipeline]  [View evidence]
```

Format duration and numbers in the frontend only for display. The frontend must not derive any metric or final status.

## 21. Acceptance criteria

- **AC1:** A completed run displays source and final Angular exact versions from the first and last stages of the active approved plan route.
- **AC2:** `stages_total` equals the dynamic active plan route length.
- **AC3:** `stages_completed` counts immutable sealed checkpoints for route stages only.
- **AC4:** Install/build/tests states use `ValidationRunner`'s final-stage current evidence and validation policy.
- **AC5:** Repair metrics distinguish attempts, evidence-proven applications, and lifecycle-proven successes.
- **AC6:** Human approvals count accepted persisted decision rows across G01-G12; no event parsing.
- **AC7:** Command totals are run-scoped, include retry rows, and preserve historical failures.
- **AC8:** Total duration and timestamps are copied from the shared Timing authority.
- **AC9:** Token totals, LLM calls, and retry calls are copied from the shared Usage authority.
- **AC10:** No summary/router/frontend code sums tokens or calculates elapsed time.
- **AC11:** The endpoint returns 409 and no summary unless `migration_runs.status` is authoritatively `COMPLETED`.
- **AC12:** Actual workspace/fingerprint/checksum come from the final immutable seal. Configured `migrated_app_path` is labeled planned until publication exists.
- **AC13:** A historical completed run renders from persisted database/evidence records after application restart.
- **AC14:** Repeated summary reads create no rows, files, events, state versions, or artifact changes.
- **AC15:** The final result appears at the top of Overview and preserves existing detailed transformation/evidence views.
- **AC16:** V1 does not expose `recovered_commands`; historical failures and successful repairs are shown separately.
- **AC17:** A completed run with an active command, missing route seal, missing final validation evidence, or missing completion timestamp fails closed as inconsistent.

## 22. Exact implementation tasks

### Task 1: Land and freeze the shared Usage/Timing interfaces

**Files:** Read-only from this feature: Feature 1's `backend/app/api/llm_contracts.py` and `backend/app/services/llm_evidence_application_service.py`; Feature 2's `backend/app/domain/contracts.py` and `backend/app/services/run_timing_service.py`.

**Current behavior:** Usage exists in `LlmEvidenceApplicationService.usage()` and Assistant projections; duration exists in Assistant projections/context. Neither is yet the explicitly shared authority required by the parallel-session contract.

**Change:** Merge Feature 1/2 first. Standardize Feature 1's planned session-scoped helper as `aggregate_run_llm_usage(session, run_id) -> LlmUsageResponse` (or adapt only the Final Summary import if another name lands), and consume Feature 2's declared `RunTimingService.build(session, run_id) -> RunTimingDto`. Confirm the returned field names match Sections 13-14. Final Summary may map fields but may not add fallback calculations.

**Fields consumed:** All five Usage fields; Timing `total_duration_seconds`, `started_at`, `finished_at`.

**Complexity:** S for Final Summary integration; implementation belongs to Features 1/2.

**Dependencies:** Feature 1 Usage V1 and Feature 2 Timing V1.

**Verification:** Contract tests from Features 1/2 pass; grep Final Summary files to prove no direct usage-row sum or timestamp subtraction exists.

### Task 2: Define the compact backend contract

**Files:**

- Create `backend/app/domain/final_summary.py`.
- Modify `backend/app/domain/__init__.py` only if this repository's import convention requires re-export; direct module import is preferred to avoid churn.

**Current behavior:** No final-summary contract exists. `MigrationRunDto`, `AuthoritativeRunStateDto`, Assistant projection, and Transformation projection are too broad.

**Change:** Add the DTOs and literal validation states from Section 17. Keep paths/fingerprints nullable only where runtime truth allows; for a valid completed summary, final workspace/fingerprint/seal are required.

**Fields consumed:** None; this task produces the API boundary types.

**Complexity:** S.

**Dependencies:** Agree on imported shared Usage/Timing DTO names, or map them into the compact nested DTOs.

**Verification:** Add Pydantic contract assertions in `backend/tests/test_final_migration_summary.py` for negative counts, invalid status, and a valid zero-usage completed payload.

### Task 3: Add read-only validation and repair aggregates at their authorities

**Files:**

- Modify `backend/app/services/validation_runner.py`.
- Modify `backend/app/services/repair_lifecycle_service.py`.
- Create `backend/tests/test_final_migration_summary.py`.

**Current behavior:** `ValidationRunner.aggregate()` validates one active stage during execution but does not return a compact read projection. `RepairLifecycleService` reconciles superseded attempts and privately validates complete replacement evidence but does not count run outcomes.

**Change:** Add `ValidationRunner.summarize_final_validation(...)` and `RepairLifecycleService.summarize_run(...)` with the exact semantics in Sections 9-10. Ensure both methods are read-only; `summarize_run` must not call the mutating reconciliation method.

**Fields consumed:** Stage plan validation policy/commands, stage steps, command execution evidence; all run repair attempts and bound G10 packages.

**Complexity:** M because lifecycle edge cases matter.

**Dependencies:** Existing validation runner and repair lifecycle tests/fixtures.

**Verification:** Tests cover multiple commands per validation group, optional tests, missing evidence, rejected/superseded/applied/validation-passed repairs, and a superficially successful status missing bound evidence.

### Task 4: Build `FinalMigrationSummaryService`

**Files:**

- Create `backend/app/services/final_migration_summary_service.py`.
- Modify `backend/tests/test_final_migration_summary.py`.

**Exact interface:**

```python
class FinalMigrationSummaryError(ValueError):
    code: str
    message: str

class FinalMigrationSummaryService:
    def __init__(
        self,
        *,
        scope=session_scope,
        usage_aggregate: Callable[[Session, str], LlmUsageResponse],
        timing_service: RunTimingService,
        validation_runner: ValidationRunner | None = None,
    ) -> None: ...

    def get_completed_summary(self, run_id: str) -> FinalMigrationSummaryDto: ...
```

**Current behavior:** No service composes completion, route, seals, validation, repairs, approvals, commands, output, Usage, and Timing.

**Change:** In one read transaction:

1. validate `MigrationRunModel.status == COMPLETED`;
2. load active migration pointer and plan route;
3. load ordered route stages and their seals;
4. load the active final-stage plan and call the validation authority;
5. call repair lifecycle counts;
6. count accepted G01-G12 decisions with the Section 11 formula;
7. group run command statuses with the Section 12 formula and reject active rows;
8. call Feature 1's Usage helper and `RunTimingService.build()` without recalculation;
9. map final sealed checkpoint output and planned path;
10. return `FinalMigrationSummaryDto`.

**Fields consumed:** All non-Usage/Timing sources in the matrix plus the two shared aggregates.

**Complexity:** M.

**Dependencies:** Tasks 1-3.

**Verification:** Service tests cover completed happy path, not-completed 409 error, missing route/seal/validation, revisions using the active plan, command history, approval rows without event parsing, zero repairs, zero LLM usage, and repeat reads with unchanged row/event/artifact counts.

### Task 5: Expose the typed read-only API

**Files:**

- Modify `backend/app/api/routes/runs.py`.
- Modify `backend/tests/test_final_migration_summary.py`.

**Current behavior:** The runs router exposes create/start/cancel/state/events but no completion summary.

**Change:** Add `get_final_summary_service()` dependency and:

```python
@router.get("/{run_id}/summary", response_model=FinalMigrationSummaryDto)
def read_final_summary(...): ...
```

Map `RUN_NOT_FOUND` to 404 and both final-summary state/evidence errors to 409 using the existing error envelope. Keep repository access out of the router.

**Fields consumed:** `FinalMigrationSummaryDto` returned by the service.

**Complexity:** S.

**Dependencies:** Task 4.

**Verification:** FastAPI client tests assert 200 schema filtering, 404, 409 non-final, stable repeat response, and no write-side effects. Confirm `/api/v1/runs/{id}/summary` appears in OpenAPI with the DTO schema.

### Task 6: Add the typed frontend client contract

**Files:**

- Modify `frontend/src/types/generated/api.ts` (or regenerate it through the repository's established OpenAPI synchronization workflow during implementation).
- Modify `frontend/src/api/runs.ts`.
- Modify `frontend/src/api/__tests__/runs.test.ts`.

**Current behavior:** The client can fetch run state but has no summary type/call.

**Change:** Add TypeScript equivalents of Section 17 and:

```ts
export function getFinalMigrationSummary(
  runId: string,
  client: ApiClient = apiClient,
): Promise<FinalMigrationSummaryDto>
```

Use `encodeURIComponent(runId)` and `/api/v1/runs/${...}/summary`.

**Fields consumed:** Typed endpoint response only.

**Complexity:** S.

**Dependencies:** Task 5/OpenAPI.

**Verification:** API client test checks URL encoding and return typing. Typecheck must reject old `calls`/`failed` aliases; use `llm_calls` and `historical_failed` exactly.

### Task 7: Build and place the compact completion component

**Files:**

- Create `frontend/src/components/FinalMigrationSummary.tsx`.
- Create `frontend/src/components/__tests__/FinalMigrationSummary.test.tsx`.
- Modify `frontend/src/components/AuthoritativeRunDashboard.tsx`.
- Modify `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`.
- Reuse `frontend/src/components/ControlTowerShell.module.css`; modify it only if one minimal responsive class cannot be expressed with existing styles.

**Current behavior:** Overview shows generic live phase/event/artifact counts. Final validation and sealing are only in the detailed Transformation section. The mock `ReportPanel` is not used by authoritative runs.

**Change:** Fetch and render the component at the top of Overview after authoritative completion. Show loading and actionable retry failure states. Format duration as hours/minutes/seconds and numeric values with `Intl.NumberFormat`. Render `delivery_path` only when non-null; otherwise label `planned_delivery_path` as “Planned delivery (not yet published).” Wire detailed-pipeline and evidence callbacks to existing sections.

**Fields consumed:** The summary DTO only; do not calculate counts, status, tokens, or elapsed time from run state/events.

**Complexity:** M.

**Dependencies:** Task 6.

**Verification:** Component tests cover completed rendering, zero repairs/usage, `not_required` tests, planned-versus-published output copy, loading/error/retry, and navigation callbacks. Dashboard test proves the component is absent before completion and appears after `STAGED_MIGRATION_COMPLETED`/`COMPLETED` without removing existing sections.

### Task 8: Full regression and read-only verification

**Files:** No product-file changes expected; fix only defects found within files already listed.

**Current behavior:** No end-to-end summary assurance exists.

**Change:** Run the targeted and standard checks in Section 25. Use a persisted completed fixture, create a fresh application/session, fetch the summary twice, and compare database row counts/state version/event sequence plus artifact-directory metadata before/after.

**Fields consumed:** Full response.

**Complexity:** M.

**Dependencies:** Tasks 1-7.

**Verification:** All acceptance criteria and regression commands pass.

## 23. Files to modify/create

### Create

- `backend/app/domain/final_summary.py`
- `backend/app/services/final_migration_summary_service.py`
- `backend/tests/test_final_migration_summary.py`
- `frontend/src/components/FinalMigrationSummary.tsx`
- `frontend/src/components/__tests__/FinalMigrationSummary.test.tsx`

### Modify

- `backend/app/services/validation_runner.py`
- `backend/app/services/repair_lifecycle_service.py`
- `backend/app/api/routes/runs.py`
- `frontend/src/types/generated/api.ts`
- `frontend/src/api/runs.ts`
- `frontend/src/api/__tests__/runs.test.ts`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`
- `frontend/src/components/ControlTowerShell.module.css` only if existing styles cannot provide the compact responsive layout

### Read only for this feature

- Feature 1 Usage domain/service files and tests
- Feature 2 Timing domain/service files and tests
- `backend/app/services/workflow_projection_service.py`
- `backend/app/services/migration_run_service.py`
- `backend/app/services/stage_gate_service.py`
- `backend/app/services/command_executor_service.py`
- `backend/app/orchestration/transformer_graph.py`
- `backend/app/orchestration/transformer_sealing_flow.py`
- `backend/app/repositories/models/workflow.py`
- `backend/app/repositories/*_models.py`
- `frontend/src/components/TransformationPanel.tsx`
- `frontend/src/components/TransformationSections.tsx`

### Must not change

- Alembic revisions or SQLAlchemy table schemas
- Completion transition rules or event vocabulary
- Command execution/retry behavior
- Repair application or gate-decision behavior
- Workspace sealing or artifact mutation behavior
- Delivery publication behavior
- Existing detailed evidence/LLM/event destinations
- Feature 1/Feature 2 aggregation algorithms from within this feature

## 24. Parallel implementation/integration order

```text
Feature 1 Usage V1 --------\
                            +--> Final Summary Tasks 4-8
Feature 2 Timing V1 -------/

Independent now: Tasks 2-3, most of Task 4 workflow projection tests,
                 Task 7 static component/layout using the agreed DTO fixture.
```

Integration-safe order:

1. Freeze names and semantics of the Usage and Timing aggregate DTOs/methods.
2. In parallel, implement Final Summary contracts; validation/repair read helpers; UI fixture/component.
3. Implement the summary service's workflow/route/seal/approval/command projection with an injected fake Usage helper and fake `RunTimingService` in tests.
4. Merge Feature 1 and Feature 2.
5. Replace test fakes at the composition boundary with the real aggregate services; do not copy their internals.
6. Add endpoint/client/dashboard integration.
7. Run historical-restart and read-only verification.

If Feature 1/2 choose different filenames or class names, change only Final Summary imports/constructor wiring. The five Usage fields and required Timing fields are the stable semantic dependency.

## 25. Verification plan

### Backend targeted checks

```powershell
python -m pytest backend/tests/test_final_migration_summary.py -q
python -m pytest backend/tests/test_full_completion_invariant.py backend/tests/test_transformation_api.py backend/tests/test_assistant_r5_workflow_projection.py -q
```

### Frontend targeted checks

```powershell
npm --prefix frontend test -- --run src/api/__tests__/runs.test.ts src/components/__tests__/FinalMigrationSummary.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx
npm --prefix frontend run typecheck
```

### Contract/OpenAPI checks

- Inspect generated OpenAPI for `/api/v1/runs/{run_id}/summary` and `FinalMigrationSummaryDto`.
- Assert response-model filtering excludes internal decision comments, actor identities, raw artifact content, and provider details.
- Confirm TypeScript fields match OpenAPI exactly.

### Historical/restart check

1. Seed or reuse a persisted completed-run fixture with route, seals, commands, repairs, approvals, usage, and timing evidence.
2. Dispose the service/session/application instance.
3. Create a fresh instance against the same test database/artifact root.
4. Fetch the summary and compare it to the pre-restart response.

### Read-only check

Before and after two GETs, assert unchanged:

- `migration_runs.state_version` and `updated_at`;
- workflow event count and maximum sequence;
- counts in command, repair, approval, artifact metadata, and Usage/Timing source tables;
- artifact file count/checksums.

### Manual demo check

- Open a completed authoritative run; Overview immediately shows the final card.
- Verify exact Angular versions, stages, validation, tokens, duration, repairs, approvals, and commands against detailed views.
- Confirm the actual sealed workspace exists and the configured migrated-app path is labeled planned when unpublished.
- Use “View detailed pipeline” and “View evidence” without losing the summary.

## 26. Risks/regression boundaries

| Risk | Boundary/mitigation |
|---|---|
| `COMPLETED` currently precedes real delivery publication | Do not label `migrated_app_path` as delivered; expose actual sealed workspace and planned delivery separately. |
| Heterogeneous G01-G12 persistence can double-count package rows | Count only explicit accepted decision forms listed in Section 11; test pending/stale/package rows. |
| Repair status names are numerous and may be superseded | Count application by bound apply evidence and success through `RepairLifecycleService`, not status sets in the summary service. |
| Validation steps are reset during repair revalidation | Read current final-stage step bindings using `ValidationRunner`; command totals independently retain historical executions. |
| Usage/Timing plans rename types or methods | Keep semantic contract stable and adapt only imports/wiring after merge. No fallback algorithms. |
| Existing Assistant projection has tempting token/duration values | Explicitly keep it read-only and out of Final Summary composition. |
| A completion event reaches the browser before refreshed run state | The event may trigger the GET, but the endpoint revalidates persisted `COMPLETED`; render loading/retry rather than infer completion client-side. |
| Sensitive/local paths | Paths are already authorized run-state data; keep the endpoint run-scoped, do not expose source contents, raw prompts, or command output. |

## 27. Web references

- [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/) — use `response_model=FinalMigrationSummaryDto` for runtime response validation, OpenAPI schema generation, serialization, and output filtering.
- [Microsoft Foundry Azure OpenAI Responses REST reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/responses) — provider responses expose authoritative `usage` with `input_tokens`, `output_tokens`, and `total_tokens`; Final Summary consumes Feature 1's persisted aggregation of those fields rather than reading provider responses itself.

## 28. Complexity estimate

**Overall: small-to-medium, approximately 3-4 engineering days after the shared Usage/Timing contracts are available.**

- Backend DTO, lifecycle helpers, service, endpoint: 1.5-2 days.
- Frontend client/component/placement: 0.75-1 day.
- Cross-lifecycle tests and historical/read-only verification: 0.75-1 day.
- Database migration: none.
- New dependencies: none.

The main complexity is semantic correctness across heterogeneous approval and repair records, not UI construction.

## 29. Recommended implementation sequence

1. Merge/freeze Feature 1 Usage and Feature 2 Timing aggregation interfaces.
2. Add the compact final-summary domain DTO and its contract tests.
3. Add read-only final validation and repair lifecycle aggregates at existing authorities.
4. Implement `FinalMigrationSummaryService` with injected Usage/Timing services and fail-closed completion checks.
5. Add the typed runs endpoint and OpenAPI/API tests.
6. Synchronize the TypeScript contract and add the runs API client method.
7. Build `FinalMigrationSummary` using existing styles and place it first in Overview.
8. Add dashboard/navigation tests, then run targeted regressions, historical restart, and read-only checks.

This sequence allows independent work on contracts, lifecycle helpers, and UI fixtures while preventing Final Summary from duplicating the two parallel aggregation features.
