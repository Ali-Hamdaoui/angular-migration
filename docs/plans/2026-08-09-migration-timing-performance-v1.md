# Migration Timing / Performance V1 — Implementation Plan

## 1. Executive verdict

Build this feature as a read-only projection over data already persisted by the workflow. No telemetry platform and no database migration are needed.

The repository already persists approximately **90% of the timing evidence required by V1**. This estimate treats the ten requested authority rows in section 7 equally: eight are complete and two are partial. LLM rows have start/end columns, but some planning-review invocations are persisted after the provider call with `started_at == completed_at` and no `latency_ms`. Validation command execution is durable, but the declared `STAGE_VALIDATION_*` events are not emitted by the real Transformer, so V1 can report cumulative validation-command activity but must not invent a full validation wall-clock span.

The simplest trustworthy design is:

```text
persisted workflow events + command/LLM/gate/repair rows + approved route
    -> RunTimingService.build(session, run_id, as_of)
    -> GET /api/v1/runs/{run_id}/timing (typed RunTimingDto)
    -> MigrationTimingPanel in the existing Overview section
```

Ponytail/YAGNI decision: add one aggregation service and one panel; reuse the runs router, existing Pydantic contract module, API client, generated TypeScript contracts, and existing dashboard styles. Do not add a timing repository, cache, background job, timer table, chart library, or observability dependency.

## 2. V1 objective

Expose and clearly display:

- authoritative total migration wall-clock duration;
- current elapsed time for a started, non-terminal run without persisting a fake finish;
- event-derived duration for the major phases that the production lifecycle actually represents;
- dynamic approved-route stage durations for any stage count or Angular version pair;
- cumulative LLM, command, human approval wait, repair, validation-command, and sealing activity;
- start, finish, and server `as_of` timestamps;
- coverage metadata when persisted evidence is incomplete.

All calculations are read-only and restart-safe.

## 3. Non-goals

- OpenTelemetry, Prometheus, distributed tracing, spans, exporters, or collectors.
- Percentiles, historical comparisons, alerts, SLAs, budgets, or performance regression analysis.
- Flame graphs, Gantt charts, timeline editing, or a charting dependency.
- Persisted aggregate counters or periodically updated elapsed-time rows.
- Reworking Transformer states or emitting new lifecycle events solely for this feature.
- Token/cost aggregation, which remains owned by Session 1's Usage feature.
- Timing assistant conversations or LLM smoke checks as migration work.
- Claiming that cumulative activity categories partition total wall-clock time.

## 4. Current timing architecture

The backend is the workflow and timestamp authority. SQLAlchemy rows persist command, LLM, repair, stage, job, and gate lifecycle timestamps. `workflow_events.occurred_at` persists ordered semantic boundaries. The frontend currently renders run state and event history but has no dedicated timing contract or panel.

There is an existing timing-like projection in `WorkflowProjectionService.build()`:

- `recorded_workflow_duration_seconds` uses `run.created_at` and `run.updated_at` for terminal runs, or the latest event for active runs;
- `stage_durations_seconds` uses `MigrationStageModel.started_at/completed_at`;
- `phase_durations_seconds` repeats the same run-wide duration under the current phase.

Those fields are not suitable authorities for this feature. `run.created_at` precedes the accepted start action, `run.updated_at` changes for unrelated state writes, real Transformer stage execution does not populate `MigrationStageModel.started_at`, and one run-wide value is not a phase duration. V1 should make `RunTimingService` the only timing calculator and have `WorkflowProjectionService` consume it for its existing timing fields.

## 5. Files inspected

Repository guidance:

- `README.md`
- `backend/README.md`
- `backend/app/repositories/README.md`
- `backend/app/services/README.md`
- `backend/app/orchestration/README.md`
- `backend/app/domain/README.md`
- `backend/app/api/README.md`
- `backend/app/events/README.md`
- `backend/app/command_execution/README.md`
- `backend/app/llm_gateway/README.md`
- `frontend/README.md`
- `docs/README.md`

Runtime and persistence:

- `backend/app/repositories/models/workflow.py`
- `backend/app/repositories/compatibility_models.py`
- `backend/app/repositories/planning_models.py`
- `backend/app/repositories/analysis_models.py`
- `backend/app/repositories/baseline_g03_models.py`
- `backend/app/repositories/planning_review_models.py`
- `backend/app/domain/contracts.py`
- `backend/app/domain/planning.py`
- `backend/app/llm_gateway/contracts.py`
- `backend/app/state/transition_service.py`
- `backend/app/services/migration_run_service.py`
- `backend/app/services/workflow_projection_service.py`
- `backend/app/services/transformation_continuation_service.py`
- `backend/app/services/stage_execution_application_service.py`
- `backend/app/services/transformer_stage_service.py`
- `backend/app/services/command_executor_service.py`
- `backend/app/services/stage_gate_service.py`
- `backend/app/services/repair_application_service.py`
- `backend/app/services/repair_lifecycle_service.py`
- `backend/app/services/validation_runner.py`
- `backend/app/services/lockfile_generation_runner.py`
- `backend/app/services/planning_job_service.py`
- `backend/app/services/planning_evidence_application_service.py`
- `backend/app/services/planning_review_evidence_application_service.py`
- `backend/app/services/analysis_evidence_application_service.py`
- `backend/app/services/discovery_evidence_application_service.py`
- `backend/app/services/parity_baseline_evidence_application_service.py`
- `backend/app/services/next_stage_materializer_service.py`
- `backend/app/orchestration/source_intake.py`
- `backend/app/orchestration/planning.py`
- `backend/app/orchestration/planning_worker.py`
- `backend/app/orchestration/transformer_graph.py`
- `backend/app/orchestration/transformer_sealing_flow.py`
- `backend/app/orchestration/transformer_worker.py`
- `backend/app/api/routes/runs.py`
- `backend/app/api/routes/transformation.py`

Frontend and focused test conventions:

- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/TransformationPanel.tsx`
- `frontend/src/components/ControlTowerShell.module.css`
- `frontend/src/components/control-tower/ControlTowerSidebar.tsx`
- `frontend/src/components/control-tower/PipelineSection.tsx`
- `frontend/src/components/control-tower/WorkflowEventsSection.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/runs.ts`
- `frontend/src/api/transformation.ts`
- `frontend/src/types/generated/api.ts`
- `frontend/src/types/transformation.ts`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`
- `frontend/src/api/__tests__/runs.test.ts`
- relevant backend timing/lifecycle tests found by repository-wide search, including `test_assistant_amfa221.py`, `test_command_terminal_lifecycle.py`, `test_state_transition_service.py`, and Transformer repair/sealing tests.

## 6. Existing persisted timestamps/events

The following evidence is already durable:

- `workflow_events.occurred_at`, with per-run monotonic `sequence` and semantic event types.
- `RUN_START_ACCEPTED` at the successful start transition.
- terminal `STAGED_MIGRATION_COMPLETED`, `RUN_CANCELLED`, `SOURCE_INTAKE_FAILED`, and `PLANNING_FAILED` transitions where applicable.
- `STAGE_CREATED` after the approved stage workspace has been prepared.
- `STAGE_SEALED` after the sealed checkpoint and output evidence are committed.
- ordered route data in `CompatibilityResolutionModel.route`; run-scoped stage IDs are deterministically produced by the existing `run_scoped_stage_id()` helper.
- `CommandExecutionModel.started_at`, `finished_at`, `duration_ms`, status, retry lineage, stage, command identity, and durable idempotency key.
- `LlmInvocationModel.started_at`, `completed_at`, `latency_ms`, task type, role, status, retry count, and stage.
- global gate lifecycle events `G02_CREATED` through `G06_*`.
- Transformer gate lifecycle events `G07_CREATED` through `G12_*`, plus `StageGatePackageModel.created_at/stale_at` and `StageGateDecisionModel.created_at`.
- `RepairAttemptModel.created_at/completed_at`, status, attempt number, and parent attempt.
- `StageStepModel.started_at/completed_at` for the current step binding.
- validation command identities produced by `validation_execution_key()` with the stable `:validation:` grammar; command rows survive failed attempts and retries.
- `G11_APPROVED` or `G12_APPROVED` immediately before the sealing path, and `STAGE_SEALED` after sealing commits.
- `PlanningJobModel.started_at/completed_at`, although its job span includes approval waits and should not be mislabeled as pure planning execution.

## 7. Authoritative timestamp matrix

| Timing concept | Existing candidates | V1 authority and decision |
|---|---|---|
| Run start | `MigrationRunModel.created_at`; `RUN_CREATED`; `RUN_START_ACCEPTED`; `RUN_STARTED`; source-intake job timestamps | Use the earliest `RUN_START_ACCEPTED.occurred_at`. It is written by `MigrationRunService.start()` only after start validation succeeds. Do not use creation or queue/worker start. |
| Run completion | `run.updated_at`; continuation completion; terminal events | For a completed migration use `STAGED_MIGRATION_COMPLETED.occurred_at`, the transition that sets `RunStatus.COMPLETED`. For other terminal statuses use their semantic terminal event only. Never use `run.updated_at` as a finish fallback. |
| Stage start | stage `created_at`; nullable `started_at`; `STAGE_PLAN_CREATED`; `STAGE_CREATED` | Use `STAGE_CREATED.occurred_at`. `created_at` means planned/materialized and may substantially precede execution; the real Transformer path does not set `started_at`. |
| Stage completion/seal | stage `completed_at`; sealed checkpoint `created_at`; `STAGE_SEALED` | Use `STAGE_SEALED.occurred_at`. It is appended after the sealed checkpoint and stage completion are persisted. The model field may be returned as corroboration, not selected as authority. |
| LLM invocation start/end | `started_at/completed_at`; `latency_ms`; `LLM_INVOCATION_*` events | For workflow-owned invocation rows, prefer non-null `latency_ms`; otherwise use a positive `completed_at - started_at`. Treat zero-width fallback rows and open rows as unmeasured. Exclude `assistant_response` and `smoke_check`. |
| Command execution start/end | `requested_at`; `started_at/finished_at`; `duration_ms`; command events | Use each row's persisted `finished_at - started_at`. Include every row with a valid pair, regardless of success/failure/timeout/cancel/interruption or retry ancestry. `requested_at` is queue time, not runtime. |
| Gate waiting start/end | gate model timestamps; `Gxx_CREATED`; `Gxx_APPROVED/REJECTED/MODIFICATION_REQUESTED/STALE` | Pair ordered workflow gate events by gate ID and stage scope. Start at `Gxx_CREATED`; stop at the first terminal event, or server `as_of` while still pending. Exclude pre-run G01 because total timing starts after it. |
| Repair start/end | attempt `created_at`, `updated_at`, `completed_at`; repair events | Use `RepairAttemptModel.created_at` to `completed_at`. For a currently active attempt use server `as_of`. A terminal row without `completed_at` is unmeasured; do not silently substitute generic `updated_at`. Sum every persisted attempt, including superseded attempts. |
| Validation start/end | declared but un-emitted `STAGE_VALIDATION_*`; step timestamps; validation command rows | V1 reports cumulative validation command runtime by summing valid command intervals whose durable idempotency key contains the stable `:validation:` grammar. Do not expose a validation wall-clock phase until real start/end events are emitted. |
| Sealing start/end | `G11/G12` decisions; sealing artifact times; `STAGE_SEALED` | Per stage, start at the latest accepted `G11_APPROVED` or `G12_APPROVED` preceding `STAGE_SEALED`; end at `STAGE_SEALED`, or server `as_of` if approval is committed and sealing is active. This excludes human gate wait from sealing execution. |

Stale/non-semantic fields that must not be used as authorities:

- `MigrationRunModel.updated_at` for run completion or elapsed duration;
- `MigrationRunModel.created_at` for migration start;
- `MigrationStageModel.created_at` for execution start;
- `MigrationStageModel.started_at` on the real Transformer path until that path actually writes it;
- `PlanningJobModel.updated_at` for phase timing;
- `RepairAttemptModel.updated_at` as a generic repair finish;
- artifact `created_at` as a substitute for workflow completion;
- `WorkflowProjectionService`'s current run-created/run-updated duration calculation;
- frontend receipt time or SSE connection time.

## 8. Existing reusable services/models

- `StateTransitionService` already guarantees ordered persisted workflow event timestamps; timing only reads its output.
- `WorkflowEventModel` supplies run, event type, sequence, payload, and occurrence time.
- `MigrationRunModel`, `MigrationStageModel`, `CommandExecutionModel`, `LlmInvocationModel`, and `RepairAttemptModel` already contain the required row-level evidence.
- `CompatibilityResolutionModel.route` is the approved, ordered, dynamic route authority.
- `run_scoped_stage_id()` already converts catalogue stage IDs to persisted run stage IDs. Reuse it; do not recreate the hash scheme.
- `validation_execution_key()` documents the persisted validation command identity grammar.
- `RunStatus`, `RunPhase`, and `WorkflowEventType` provide canonical vocabulary.
- `ContractModel` in `domain/contracts.py` provides immutable, `extra="forbid"` Pydantic response behavior.
- `runs.py` already hosts versioned authoritative read endpoints and error adaptation.
- `frontend/src/api/runs.ts` already owns typed run reads.
- `AuthoritativeRunDashboard` Overview and `ControlTowerShell.module.css` already provide suitable panel, metric list, metadata, and responsive styles.

## 9. Gaps

1. `MigrationRunModel` has no semantic `started_at` or `finished_at`; events are the stronger authority and make new columns unnecessary.
2. The real Transformer does not populate `MigrationStageModel.started_at`; `STAGE_CREATED` must be used.
3. Some planning reviewer LLM records are created as already completed with identical start/end values and null latency. Their provider duration is not recoverable. V1 must show partial coverage, not count them as authoritative zero-duration calls.
4. `STAGE_VALIDATION_STARTED/COMPLETED/FAILED` are declared but not emitted. Validation V1 is cumulative command activity, not wall-clock phase time.
5. Some cancelled repair paths set status and `updated_at` without setting `completed_at`. Those rows must be reported as unmeasured rather than guessed.
6. Production code does not consistently advance `run_phase` to `STAGED_MIGRATION`, `FINAL_ASSURANCE`, or `DELIVERY_REPORTING`. Event boundaries are therefore more trustworthy than `run.run_phase` history.
7. No current timing endpoint or frontend timing type exists.
8. Existing assistant operational timing is stale and would become a duplicate calculator unless delegated to the new service.

None of these gaps requires a schema migration for V1. Emitting better validation/LLM lifecycle data can be a later improvement; V1 should expose coverage now.

## 10. V1 timing semantics

### Total wall-clock

Total wall-clock begins only when the run start request is durably accepted. Run creation and the pre-run G01 process are excluded.

- Completed: accepted start to staged migration completion.
- Running: accepted start to one UTC `as_of` captured once at request entry.
- Created but not started: `started_at`, `finished_at`, and duration are null.
- Terminal without its required semantic terminal event: finish and duration are null with `measurement_status="unavailable"`; do not fall back to `updated_at`.

### Major phase wall-clock

Use the smallest production-represented major phase set, retaining existing `RunPhase` names:

1. `PREFLIGHT_SNAPSHOT`: `RUN_START_ACCEPTED` to `DISCOVERY_STARTED`.
2. `DISCOVERY_BASELINE`: `DISCOVERY_STARTED` to `G04_APPROVED` (the real transition to `FEASIBILITY_PLANNING`).
3. `FEASIBILITY_PLANNING`: `G04_APPROVED` to `TRANSFORMATION_CONTINUATION_CREATED`.
4. `STAGED_MIGRATION`: `TRANSFORMATION_CONTINUATION_CREATED` to `STAGED_MIGRATION_COMPLETED`.

For the current phase, use `as_of` as the provisional end and mark `status="running"`. Omit `FINAL_ASSURANCE` and `DELIVERY_REPORTING` until the production lifecycle persists their boundaries. These are phase wall-clock spans and may include commands, LLM work, and human waits.

### Stage wall-clock

Build the stage list from the approved ordered compatibility route, not from hardcoded versions and not only from already materialized stage rows. Each route item maps to the existing run-scoped ID helper and a dynamic label derived from its source/target families. Future stages are returned with null timestamps/duration. Started, unsealed stages use `as_of` and `status="running"`.

### Cumulative activity

- LLM: measured workflow-owned invocation latency, including failed attempts that consumed provider time; exclude Assistant and smoke diagnostics.
- Commands: all valid started/finished execution rows, including failed, timed out, cancelled, interrupted, superseded, and retried executions.
- Human approval waiting: all G02-G12 gate waiting intervals occurring after run start, including completed and currently pending intervals. G01 is outside run timing.
- Repair: all valid repair-attempt spans, including superseded attempts; active attempts run to `as_of`.
- Validation: the subset of command activity carrying the stable persisted validation execution identity.
- Sealing: post-approval sealing spans per stage.

Each activity object reports measured count, unmeasured count, duration, and `measurement_status` (`complete`, `partial`, or `unavailable`).

## 11. Exact formulas

Capture `as_of = datetime.now(UTC)` once. Normalize persisted SQLite datetimes to aware UTC using the repository's existing convention (`value if value.tzinfo else value.replace(tzinfo=UTC)`). Compute duration with `(end_utc - start_utc).total_seconds()`. A negative interval is invalid evidence: exclude it, increment `unmeasured_count`, and mark the category partial; never silently clamp it to zero.

```text
total_finished_at = event_time(STAGED_MIGRATION_COMPLETED) when run.status == COMPLETED
total_effective_end = total_finished_at if present else as_of when run is non-terminal
total_duration_seconds = seconds(total_effective_end - event_time(RUN_START_ACCEPTED))
```

```text
stage_start(stage) = event_time(STAGE_CREATED, stage_id)
stage_finish(stage) = event_time(STAGE_SEALED, stage_id)
stage_effective_end = stage_finish or as_of when stage_start exists and stage is not terminal
stage_duration_seconds = seconds(stage_effective_end - stage_start)
```

```text
command_seconds = SUM(seconds(row.finished_at - row.started_at)
                      for every command_executions row in the run
                      where both timestamps exist and end >= start)
```

Do not filter commands by final status. A failed first attempt and successful retry both consumed runtime and both count.

```text
llm_interval(row) = row.latency_ms / 1000
                    when latency_ms is non-null and >= 0
                  else seconds(row.completed_at - row.started_at)
                    when both exist and completed_at > started_at
                  else unmeasured

llm_seconds = SUM(llm_interval(row)
                  for workflow-owned rows where task_type not in
                  {assistant_response, smoke_check})
```

```text
human_wait_seconds = SUM(seconds((terminal_event_time or as_of) - created_event_time)
                         for each sequence-paired G02..G12 lifecycle instance)
```

Pair by `(gate_id, stage_scope)` in event sequence order. Terminal types are approved, rejected, modification requested, or stale. Only one terminal event consumes one open created event. Unpaired terminals are anomalies, not negative time.

```text
repair_seconds = SUM(seconds((attempt.completed_at or as_of_if_active) - attempt.created_at)
                     for each repair_attempt row with a valid authoritative end)
```

Terminal attempts missing `completed_at` are unmeasured. Do not use `updated_at`.

```text
validation_seconds = SUM(valid_command_interval(row)
                         for command rows whose idempotency_key contains ':validation:')
```

This is cumulative validation command execution, including revalidation attempts, and is a subset of `command_seconds`.

```text
sealing_start(stage) = latest event_time(G11_APPROVED or G12_APPROVED)
                       after STAGE_CREATED and before STAGE_SEALED/as_of
sealing_seconds = SUM(seconds((STAGE_SEALED or as_of_if_active) - sealing_start(stage)))
```

Phase formulas:

```text
PREFLIGHT_SNAPSHOT    = DISCOVERY_STARTED - RUN_START_ACCEPTED
DISCOVERY_BASELINE    = G04_APPROVED - DISCOVERY_STARTED
FEASIBILITY_PLANNING  = TRANSFORMATION_CONTINUATION_CREATED - G04_APPROVED
STAGED_MIGRATION      = STAGED_MIGRATION_COMPLETED - TRANSFORMATION_CONTINUATION_CREATED
```

For the single active phase, replace the absent end boundary with `as_of`.

## 12. Overlap/double-counting rules

The UI and API must call the category group **Cumulative activity**, not “breakdown of total.”

- Never display or document `LLM + commands + human wait + repair + validation + sealing = total`.
- Validation is explicitly a subset of command runtime.
- Repair wall-clock can contain LLM, commands, validation, and G10/G11 human waits.
- Stage wall-clock contains all work and waits between stage creation and sealing.
- Phase wall-clock contains activity categories and human waits.
- Concurrent or nested LLM/command work can make cumulative activity sums differ from wall-clock.
- Total wall-clock is the only end-to-end elapsed measure.
- Do not subtract human wait from total to manufacture “active compute time.”
- Coverage counts accompany partial categories; missing evidence is never represented as zero work.

## 13. Proposed backend architecture

Create `backend/app/services/run_timing_service.py` with one public method:

```python
class RunTimingService:
    def build(self, session: Session, run_id: str, *, as_of: datetime | None = None) -> RunTimingDto:
        ...
```

The service should:

1. capture/normalize `as_of` once;
2. load the run or raise a small `RunTimingError("RUN_NOT_FOUND", ...)`;
3. query only run-scoped events, commands, LLM invocations, repair attempts, stages, and the latest approved compatibility resolution;
4. sort events by sequence and calculate all spans in memory with small private functions;
5. construct Pydantic DTOs directly;
6. perform no inserts, updates, artifact reads, filesystem access, state transitions, or event appends.

Keep the aggregation in the service rather than the router. Do not introduce a repository class: SQLAlchemy queries in application services are the existing local pattern, and a timing-specific repository would add no authority or reuse.

Add a `GET /{run_id}/timing` handler to the existing `backend/app/api/routes/runs.py`, using `response_model=RunTimingDto`, dependency-injected service construction, and the existing run error envelope pattern.

Modify `WorkflowProjectionService.build()` to call `RunTimingService.build(session, run_id, as_of=...)` and map its authoritative total/phase/stage values into the already exposed assistant operational fields. Remove its local `_seconds(run.created_at, run.updated_at/latest_event)` timing calculation. The assistant remains a consumer; it must not become another timing implementation.

No caching is needed in V1. The current data volume is one run's operational rows, and timing reads are triggered by the dashboard rather than a high-frequency metrics scraper.

## 14. Proposed API contract

Endpoint:

```http
GET /api/v1/runs/{run_id}/timing
```

Suggested DTOs in `backend/app/domain/contracts.py`:

```python
class TimingActivityDto(ContractModel):
    duration_seconds: float | None = Field(default=None, ge=0)
    measured_count: int = Field(ge=0)
    unmeasured_count: int = Field(ge=0)
    active_count: int = Field(default=0, ge=0)
    measurement_status: Literal["complete", "partial", "unavailable"]

class TimingSpanDto(ContractModel):
    key: str
    label: str
    status: Literal["not_started", "running", "completed", "unavailable"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)

class RunTimingActivityDto(ContractModel):
    llm: TimingActivityDto
    commands: TimingActivityDto
    human_approval_wait: TimingActivityDto
    repair: TimingActivityDto
    validation: TimingActivityDto
    sealing: TimingActivityDto

class RunTimingDto(ContractModel):
    run_id: str
    status: RunStatus
    as_of: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_duration_seconds: float | None = Field(default=None, ge=0)
    total_measurement_status: Literal["running", "complete", "unavailable"]
    activity: RunTimingActivityDto
    phases: list[TimingSpanDto] = Field(default_factory=list)
    stages: list[TimingSpanDto] = Field(default_factory=list)
```

Why a dedicated endpoint instead of expanding `/state`:

- timing is a derived, read-only projection with an `as_of` that changes without workflow mutation;
- it avoids making every SSE state refresh recompute timing;
- it gives Final Migration Summary a stable reusable contract;
- it prevents timing arithmetic from leaking into the frontend.

Return `404` with the existing error envelope for an unknown run. Return a valid DTO with unavailable fields for a created-but-not-started run; that is not an API error.

## 15. Proposed frontend

Add `MigrationTimingPanel.tsx` and mount it in the existing Overview section immediately after the current overview metric cards.

Behavior:

- call `getAuthoritativeRunTiming()` from `frontend/src/api/runs.ts` on mount;
- refresh when the latest authoritative workflow event sequence changes;
- while the returned total is running, tick the displayed total once per second from the last backend duration using `performance.now()`; periodically refresh from the backend (for example every 30 seconds) to bound drift;
- do not infer stage completion or category values from frontend events;
- show an inline unavailable/error state without breaking the rest of the dashboard;
- use `Intl.DateTimeFormat` for start/end display and a small local `formatDuration(seconds)` formatter for `d h m s` output;
- show `—` for unavailable values, never `0s`;
- label partial LLM timing as “Measured LLM execution” and show “N invocation(s) lack timing”;
- label the category section “Cumulative activity — categories may overlap.”

Use existing `panel`, `metricList`, `metadataGrid`, and overview grid styles. Add no chart library and preferably no CSS file; add a few rules to `ControlTowerShell.module.css` only if the existing list cannot render the stage/phase rows accessibly.

## 16. Example JSON

```json
{
  "run_id": "run-8f31b26a107c",
  "status": "COMPLETED",
  "as_of": "2026-08-09T14:48:32Z",
  "started_at": "2026-08-09T14:01:00Z",
  "finished_at": "2026-08-09T14:48:32Z",
  "total_duration_seconds": 2852.0,
  "total_measurement_status": "complete",
  "activity": {
    "llm": {
      "duration_seconds": 312.2,
      "measured_count": 8,
      "unmeasured_count": 1,
      "active_count": 0,
      "measurement_status": "partial"
    },
    "commands": {
      "duration_seconds": 1684.4,
      "measured_count": 23,
      "unmeasured_count": 0,
      "active_count": 0,
      "measurement_status": "complete"
    },
    "human_approval_wait": {
      "duration_seconds": 421.0,
      "measured_count": 9,
      "unmeasured_count": 0,
      "active_count": 0,
      "measurement_status": "complete"
    },
    "repair": {
      "duration_seconds": 188.6,
      "measured_count": 2,
      "unmeasured_count": 0,
      "active_count": 0,
      "measurement_status": "complete"
    },
    "validation": {
      "duration_seconds": 612.8,
      "measured_count": 11,
      "unmeasured_count": 0,
      "active_count": 0,
      "measurement_status": "complete"
    },
    "sealing": {
      "duration_seconds": 28.4,
      "measured_count": 3,
      "unmeasured_count": 0,
      "active_count": 0,
      "measurement_status": "complete"
    }
  },
  "phases": [
    {
      "key": "PREFLIGHT_SNAPSHOT",
      "label": "Preflight & snapshot",
      "status": "completed",
      "started_at": "2026-08-09T14:01:00Z",
      "finished_at": "2026-08-09T14:09:10Z",
      "duration_seconds": 490.0
    },
    {
      "key": "DISCOVERY_BASELINE",
      "label": "Discovery & baseline",
      "status": "completed",
      "started_at": "2026-08-09T14:09:10Z",
      "finished_at": "2026-08-09T14:18:00Z",
      "duration_seconds": 530.0
    },
    {
      "key": "FEASIBILITY_PLANNING",
      "label": "Feasibility & planning",
      "status": "completed",
      "started_at": "2026-08-09T14:18:00Z",
      "finished_at": "2026-08-09T14:24:00Z",
      "duration_seconds": 360.0
    },
    {
      "key": "STAGED_MIGRATION",
      "label": "Staged migration",
      "status": "completed",
      "started_at": "2026-08-09T14:24:00Z",
      "finished_at": "2026-08-09T14:48:32Z",
      "duration_seconds": 1472.0
    }
  ],
  "stages": [
    {
      "key": "angular-18-to-19--a1b2c3d4e5f60708",
      "label": "Angular 18 → 19",
      "status": "completed",
      "started_at": "2026-08-09T14:24:00Z",
      "finished_at": "2026-08-09T14:34:20Z",
      "duration_seconds": 620.0
    },
    {
      "key": "angular-19-to-20--b2c3d4e5f6070819",
      "label": "Angular 19 → 20",
      "status": "completed",
      "started_at": "2026-08-09T14:34:20Z",
      "finished_at": "2026-08-09T14:43:02Z",
      "duration_seconds": 522.0
    },
    {
      "key": "angular-20-to-21--c3d4e5f60708192a",
      "label": "Angular 20 → 21",
      "status": "completed",
      "started_at": "2026-08-09T14:43:02Z",
      "finished_at": "2026-08-09T14:48:32Z",
      "duration_seconds": 330.0
    }
  ]
}
```

The version pairs above are illustrative output derived from route records. No implementation constant may contain them.

## 17. Example UI

```text
Migration timing
────────────────────────────────────────
Total wall clock                 47m 32s
Started                          14:01:00
Completed                        14:48:32

Cumulative activity — categories may overlap
Measured LLM execution            5m 12s  · 1 unmeasured
Command execution                28m 04s
Human approval waiting            7m 01s
Repair activity                   3m 09s
Validation command activity      10m 13s
Sealing activity                    28s

Stages
Angular 18 → 19                  10m 20s
Angular 19 → 20                   8m 42s
Angular 20 → 21                   5m 30s

Major phases
Preflight & snapshot              8m 10s
Discovery & baseline              8m 50s
Feasibility & planning            6m 00s
Staged migration                 24m 32s
```

For a running run, replace “Completed” with “Elapsed as of HH:MM:SS” and keep the total ticking. For future stages display “Not started.”

## 18. Acceptance criteria

- **AC1:** A completed run returns `RUN_START_ACCEPTED.occurred_at`, `STAGED_MIGRATION_COMPLETED.occurred_at`, and their UTC duration.
- **AC2:** A started non-terminal run returns server-`as_of` elapsed duration and leaves `finished_at` null; the read performs no write.
- **AC3:** Every approved route item is returned in route order; a started stage uses `STAGE_CREATED`, and a sealed stage uses `STAGE_SEALED`.
- **AC4:** No Angular version pair or stage count is hardcoded; labels are derived from approved route families.
- **AC5:** Command duration uses only persisted `started_at/finished_at` pairs.
- **AC6:** LLM duration uses only persisted `latency_ms` or valid invocation timestamp pairs; unmeasured calls are counted and not fabricated.
- **AC7:** Human wait uses only persisted G02-G12 gate lifecycle events after run start.
- **AC8:** Failed, timed-out, cancelled, interrupted, superseded, and retried command rows with valid intervals remain in cumulative command activity.
- **AC9:** Aggregation executes no insert, update, delete, state transition, event append, artifact write, or filesystem mutation.
- **AC10:** Backend/Transformer restart does not reset timing because all boundaries are persisted.
- **AC11:** Frontend labels total as wall-clock and labels activity categories as cumulative and overlapping.
- **AC12:** V1 adds no telemetry infrastructure and no database migration.
- **AC13:** Created-but-not-started runs return unavailable timing, not `0s` and not `created_at`-based elapsed time.
- **AC14:** A terminal run missing its semantic terminal event returns unavailable total timing rather than falling back to `updated_at`.
- **AC15:** Validation is labeled cumulative validation command activity; the API/UI does not call it validation phase wall-clock.
- **AC16:** Assistant operational timing delegates to `RunTimingService`; no stale second formula remains.
- **AC17:** `assistant_response` and `smoke_check` invocations do not inflate migration LLM time.
- **AC18:** Negative, inverted, or zero-width unmeasured evidence changes coverage status instead of being clamped or silently accepted.
- **AC19:** Current pending gates and active repair/sealing spans may use the single server `as_of`; completed command/LLM activity never uses frontend time.
- **AC20:** Final Migration Summary consumes `RunTimingDto`/`RunTimingService` values and contains no timing arithmetic.

## 19. Exact implementation tasks

### Task 1 — Define the response contract

- **Exact file:** `backend/app/domain/contracts.py`
- **Class/function:** add `TimingActivityDto`, `TimingSpanDto`, `RunTimingActivityDto`, and `RunTimingDto` near the authoritative run DTOs.
- **Current behavior:** no typed timing response exists.
- **Change:** add immutable Pydantic models with non-negative constraints, explicit status literals, coverage counts, `as_of`, phases, and stages.
- **Formula:** none; contracts only.
- **Dependency:** existing `ContractModel`, `RunStatus`, `datetime`, `Field`, and `Literal`.
- **Complexity:** low.
- **Focused verification:** Pydantic rejects negative durations/counts and serializes aware timestamps/OpenAPI schema correctly.

### Task 2 — Implement one read-only timing authority

- **Exact file:** create `backend/app/services/run_timing_service.py`.
- **Class/function:** `RunTimingService.build()` plus private UTC normalization, interval, event lookup, gate pairing, route-stage, phase, and coverage helpers.
- **Current behavior:** timing is scattered and the assistant projection uses stale generic timestamps.
- **Change:** query run-scoped persisted evidence and build `RunTimingDto` without mutations.
- **Formula:** all formulas in section 11.
- **Dependency:** workflow/command/LLM/repair/stage/compatibility models; `run_scoped_stage_id()`; timing DTOs.
- **Complexity:** medium-high; event pairing and coverage handling are the substantive logic.
- **Focused verification:** deterministic unit tests with an injected `as_of` covering completed/running/not-started/invalid intervals, multiple gates, dynamic routes, failed command retries, partial LLM records, repair attempts, validation filtering, and G11/G12 sealing paths.

### Task 3 — Expose the endpoint

- **Exact file:** `backend/app/api/routes/runs.py`.
- **Class/function:** `get_run_timing_service()` and `read_run_timing()`.
- **Current behavior:** the runs router exposes state and events only.
- **Change:** add `GET /{run_id}/timing`, `response_model=RunTimingDto`, delegate to the service, and adapt `RUN_NOT_FOUND` through the existing error envelope.
- **Formula:** none in the router.
- **Dependency:** Task 1 and Task 2.
- **Complexity:** low.
- **Focused verification:** API test asserts status 200/shape, 404 envelope, and that repeated reads create no rows or events.

### Task 4 — Remove the stale duplicate timing formula

- **Exact file:** `backend/app/services/workflow_projection_service.py`.
- **Class/function:** `WorkflowProjectionService.build()`.
- **Current behavior:** uses `run.created_at`, `run.updated_at`/latest event, and nullable stage model timestamps.
- **Change:** call `RunTimingService.build(session, run_id, as_of=...)`; map authoritative total, phase, and started stage durations to existing assistant operational fields. Keep unsupported values unavailable rather than substituting old formulas.
- **Formula:** delegated entirely to Task 2.
- **Dependency:** Task 2.
- **Complexity:** medium because existing assistant assertions must be updated to semantic start/end behavior.
- **Focused verification:** assistant projection tests prove `RUN_START_ACCEPTED`/terminal event authority and no `created_at`/`updated_at` fallback.

### Task 5 — Synchronize the frontend contract and API client

- **Exact files:** `frontend/src/types/generated/api.ts`, `frontend/src/api/runs.ts`.
- **Class/function:** generated timing types; `getAuthoritativeRunTiming(runId, client?)`.
- **Current behavior:** no frontend timing type or call exists.
- **Change:** regenerate/synchronize the OpenAPI-derived TypeScript definitions and add the GET client function.
- **Formula:** none.
- **Dependency:** Task 1 and Task 3.
- **Complexity:** low.
- **Focused verification:** extend `frontend/src/api/__tests__/runs.test.ts` to assert the encoded `/api/v1/runs/{id}/timing` URL and typed response.

### Task 6 — Add the simple timing panel

- **Exact file:** create `frontend/src/components/MigrationTimingPanel.tsx`.
- **Class/function:** `MigrationTimingPanel`, `formatDuration`, and local fetch/tick state.
- **Current behavior:** Overview shows state/event/artifact counts but no elapsed or activity timing.
- **Change:** render total/start/finish, cumulative activity, route stages, and major phases; show partial/unavailable coverage and an error fallback.
- **Formula:** formatting only; all business durations come from the API. A running display increments from the server-provided duration using monotonic browser elapsed time between refreshes.
- **Dependency:** Task 5; existing dashboard styles.
- **Complexity:** medium.
- **Focused verification:** fake-timer component tests for completed and running totals, dynamic stage counts, partial LLM label, overlap copy, unavailable values, and fetch failure isolation.

### Task 7 — Mount in Overview

- **Exact file:** `frontend/src/components/AuthoritativeRunDashboard.tsx`.
- **Class/function:** `AuthoritativeRunDashboard` Overview branch.
- **Current behavior:** Overview has current phase, generic run metrics, context, and recent decision.
- **Change:** import and mount `MigrationTimingPanel` with `runId` and latest event sequence as a refresh key. Wrap it in the existing `PanelBoundary` so timing failure does not take down workflow controls.
- **Formula:** none.
- **Dependency:** Task 6.
- **Complexity:** low.
- **Focused verification:** dashboard test confirms timing is visible in Overview and a timing-panel failure leaves the dashboard usable.

### Task 8 — Focused backend and frontend regression coverage

- **Exact files:** create `backend/tests/test_run_timing_service.py`; update or create a focused route test near authoritative run route tests; update `frontend/src/api/__tests__/runs.test.ts`; create `frontend/src/components/__tests__/MigrationTimingPanel.test.tsx`; update `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx` only for integration.
- **Class/function:** focused tests named by acceptance criterion.
- **Current behavior:** command and lifecycle tests verify timestamp persistence, but no aggregate timing contract exists.
- **Change:** add the smallest deterministic tests that prove formulas and non-mutation.
- **Formula:** fixtures use fixed UTC timestamps and exact expected `total_seconds()` results.
- **Dependency:** Tasks 1–7.
- **Complexity:** medium.
- **Focused verification:** commands listed in section 21, run only during implementation (not during this planning task).

## 20. Files to modify/create

### Files to create during implementation

- `backend/app/services/run_timing_service.py`
- `backend/tests/test_run_timing_service.py`
- `frontend/src/components/MigrationTimingPanel.tsx`
- `frontend/src/components/__tests__/MigrationTimingPanel.test.tsx`

### Files to modify during implementation

- `backend/app/domain/contracts.py`
- `backend/app/api/routes/runs.py`
- `backend/app/services/workflow_projection_service.py`
- the existing authoritative-run API test module selected during implementation
- `frontend/src/types/generated/api.ts` via the repository's contract synchronization process
- `frontend/src/api/runs.ts`
- `frontend/src/api/__tests__/runs.test.ts`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`
- `frontend/src/components/ControlTowerShell.module.css` only if existing styles prove insufficient; default is no change.

### Files to read only during implementation

- all persistence models, lifecycle services, orchestration files, and frontend support files listed in section 5 that are not explicitly listed for modification.
- especially `backend/app/repositories/models/workflow.py`, `backend/app/repositories/compatibility_models.py`, `backend/app/services/command_executor_service.py`, `backend/app/services/stage_gate_service.py`, `backend/app/services/repair_lifecycle_service.py`, `backend/app/services/validation_runner.py`, `backend/app/orchestration/transformer_graph.py`, and `backend/app/orchestration/transformer_sealing_flow.py`.

### Files that must not change for V1

- any Alembic revision or SQLAlchemy table definition;
- `backend/app/repositories/models/workflow.py` and other persistence model files;
- Transformer graph, worker, continuation, command execution, validation, repair, gate, or sealing lifecycle code;
- artifact contents or artifact store code;
- Usage/token calculation code owned by Session 1;
- branch/worktree/CI/deployment configuration;
- package manifests or lockfiles;
- unrelated frontend panels and navigation.

This planning task itself creates only this Markdown file and changes no production or test file.

## 21. Verification plan

No verification commands were executed while producing this read-only plan. During implementation, run focused checks in this order:

1. Backend service tests for exact arithmetic and coverage:
   - completed total;
   - active elapsed with fixed `as_of`;
   - created/not-started unavailable;
   - terminal event missing unavailable;
   - dynamic one-, three-, and arbitrary-stage routes;
   - stage planned versus created versus sealed;
   - all historical command terminal statuses and retries;
   - LLM `latency_ms`, positive timestamp fallback, synthetic zero-width/unmeasured, failed invocation, and Assistant/smoke exclusion;
   - repeated/stale/current G02-G12 waits;
   - repair completed/active/unmeasured terminal attempts;
   - validation command subset;
   - G11 and G12 sealing paths;
   - inverted timestamps marked partial;
   - no session mutations/events after repeated builds.
2. Focused runs route test for response validation and 404 behavior.
3. Existing assistant projection timing tests updated to the new semantic authority.
4. Frontend API client test.
5. `MigrationTimingPanel` tests with fake timers and mocked API.
6. Dashboard integration/error-boundary test.
7. Backend targeted pytest commands for only the touched timing/route/assistant tests.
8. Frontend targeted Vitest commands for only the touched API/component tests, then typecheck.
9. If repository policy requires it after focused success, run broader backend/frontend suites and build in the implementation session.

Manual demo verification after implementation:

- open a created-but-not-started run and confirm `—`, not a growing timer;
- start a run and confirm total elapsed grows without state writes;
- pause at a gate and confirm total and human wait grow while command/LLM completed totals remain stable;
- complete multiple dynamically planned stages and confirm labels/order/durations;
- restart backend/Transformer and confirm all completed values remain unchanged;
- inspect network response and confirm activity is labeled cumulative/overlapping.

## 22. Risks/regression boundaries

1. **SQLite timezone decoding:** SQLite may return naive values despite timezone-declared columns. Normalize under the repository's UTC convention and test both aware and naive persisted values.
2. **Synthetic LLM timing:** planning reviewer records can appear as zero-duration completed rows. Coverage metadata must prevent false precision.
3. **Event pairing across revisions:** gates can be stale/recreated. Pair in sequence order by gate and stage scope; test modification/stale/retry lifecycles.
4. **Missing `event.stage_id`:** `append_audit_event()` stores stage scope in payload for Transformer gates. The pairing helper must read canonical `event.stage_id` first, then validated payload `stage_id`.
5. **Route identity:** compatibility route uses catalogue stage IDs while stage rows use run-scoped IDs. Reuse `run_scoped_stage_id()` exactly.
6. **Validation classification:** `:validation:` is an existing persisted grammar, not a general tracing system. If that grammar changes, its helper and timing tests must change together. Do not classify by executable text.
7. **Double counting:** repair, validation, sealing, LLM, commands, stages, and phases overlap. API naming and UI copy are part of correctness.
8. **Terminal semantics:** do not regress to `updated_at` when a terminal event is absent; visible unavailability is safer than fabricated certainty.
9. **Read performance:** use a bounded number of run-scoped queries, not one query per stage/gate. No optimization or cache is justified until measured.
10. **Existing assistant behavior:** replacing its stale formula will change existing duration assertions. Update expectations to semantic lifecycle evidence, not to preserve incorrect output.
11. **Frontend clock drift:** browser ticking is presentation only and must be rebased periodically from backend `as_of`; completed durations never tick.

## 23. Integration contract with Usage + Final Summary

Ownership boundary:

```json
{
  "timing": {
    "total_duration_seconds": 2852.0,
    "llm_seconds": 312.2,
    "command_seconds": 1684.4,
    "human_wait_seconds": 421.0,
    "repair_seconds": 188.6,
    "validation_seconds": 612.8,
    "sealing_seconds": 28.4,
    "phases": [],
    "stages": []
  },
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "cost_usd": 0
  }
}
```

- This feature owns elapsed-time formulas and `RunTimingDto`.
- Session 1 owns token, cost, and usage formulas; timing reads `LlmInvocationModel` only for elapsed duration and does not aggregate tokens.
- Final Migration Summary must inject/call `RunTimingService` (or consume the endpoint-equivalent DTO inside the backend) and the Usage service. It must not query timing rows and recompute durations.
- Assistant workflow projection is also a consumer of `RunTimingService`.
- If Final Summary is generated before run completion, it should preserve `finished_at=null`, `as_of`, running status, and coverage metadata rather than freezing a fake terminal duration.
- JSON field names in the summary should match the timing DTO or nest the DTO unchanged to avoid semantic drift.

## 24. Web references

- [Python `datetime` documentation](https://docs.python.org/3/library/datetime.html): datetime subtraction yields a `timedelta` only when both values are consistently naive or aware; V1 normalizes persisted UTC values before subtraction.
- [Python `timedelta.total_seconds()` documentation](https://docs.python.org/3/library/datetime.html#datetime.timedelta.total_seconds): returns the full duration in seconds and avoids the common mistake of reading the modulo-day `.seconds` attribute.
- [FastAPI response model documentation](https://fastapi.tiangolo.com/tutorial/response-model/): `response_model` validates, documents, serializes, and filters endpoint output; the timing route should declare `RunTimingDto` explicitly.

No external observability architecture was consulted or adopted.

## 25. Complexity estimate

Overall: **medium (approximately 4–6 focused engineering days including tests and review)**.

- Contract and endpoint: 0.5 day.
- Aggregation service and edge-case tests: 2–3 days.
- Assistant projection delegation/regression updates: 0.5–1 day.
- Frontend client/panel/tests: 1–1.5 days.
- Integrated verification and cleanup: 0.5 day.

No database, infrastructure, orchestration, or deployment work is expected. The largest risk is semantic correctness in gate/event pairing and partial evidence reporting, not code volume.

## 26. Recommended implementation order

1. Add DTOs and fixed-time service tests.
2. Implement `RunTimingService` until total, phase, stage, and activity tests pass.
3. Add the typed runs endpoint and non-mutation/404 route tests.
4. Delegate existing assistant timing fields to the service and update semantic expectations.
5. Synchronize TypeScript contracts and add the run API client call.
6. Build/test `MigrationTimingPanel` using completed, running, partial, and unavailable fixtures.
7. Mount the panel in Overview with the existing error boundary and styles.
8. Run focused backend/frontend checks, then broader repository checks only after focused success.
9. Hand `RunTimingDto` to the Final Migration Summary owner as the sole timing input.

Stop after this V1. Add persisted run/stage columns, validation events, richer timelines, or historical analytics only when a measured product need requires them.
