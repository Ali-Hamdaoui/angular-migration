# LLM Usage / Token Consumption V1 — Read-only Audit and Implementation Plan

Date: 2026-08-09  
Repository: `C:\Users\abdelilah.mortaki\Desktop\angular-migration`  
Audited branch: `dev`  
Audited commit: `60942d527e8cc7537ac24b031fc11c49abe2b513` (`fix governed repair recovery lifecycle`)

## 1. Executive verdict

The repository already contains roughly 70% of this feature. Azure Responses usage reaches the governed gateway, successful usage is persisted in a run-scoped, invocation-bound table, a typed `GET /api/v1/runs/{run_id}/usage` endpoint already sums tokens and estimated costs, and the authoritative dashboard already fetches and renders those totals.

V1 should extend that existing vertical slice. It should not create a telemetry platform, a second endpoint, a new table, or a new dashboard. The smallest complete change is:

1. preserve Azure's provider-reported `total_tokens` instead of rebuilding it;
2. join existing `llm_invocations` to `usage_cost_records` in the existing usage application service;
3. add run-scoped call/retry counts and breakdowns by persisted phase marker, Angular `stage_id`, role, and `task_type`;
4. explicitly report how many logical calls do and do not have persisted usage;
5. extend the current LLM Diagnostics section with cards and compact lists.

No database migration is needed. The existing schema already has the required keys and dimensions. Historical runs can be queried directly. Their totals remain limited to usage that was actually persisted; V1 must not estimate or backfill missing provider usage.

The main caveat is retry semantics. Transport retries normally remain inside one `LlmInvocationModel` row and increment `retries`; repair semantic retries can be separate invocation rows and older repair code also seeds the retry row's `retries` value. Therefore V1 should expose the persisted retry count as **recorded retries**, not invent `provider_calls = llm_calls + retries` or claim billing-level completeness.

## 2. V1 objective

For one persisted migration run, expose and render a stable, historical, run-scoped summary of:

- authoritative persisted provider input tokens;
- authoritative persisted provider output tokens;
- authoritative persisted provider total tokens;
- logical LLM invocation rows;
- persisted retry/repeated-call metadata where it is authoritative;
- calls with and without persisted usage;
- token/call breakdown by the existing invocation phase marker;
- token/call breakdown by Angular `stage_id`, including an explicit unassigned bucket;
- token/call breakdown by persisted LLM `role`;
- token/call breakdown by persisted `task_type` as the authoritative purpose/operation.

The result must be usable by the current LLM Diagnostics UI and by the separately owned Final Migration Summary without either consumer recalculating token usage.

## 3. Explicit non-goals

- A new telemetry platform or event pipeline.
- OpenTelemetry, Prometheus, external dashboards, or exporters.
- A new usage endpoint when `/api/v1/runs/{run_id}/usage` already owns the concern.
- A pricing or billing engine.
- Per-user billing or quotas.
- Cross-run history, comparisons, cohorts, or analytics.
- Advanced charts.
- Prompt-length token estimates or tokenizer-based reconstruction.
- Parsing prompts, artifacts, or free text to guess role, purpose, phase, or stage.
- Replaying completed LLM calls or recomputing historical runs.
- Persisting token-detail subfields such as cached or reasoning tokens in V1.
- Redesigning retry execution or normalizing legacy retry history.
- Changing migration, repair, approval, Assistant, or LLM execution behavior beyond preserving the provider's reported `total_tokens`.
- A new DB table or column.

Existing cost calculation is retained only for backward compatibility: configured per-million input/output prices are applied when each `UsageCostRecordModel` is created, and the current endpoint already sums `input_cost_usd`, `output_cost_usd`, and `total_cost_usd`. The UI may continue to label these values **Estimated cost**. No new cost logic belongs in V1.

## 4. Current architecture/code truth

### One real call traced end to end

The Analysis proposer is a representative production path:

1. `AnalysisEvidenceApplicationService.generate()` in `backend/app/services/analysis_evidence_application_service.py` creates an in-progress `LlmInvocationModel` with `run_id`, `role="phase_proposer"`, `task_type="analysis_summary"`, and `stage="analysis"`.
2. `AnalysisAgentService._propose()` in `backend/app/services/analysis_application_service.py` creates `LlmRequest` and calls `AzureOpenAILLMGateway.complete()`.
3. `AzureOpenAILLMGateway.complete()` in `backend/app/llm_gateway/azure_gateway.py` sends `POST .../openai/responses`, validates the response, calls `_extract_usage(raw)`, and constructs `LlmUsageRecord` through `build_usage_record()`.
4. `_extract_usage()` reads provider `usage.input_tokens` and `usage.output_tokens`. Current code does **not** retain raw `usage.total_tokens`; `build_usage_record()` recalculates it as input plus output.
5. `AnalysisEvidenceApplicationService._complete()` persists proposer and reviewer usage as one `UsageCostRecordModel` per invocation after the complete Analysis package is accepted.
6. `UsageCostRecordModel` in `backend/app/repositories/models/workflow.py` stores the token values and costs. Its `invocation_id` is unique and references `llm_invocations.id`; both records carry `run_id`, and stage-scoped calls also carry `stage_id`.
7. Analysis also writes immutable evidence artifacts containing usage/provenance in `AnalysisEvidenceApplicationService._complete()`. Other callers write `llm_usage_cost.json` or role-specific evidence.
8. `LlmEvidenceApplicationService.usage()` queries `usage_cost_records` by `run_id` and returns sums.
9. `usage()` in `backend/app/api/routes/llm.py` exposes the result at both legacy and v1 router mounts; the frontend uses `/api/v1/runs/{run_id}/usage`.
10. `getLlmUsage()` in `frontend/src/api/llm.ts` loads it into `LlmDiagnosticsPanel`, which already renders input/output/total tokens and estimated cost in the authoritative dashboard's LLM section.

### Direct answers to the audit questions

| Question | Current truth |
|---|---|
| 1. Does Azure usage already reach the gateway? | **Yes.** `AzureOpenAILLMGateway.complete()` calls `_extract_usage()` on a completed response. `_extract_usage()` reads `input_tokens` and `output_tokens`, with legacy `prompt_tokens`/`completion_tokens` fallbacks. Raw `total_tokens` and detail objects are currently ignored. |
| 2. Are input/output/total tokens persisted? | **Yes for paths that create a usage row.** They are persisted in `UsageCostRecordModel.input_tokens`, `.output_tokens`, and `.total_tokens`. Current Azure `total_tokens` is derived as input + output before persistence rather than copied from the provider. |
| 3. In which table/model? | Authoritative production usage is `usage_cost_records` / `UsageCostRecordModel`. Provenance and dimensions are `llm_invocations` / `LlmInvocationModel`. The older `llm_usage_records` / `LlmUsageRecordModel` is used by mock/legacy DTO paths and must not become the V1 source. |
| 4. Are failed calls persisted? | **Invocation evidence: yes. Usage: conditional.** Failed invocations are retained with status/failure/transport fields. A usage row exists only when a caller persisted provider usage. `LlmEvidenceApplicationService._fail_assistant()` can persist available usage, but it also currently creates a zero usage row for one structured-response-invalid path. Analysis/planning/repair failure paths do not uniformly persist provider usage after post-provider validation failures. |
| 5. Are retries separate invocation rows? | **Transport retries: no.** `AzureOpenAILLMGateway.complete()` loops internally and stores the additional attempt count in `LlmInvocationModel.retries`. **Semantic/application repeats: sometimes yes.** Analysis reviewer revisions and repair semantic retries can create distinct invocation rows. Repair semantic retry rows may also have a seeded `retries` value, so adding invocation count to retries would double-count some repeated calls. |
| 6. Is `run_id` persisted? | **Yes**, non-null and indexed on both authoritative models. |
| 7. Is `stage_id` persisted? | **Available where the caller has an Angular stage.** It is nullable on both models. Repair and transformation prompt explanation populate it; Analysis, Planning, Assistant, and smoke calls use `None`. |
| 8. Is operation/purpose/role persisted? | **Yes.** `LlmInvocationModel.role` and `.task_type` are non-null. `task_type` is the authoritative purpose/operation; no prompt parsing is required. |
| 9. Is phase persisted? | There is no field named `phase`. `LlmInvocationModel.stage` is a nullable phase-like marker populated with values such as `analysis`, `planning`, `repair`, `prompt_explanation`, and `smoke`; Assistant calls currently use `None`. |
| 10. Is model/deployment persisted? | `provider` and `deployment_alias` are persisted. There is no separate authoritative model-name column. The gateway request manifest may contain the resolved deployment name, but V1 should expose the persisted alias rather than reading artifacts to reconstruct it. |
| 11. Does a backend service already aggregate usage? | **Yes.** `LlmEvidenceApplicationService.usage()` is the live API authority. `WorkflowProjectionService.build()` separately aggregates completed-call usage for Assistant operational statistics, and `summarize_usage()` in `mock_gateway.py` aggregates in-memory gateway records. These are not fully aligned and Final Migration Summary must not add a fourth calculation. |
| 12. Does `/usage` expose some/all required data? | **Some.** It exposes run ID, usage-record count, input/output/total tokens, estimated costs, pricing versions, and per-record token totals. It lacks logical call count, calls without usage, retry count, phase/stage/role/purpose breakdowns, and typed record items. |
| 13. Does the frontend consume usage? | **Yes.** `LlmDiagnosticsPanel` calls `getLlmUsage()` and displays overall token/cost totals. The legacy/mock `LlmUsagePanel` sums `MigrationRunDto.llm_usage`, but it is not the current authoritative dashboard path. |

### Persisted role and purpose values proven by production constructors

| Production flow | Persisted `role` | Persisted `task_type` | Persisted `stage` | Angular `stage_id` |
|---|---|---|---|---|
| Analysis proposer | `phase_proposer` | `analysis_summary` | `analysis` | null |
| Analysis reviewer | `phase_reviewer` | `analysis_review` | `analysis` | null |
| Planning proposer | `phase_proposer` | `plan_rationale` | `planning` | null |
| Planning reviewer | `phase_reviewer` | `planning_review` | `planning` | null |
| Repair proposer | `repair_proposer` | `repair_diagnosis` | `repair` | populated |
| Repair reviewer | `repair_reviewer` | `repair_review` | `repair` | populated |
| CLI prompt explanation | `assistant` in the invocation row | `transformation_explanation` | `prompt_explanation` | populated |
| Run Assistant | `assistant` | `assistant_response` | null | null |
| Governed smoke | `assistant` | `smoke_check` | `smoke` | null |

The prompt-explanation gateway request currently uses `phase_reviewer`, while its pre-created persisted invocation uses `assistant`. The persisted invocation is the reporting authority; V1 must not overwrite or guess around this discrepancy.

## 5. Files inspected

### Repository guidance and state

- `AGENT.md`
- current branch, status, HEAD, recent log, targeted `git log`, `git blame`, and history searches

### Gateway and contracts

- `backend/app/llm_gateway/azure_gateway.py`
- `backend/app/llm_gateway/contracts.py`
- `backend/app/llm_gateway/mock_gateway.py`
- `backend/app/llm_gateway/README.md`
- `backend/app/core/config.py`
- `backend/app/domain/contracts.py`

### Persistence and migrations

- `backend/app/repositories/models/workflow.py`
- `backend/app/repositories/models/__init__.py`
- `backend/app/repositories/analysis_models.py`
- `backend/alembic/versions/20260710_01_initial_workflow_state.py`
- `backend/alembic/versions/20260718_03_llm_invocation_evidence.py`
- `backend/alembic/versions/20260719_01_llm_provenance.py`
- `backend/alembic/versions/20260719_02_schema_alignment.py`
- `backend/alembic/versions/20260724_18_llm_provider_failure_evidence.py`
- `backend/alembic/versions/20260725_22_transport_diagnostics.py`

### Application services and call sites

- `backend/app/services/llm_evidence_application_service.py`
- `backend/app/services/workflow_projection_service.py`
- `backend/app/services/assistant_context_service.py`
- `backend/app/services/analysis_application_service.py`
- `backend/app/services/analysis_evidence_application_service.py`
- `backend/app/services/planning_application_service.py`
- `backend/app/services/planning_review_application_service.py`
- `backend/app/services/planning_review_evidence_application_service.py`
- `backend/app/services/prompt_explanation_service.py`
- `backend/app/services/repair_application_service.py`
- `backend/app/services/migration_run_service.py`

### API

- `backend/app/api/llm_contracts.py`
- `backend/app/api/routes/llm.py`
- `backend/app/api/routes/analysis.py`
- `backend/app/api/routes/planning_review.py`
- `backend/app/api/routes/transformation.py`
- `backend/app/api/routes/assistant.py`
- `backend/app/api/router.py`

### Frontend

- `frontend/src/api/llm.ts`
- `frontend/src/types/llm.ts`
- `frontend/src/types/assistant.ts`
- `frontend/src/types/generated/api.ts`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/LlmDiagnosticsPanel.tsx`
- `frontend/src/components/LlmUsagePanel.tsx`
- `frontend/src/components/AnalysisReviewPanel.tsx`
- `frontend/src/components/TransformationPanel.tsx`
- `frontend/src/components/AssistantPanel.tsx`
- `frontend/src/components/control-tower/ControlTowerSidebar.tsx`
- `frontend/src/components/ControlTowerShell.module.css`

### Tests used as secondary documentation only

- `backend/tests/test_llm_evidence_s2_f03.py`
- `backend/tests/test_llm_verification_s2_f03.py`
- `backend/tests/test_llm_gateway.py`
- `backend/tests/test_azure_response_boundary.py`
- `backend/tests/test_analysis_evidence_persistence_api_s2_f04_i02.py`
- `backend/tests/test_planning_review_evidence_s2_f07_i02.py`
- `backend/tests/test_transformer_repair_failure_governance.py`
- `backend/tests/test_assistant_amfa221.py`
- `backend/tests/test_assistant_r5_workflow_projection.py`
- `frontend/src/api/__tests__/llm.test.ts`
- `frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`

No runtime DB file was present under the repository, so no runtime DB was opened. No backend, frontend, migration, or test process was run.

## 6. Existing functionality we can reuse

- `AzureOpenAILLMGateway.complete()` is the single governed provider boundary.
- `_extract_usage()` is already the response usage parser.
- `LlmUsageRecord` already carries input/output/total tokens, retry count, stage ID, task type, and cost fields.
- `LlmInvocationModel` already carries run, Angular stage, role, task type, provider, deployment alias, phase-like stage, status, retries, and timestamps.
- `UsageCostRecordModel` already carries one usage record per invocation, enforced by a unique foreign key.
- Existing indexes support run- and stage-scoped reads.
- `LlmEvidenceApplicationService.usage()` already owns authorization, run existence, aggregation, and endpoint response construction.
- `/runs/{run_id}/usage` is already mounted under `/api/v1` and already consumed by the frontend.
- `getLlmUsage()` and `LlmUsageResponse` already establish the frontend client/type path.
- `LlmDiagnosticsPanel` is already the authoritative dashboard location and already handles loading and partial errors.
- Existing estimated cost fields may be retained without adding cost behavior.
- Existing CSS primitives `metricList`, `metadataGrid`, `panel`, and `note` are sufficient for cards/lists; no chart dependency is needed.

`summarize_usage()` in `mock_gateway.py` demonstrates useful grouping names, but it works on transient `LlmUsageRecord` objects and groups by `agent_kind`, not persisted role. It should not be called by the production run endpoint.

## 7. Current DB/model truth

### Authoritative tables

`llm_invocations` / `LlmInvocationModel`:

- `id`: logical invocation identity.
- `run_id`: required, indexed, foreign-keyed to `migration_runs.id`.
- `stage_id`: nullable, indexed, foreign-keyed to `migration_stages.id`.
- `role`: required persisted role.
- `task_type`: required persisted purpose.
- `provider`, `deployment_alias`: required provider/deployment provenance.
- `stage`: nullable phase-like marker.
- `status`: in-progress/completed/failed/blocked lifecycle.
- `retries`: non-negative persisted additional-attempt metadata.
- `provider_request_id` and transport/failure fields: available for diagnostics, not needed for V1 totals.
- unique constraint `(run_id, idempotency_key)` prevents logical replay duplication.

`usage_cost_records` / `UsageCostRecordModel`:

- `invocation_id`: required, unique foreign key to `llm_invocations.id`; one usage row can be counted at most once per logical invocation.
- `run_id`: required and indexed.
- `stage_id`: nullable and indexed.
- `input_tokens`, `output_tokens`, `total_tokens`: required integers.
- price and cost fields: required and already exposed as estimates.
- `pricing_version`, `created_at`: required provenance.

### Non-authoritative/legacy usage table

`llm_usage_records` / `LlmUsageRecordModel` predates the governed invocation evidence path. Current production writers do not use it; `mock_migration_service.py` supplies a mock DTO instead. V1 must not union this table with `usage_cost_records`, because doing so risks duplicate or mock data.

### Schema verdict

The schema is sufficient. A join on `UsageCostRecordModel.invocation_id == LlmInvocationModel.id`, with both sides constrained to the requested `run_id`, supplies every V1 grouping field. No Alembic revision is justified.

## 8. Current API truth

Current route:

`GET /api/v1/runs/{run_id}/usage`

Route function: `usage()` in `backend/app/api/routes/llm.py`  
Service function: `LlmEvidenceApplicationService.usage()`  
Response model: `LlmUsageResponse` in `backend/app/api/llm_contracts.py`

Current fields:

- `run_id`
- `invocation_count` (currently the number of usage rows, not all invocation rows)
- `input_tokens`
- `output_tokens`
- `total_tokens`
- input/output/total estimated cost
- `pricing_versions`
- untyped `records`

The route already enforces run existence and actor authorization through the service. It is the correct V1 endpoint and should be extended in place. FastAPI's existing `response_model=LlmUsageResponse` should remain.

Compatibility decision: preserve all existing response fields. Keep `invocation_count` with its present usage-record-count meaning for existing consumers, mark it as a compatibility field in code documentation, and add unambiguous `llm_calls`, `usage_recorded_calls`, and `usage_unavailable_calls` fields.

## 9. Current frontend truth

The live application uses `AuthoritativeRunDashboard`, whose sidebar contains `LLM Diagnostics`. That section renders `LlmDiagnosticsPanel`, and the panel independently loads:

- readiness;
- invocation activity;
- usage.

It already displays overall input, output, total tokens, and estimated costs. It displays only the latest invocation's retry count and does not display run-level call count or breakdowns.

`LlmUsagePanel` belongs to the older `ControlTowerShell`/mock `MigrationRunDto.llm_usage` path. It should remain untouched in V1. Adding the new UI there would duplicate authority and implementation.

Best current location: extend the usage portion of `LlmDiagnosticsPanel` inside the existing `LLM Diagnostics` dashboard section. No new navigation entry or component is required.

## 10. Gaps

1. `_extract_usage()` ignores provider `total_tokens`; the gateway rebuilds it from input and output.
2. `/usage.invocation_count` is usage-row count, not total logical invocation count.
3. No run-level retry total exists.
4. No calls-without-usage count exists, so zero and unavailable are visually conflated.
5. No phase, Angular stage, role, or purpose breakdown exists.
6. `records` is `list[dict[str, Any]]` rather than a typed response item.
7. The endpoint queries usage rows alone, so it cannot group by invocation role/task/stage or count failed/in-progress invocations without usage.
8. `WorkflowProjectionService.build()` has a separate aggregation and only includes completed invocation usage, while `/usage` includes every persisted usage row. This is a divergence risk for Assistant and Final Migration Summary.
9. Failed-call usage persistence is not uniform. V1 can report only what exists and must make missing usage explicit.
10. Gateway transport retry attempts are held inside one invocation. Only the final successful response usage is currently returned; usage from an earlier incomplete response is not persisted even when present in the raw response.
11. Repair retry metadata has mixed legacy semantics; deriving a new provider-call total from it would be unsafe.
12. The frontend renders `0` as a fallback when usage fails to load or is absent, which can make unavailable look like a measured zero.

## 11. Proposed V1 architecture

Use the existing authority chain:

```text
Azure Responses usage
  -> AzureOpenAILLMGateway._extract_usage
  -> LlmUsageRecord
  -> existing caller persistence
  -> UsageCostRecordModel (tokens/cost, one per invocation)
     + LlmInvocationModel (run/phase/stage/role/purpose/status/retries)
  -> LlmEvidenceApplicationService.usage
  -> existing GET /api/v1/runs/{run_id}/usage
  -> getLlmUsage
  -> existing LlmDiagnosticsPanel
```

The application service remains the single run-usage aggregation owner. Add a small module-level/session-scoped helper in `llm_evidence_application_service.py` that returns the four-field reusable totals plus the full endpoint projection. `WorkflowProjectionService` and the future Final Migration Summary should consume that helper instead of writing their own sums.

No repository class is needed: this is one bounded read query over two ORM models. No cache is needed: completed historical rows are already durable, and active runs are small enough for a run-scoped read.

## 12. Data flow

1. A caller creates one governed `LlmInvocationModel` before external work.
2. Azure returns a Responses object.
3. The gateway validates `usage.input_tokens`, `usage.output_tokens`, and `usage.total_tokens` as non-negative integers and preserves them.
4. The caller persists one `UsageCostRecordModel` when provider usage is available.
5. The usage service loads all non-deterministic-fallback invocation rows for the requested run and all usage rows joined by invocation ID.
6. Each logical invocation contributes once to call counts.
7. Each usage row contributes once to token and estimated-cost sums, regardless of final invocation status, because a persisted provider usage record represents consumed usage.
8. Missing usage contributes no tokens and increments `usage_unavailable_calls`; it is not converted to a made-up zero usage record by the aggregation layer.
9. The service groups the same joined rows by persisted role, `task_type`, phase mapping, and nullable Angular stage.
10. FastAPI validates and serializes the typed result.
11. The frontend renders totals and compact lists from the response without recalculation.

## 13. Aggregation formulas

Let `I(run)` be `llm_invocations` rows for `run_id`, excluding rows whose persisted provider is exactly `deterministic_fallback`. Let `U(run)` be `usage_cost_records` rows whose `run_id` matches and whose `invocation_id` joins to an item in `I(run)` with the same `run_id`.

The same-run condition on both tables is intentional defense in depth.

```text
TOTAL INPUT TOKENS  = sum(u.input_tokens  for u in U(run))
TOTAL OUTPUT TOKENS = sum(u.output_tokens for u in U(run))
TOTAL TOKENS        = sum(u.total_tokens  for u in U(run))
LLM CALLS           = count(I(run))
USAGE RECORDED CALLS   = count(distinct u.invocation_id for u in U(run))
USAGE UNAVAILABLE CALLS = LLM CALLS - USAGE RECORDED CALLS
RECORDED RETRIES     = sum(max(i.retries, 0) for i in I(run))
```

`invocation_count` remains `count(U(run))` for backward compatibility. Because `usage_cost_records.invocation_id` is unique, this equals `USAGE RECORDED CALLS` for valid data.

Do not compute `TOTAL TOKENS` as API input plus API output. Sum the persisted provider total field independently so the three API totals each reconcile to their own authoritative column.

Do not compute a `provider_calls` field in V1. Current retry metadata is insufficiently uniform for a guaranteed formula.

### Breakdown row formula

For each grouping key, use the same invocation set and left join:

```text
calls             = count(group invocation rows)
retry_calls       = sum(group invocation retries)
input_tokens      = sum(joined persisted input tokens, missing usage contributes nothing)
output_tokens     = sum(joined persisted output tokens, missing usage contributes nothing)
total_tokens      = sum(joined persisted total tokens, missing usage contributes nothing)
usage_recorded_calls = count(group invocation rows with a joined usage row)
usage_unavailable_calls = calls - usage_recorded_calls
```

### Phase mapping

There is no persisted `phase` column. Use only the persisted invocation `stage` marker and this minimal deterministic mapping:

| Persisted `LlmInvocationModel.stage` | V1 phase key |
|---|---|
| `analysis` | `analysis` |
| `planning` | `planning` |
| `repair` | `transformation` |
| `prompt_explanation` | `transformation` |
| `smoke` | `diagnostics` |
| null/empty | `unassigned` |
| any other non-empty value | expose the normalized persisted value unchanged |

This mapping does not inspect prompt text or workflow events. `unassigned` is required so phase breakdown totals reconcile. Assistant usage remains visible and is independently identifiable by role/purpose.

### Angular stage grouping

Use `LlmInvocationModel.stage_id` as the key. Do not infer a stage from artifact paths or timestamps. Emit `stage_id: null` with label `Run-level / unassigned` so stage totals reconcile with overall totals while still showing real Angular stage IDs where available.

### Retry and failed-call decision

- Every distinct persisted invocation row contributes once to `llm_calls`, including failed calls, because it is a durable logical LLM attempt.
- `deterministic_fallback` rows do not contribute because no LLM provider was called.
- Idempotent replay does not create a new invocation row and therefore is not counted again.
- Transport retries inside the gateway do not create rows; their persisted additional-attempt count contributes to `retry_calls`.
- Semantic repeats that create a new invocation row contribute to `llm_calls` once per row.
- Do not add `llm_calls + retry_calls` to claim provider calls.
- A failed invocation with a persisted usage row contributes its tokens exactly once.
- A failed invocation without a usage row contributes no tokens and increments `usage_unavailable_calls`.
- No prompt-length estimate, zero usage row, or synthetic token count is created by aggregation.

## 14. Proposed API contract

Keep:

`GET /api/v1/runs/{run_id}/usage`

Add typed models in `backend/app/api/llm_contracts.py`:

```python
class LlmUsageTotals(ContractModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_calls: int

class LlmUsageBreakdown(ContractModel):
    key: str
    label: str
    calls: int
    retry_calls: int
    usage_recorded_calls: int
    usage_unavailable_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    stage_id: str | None = None

class LlmUsageRecordResponse(ContractModel):
    invocation_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost_usd: float
    pricing_version: str
```

Extend `LlmUsageResponse` without removing current fields:

```python
class LlmUsageResponse(ContractModel):
    run_id: str
    invocation_count: int                 # compatibility: usage rows
    llm_calls: int
    retry_calls: int
    usage_recorded_calls: int
    usage_unavailable_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_versions: list[str]
    by_phase: list[LlmUsageBreakdown]
    by_stage: list[LlmUsageBreakdown]
    by_role: list[LlmUsageBreakdown]
    by_purpose: list[LlmUsageBreakdown]
    records: list[LlmUsageRecordResponse]
```

The reusable Final Migration Summary contract is the existing flat four-field subset represented by `LlmUsageTotals`. The usage service should expose it from the same aggregate result; the Final Migration Summary must consume this value and must not issue its own token query or sum records.

Use stable sorting: token total descending, then key ascending. This makes API tests and UI ordering deterministic.

## 15. Proposed frontend

Extend the usage area of `LlmDiagnosticsPanel`; retain readiness/activity diagnostics below or alongside it.

Render:

- Total tokens
- Input tokens
- Output tokens
- LLM calls
- Recorded retries
- Usage unavailable for N calls, only when `usage_unavailable_calls > 0`
- By phase list
- By role list
- By Angular stage list
- By purpose list in a collapsed `<details>` or after role/stage if the panel remains compact

Each list row needs only label, total tokens, and calls. Do not add charts. Use `toLocaleString()` and existing layout classes. Human-readable labels are a presentation transform of authoritative keys (`replaceAll("_", " ")` plus title casing); the raw key remains in the API response.

Loading/unavailable behavior:

- While usage is loading, show the existing loading state.
- If the usage request fails, do not fall back to the latest invocation or display run totals as zero. Show `Usage unavailable` for the run summary while keeping readiness/activity diagnostics usable.
- A successful response containing actual zero totals renders `0`.
- An empty stage ID bucket renders `Run-level / unassigned`.

The current estimated cost rows may remain, labeled `Estimated`, because safe calculation already exists. They are secondary and must not drive acceptance of this feature.

## 16. Example JSON

```json
{
  "run_id": "run-2026-08-09-001",
  "invocation_count": 21,
  "llm_calls": 24,
  "retry_calls": 3,
  "usage_recorded_calls": 21,
  "usage_unavailable_calls": 3,
  "input_tokens": 120450,
  "output_tokens": 18420,
  "total_tokens": 138870,
  "input_cost_usd": 0.0301125,
  "output_cost_usd": 0.03684,
  "total_cost_usd": 0.0669525,
  "pricing_versions": ["mvp-pricing-2026-01"],
  "by_phase": [
    {
      "key": "transformation",
      "label": "Transformation",
      "calls": 12,
      "retry_calls": 2,
      "usage_recorded_calls": 11,
      "usage_unavailable_calls": 1,
      "input_tokens": 54000,
      "output_tokens": 9100,
      "total_tokens": 63100,
      "stage_id": null
    },
    {
      "key": "analysis",
      "label": "Analysis",
      "calls": 4,
      "retry_calls": 1,
      "usage_recorded_calls": 4,
      "usage_unavailable_calls": 0,
      "input_tokens": 22000,
      "output_tokens": 3200,
      "total_tokens": 25200,
      "stage_id": null
    }
  ],
  "by_stage": [
    {
      "key": "angular-18-to-19--abc",
      "label": "angular-18-to-19--abc",
      "stage_id": "angular-18-to-19--abc",
      "calls": 4,
      "retry_calls": 1,
      "usage_recorded_calls": 4,
      "usage_unavailable_calls": 0,
      "input_tokens": 15000,
      "output_tokens": 2500,
      "total_tokens": 17500
    },
    {
      "key": "unassigned",
      "label": "Run-level / unassigned",
      "stage_id": null,
      "calls": 12,
      "retry_calls": 1,
      "usage_recorded_calls": 10,
      "usage_unavailable_calls": 2,
      "input_tokens": 65000,
      "output_tokens": 9000,
      "total_tokens": 74000
    }
  ],
  "by_role": [
    {
      "key": "repair_proposer",
      "label": "Repair proposer",
      "calls": 4,
      "retry_calls": 1,
      "usage_recorded_calls": 4,
      "usage_unavailable_calls": 0,
      "input_tokens": 18000,
      "output_tokens": 4200,
      "total_tokens": 22200,
      "stage_id": null
    }
  ],
  "by_purpose": [
    {
      "key": "repair_diagnosis",
      "label": "Repair diagnosis",
      "calls": 4,
      "retry_calls": 1,
      "usage_recorded_calls": 4,
      "usage_unavailable_calls": 0,
      "input_tokens": 18000,
      "output_tokens": 4200,
      "total_tokens": 22200,
      "stage_id": null
    }
  ],
  "records": []
}
```

The abbreviated example omits additional breakdown rows and record items. In a real response, each complete grouping contains all buckets needed for reconciliation.

## 17. Example UI

```text
LLM Usage
------------------------------------------------
Total tokens                              138,870
Input                                     120,450
Output                                     18,420
LLM calls                                      24
Recorded retries                                3
Usage unavailable for                           3 calls

By phase
Transformation                           63,100   12 calls
Planning                                 31,450    5 calls
Analysis                                 25,200    4 calls
Unassigned                               19,120    3 calls

By role
Phase proposer                           45,200    6 calls
Phase reviewer                           31,450    5 calls
Repair proposer                          22,200    4 calls
Repair reviewer                          12,100    3 calls
Assistant                                27,920    6 calls

By Angular stage
18 -> 19                                 34,500    4 calls
19 -> 20                                 30,500    5 calls
Run-level / unassigned                   73,870   15 calls
```

## 18. Acceptance criteria

### AC1 — authoritative totals

For a run with persisted usage records, API `input_tokens`, `output_tokens`, and `total_tokens` equal the independent sums of `UsageCostRecordModel.input_tokens`, `.output_tokens`, and `.total_tokens` joined to invocations from that run.

### AC2 — retries and repeated calls

Each persisted invocation contributes exactly once to `llm_calls`. Persisted `retries` contribute once to `retry_calls`. Any usage already persisted for a retried or repeated invocation contributes exactly once through the unique `invocation_id` join. The API does not derive or claim a total provider-call count.

### AC3 — no estimation

No API or UI token value is estimated from prompt text, character length, context-budget estimates, or artifact contents.

### AC4 — strict run isolation

An invocation or usage row from another run is never included, even if malformed data reuses an invocation identifier; both joined rows are constrained to the requested `run_id`.

### AC5 — reconciliation

For `by_phase`, `by_stage`, `by_role`, and `by_purpose`, the sum of bucket input/output/total tokens equals the corresponding overall total, and the sum of bucket calls equals `llm_calls`. Null phase/stage values are placed in explicit `unassigned` buckets.

### AC6 — unavailable usage

An LLM invocation without a persisted provider usage record contributes no token value, increments `usage_unavailable_calls`, and is never assigned fabricated tokens. A measured persisted zero remains distinguishable from a missing usage row.

### AC7 — execution unchanged

Migration routing, Azure request payloads, LLM role selection, retry decisions, idempotency, repair behavior, approvals, and artifact behavior are unchanged. The only gateway data change is preserving validated provider `total_tokens` in future usage records.

### AC8 — frontend V1

The authoritative LLM dashboard section displays total, input, and output tokens, logical LLM calls, recorded retries, missing-usage notice when applicable, and compact authoritative breakdowns by phase, role, and Angular stage. Purpose is available without an advanced chart.

### AC9 — historical runs

A completed historical run is queryable directly from persisted invocation and usage rows without replaying LLM calls, reading prompt artifacts, or recomputing workflow execution.

### AC10 — no schema change

No new DB schema is introduced. Implementation uses existing `llm_invocations` and `usage_cost_records` fields and indexes.

### AC11 — provider total authority

For future Azure responses, gateway extraction validates and preserves provider `usage.total_tokens`; it does not silently replace the value with `input_tokens + output_tokens`. Existing historical values remain unchanged.

### AC12 — call semantics

Rows with `provider == "deterministic_fallback"` are excluded from LLM call and token groupings. Smoke and Assistant invocations remain included when attached to the run and are visible through authoritative purpose/phase buckets.

### AC13 — backward compatibility

Existing `/usage` fields and estimated cost fields remain available. `invocation_count` retains its current usage-record-count meaning; new consumers use `llm_calls`.

### AC14 — authorization and errors

The existing 403 actor authorization and 404 run-not-found behavior remain unchanged. A usage section failure does not break readiness/activity diagnostics in the UI.

### AC15 — Final Migration Summary boundary

The shared totals object returned by the usage aggregation owner contains exactly `total_tokens`, `input_tokens`, `output_tokens`, and `llm_calls`; Final Migration Summary consumes it and does not independently query or sum LLM usage.

## 19. Exact implementation tasks

### Phase A — provider total authority

#### A1. Preserve Azure `total_tokens`

- **Exact files:** `backend/app/llm_gateway/azure_gateway.py`; `backend/app/llm_gateway/mock_gateway.py`
- **Exact symbols:** `_extract_usage()`, `AzureOpenAILLMGateway.complete()`, `build_usage_record()`
- **Current behavior:** `_extract_usage()` returns only input/output. `build_usage_record()` sets total to input + output.
- **Proposed change:** require a non-negative integer provider `total_tokens` for Azure Responses; return all three values; let `build_usage_record()` accept an optional explicit `total_tokens` and pass the provider value from Azure. Keep the optional default for mock/test callers that intentionally construct usage from input/output.
- **Why required:** makes future persisted `total_tokens` provider-reported as specified, without touching schema or estimates.
- **Dependencies:** none.
- **Verification:** focused gateway tests for exact preservation, invalid/missing total rejection, and unchanged mock construction.
- **Complexity:** S.

### Phase B — one run-scoped aggregation authority

#### B1. Add typed summary/breakdown contracts

- **Exact file:** `backend/app/api/llm_contracts.py`
- **Exact classes:** `LlmUsageResponse`; add `LlmUsageTotals`, `LlmUsageBreakdown`, `LlmUsageRecordResponse`.
- **Current behavior:** overall totals and costs are typed; record dictionaries and breakdowns are not.
- **Proposed change:** add the new count, availability, and breakdown fields while retaining existing fields.
- **Why required:** gives FastAPI/OpenAPI and the frontend a stable contract and creates the four-field integration subset.
- **Dependencies:** agreed formulas in this plan.
- **Verification:** model construction tests and API response validation.
- **Complexity:** S.

#### B2. Extend existing aggregation

- **Exact file:** `backend/app/services/llm_evidence_application_service.py`
- **Exact symbols:** `LlmEvidenceApplicationService.usage()`; add a small module-level/session-scoped aggregation helper and phase-key helper near the service.
- **Current behavior:** queries only `UsageCostRecordModel`, counts usage rows, and returns overall sums.
- **Proposed change:** load same-run invocation rows excluding deterministic fallback, load/join usage once, compute totals/counts, produce deterministic breakdowns, and return the extended response. Keep authorization and not-found handling in `usage()`.
- **Why required:** role, purpose, phase, stage, failed calls, and retry count live on invocation rows.
- **Dependencies:** B1.
- **Verification:** service tests with two runs; completed/failed/in-progress calls; measured zero; missing usage; retries; null phase/stage; deterministic fallback; all reconciliation assertions.
- **Complexity:** M.

#### B3. Reuse totals in Assistant projection

- **Exact file:** `backend/app/services/workflow_projection_service.py`
- **Exact symbol:** `WorkflowProjectionService.build()` operational-statistics block.
- **Current behavior:** independently sums only usage attached to completed invocations.
- **Proposed change:** consume the session-scoped totals from B2 for input/output/total tokens and call count; retain existing Assistant DTO field shapes. Do not add phase/stage UI data to the Assistant contract in this feature.
- **Why required:** removes conflicting totals and establishes the single owner that Final Migration Summary will reuse.
- **Dependencies:** B2.
- **Verification:** projection test showing a persisted usage record reconciles with `/usage`, including provider usage persisted on a non-completed invocation.
- **Complexity:** S.

### Phase C — API projection

#### C1. Keep and verify the existing route

- **Exact file:** `backend/app/api/routes/llm.py`
- **Exact function:** `usage()`
- **Current behavior:** already declares `response_model=LlmUsageResponse`, authenticates, and delegates.
- **Proposed change:** no production logic change expected; update only if a return annotation/import is needed after B1.
- **Why required:** confirms the route remains thin and backward compatible.
- **Dependencies:** B1-B2.
- **Verification:** API contract test at `/api/v1/runs/{run_id}/usage`, plus 403/404 regressions.
- **Complexity:** XS.

### Phase D — frontend types/client

#### D1. Extend frontend usage types

- **Exact file:** `frontend/src/types/llm.ts`
- **Exact types:** `LlmUsageRecord`, `LlmUsageResponse`; add `LlmUsageBreakdown` and `LlmUsageTotals`.
- **Current behavior:** types only current overall totals/cost and records.
- **Proposed change:** mirror the extended backend contract exactly.
- **Why required:** compile-time API/UI agreement.
- **Dependencies:** B1.
- **Verification:** frontend typecheck through the repository's approved focused frontend validation during implementation.
- **Complexity:** XS.

#### D2. Reuse the existing client function

- **Exact file:** `frontend/src/api/llm.ts`
- **Exact function:** `getLlmUsage()`
- **Current behavior:** already calls the correct endpoint with encoded run ID.
- **Proposed change:** no production change expected beyond type imports if needed.
- **Why required:** explicitly prevents a duplicate client or endpoint.
- **Dependencies:** D1.
- **Verification:** existing client test updated for the extended fixture.
- **Complexity:** XS.

### Phase E — frontend usage section

#### E1. Render V1 summary and lists

- **Exact file:** `frontend/src/components/LlmDiagnosticsPanel.tsx`
- **Exact component:** `LlmDiagnosticsPanel`
- **Current behavior:** shows token/cost totals and only the latest invocation's retry count.
- **Proposed change:** add call/retry cards, missing-usage notice, and compact phase/role/stage/purpose lists from the API. Keep the existing readiness, activity, smoke, error, and cost behavior. Remove the usage fallback to the latest invocation for run totals; show unavailable on usage-request failure.
- **Why required:** satisfies the V1 dashboard while keeping one existing component.
- **Dependencies:** D1 and backend response.
- **Verification:** component tests for loading, zero, populated breakdowns, unassigned stage, usage partial failure, retry count, and number formatting.
- **Complexity:** S.

#### E2. Reuse current styling

- **Exact file:** `frontend/src/components/ControlTowerShell.module.css`
- **Exact selectors:** reuse `metricList`, `metadataGrid`, `panel`, `note`; add at most one compact breakdown-list selector only if existing selectors cannot provide readable rows.
- **Current behavior:** existing panel/metric styles support the current diagnostics UI.
- **Proposed change:** preferably none; if needed, add only the smallest accessible row layout.
- **Why required:** avoids a new stylesheet or chart library.
- **Dependencies:** E1.
- **Verification:** component DOM assertions and browser/manual inspection during implementation.
- **Complexity:** XS.

### Phase F — focused verification

#### F1. Backend gateway and aggregation tests

- **Exact files:** `backend/tests/test_llm_gateway.py`, `backend/tests/test_llm_evidence_s2_f03.py`, `backend/tests/test_llm_verification_s2_f03.py`, `backend/tests/test_assistant_r5_workflow_projection.py`
- **Exact coverage:** provider total preservation; run isolation; logical calls; recorded retries; failed call with/without usage; measured zero; deterministic fallback exclusion; all grouping reconciliation; API compatibility; shared projection totals.
- **Current behavior:** tests cover basic totals, cost, endpoint shape, retries, and zero-vs-unavailable in Assistant projection, but not the V1 aggregate.
- **Proposed change:** extend focused tests; do not add a new broad suite.
- **Why required:** proves formulas and regression boundaries.
- **Dependencies:** A-E.
- **Verification method:** run only the named focused tests first during implementation; broader suites only if repository policy or failures require them.
- **Complexity:** M.

#### F2. Frontend tests

- **Exact files:** `frontend/src/api/__tests__/llm.test.ts`, `frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx`, and only if the section boundary changes, `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`.
- **Current behavior:** tests cover current usage/cost and partial diagnostics errors.
- **Proposed change:** extend fixtures and assertions for V1 cards/lists and unavailable-vs-zero behavior.
- **Why required:** proves the UI is driven by the API contract and remains resilient.
- **Dependencies:** D-E.
- **Verification method:** run only named tests and the approved frontend typecheck during implementation.
- **Complexity:** S.

## 20. Exact files to modify/create

### Files to modify

Required:

- `backend/app/llm_gateway/azure_gateway.py`
- `backend/app/llm_gateway/mock_gateway.py`
- `backend/app/api/llm_contracts.py`
- `backend/app/services/llm_evidence_application_service.py`
- `backend/app/services/workflow_projection_service.py`
- `frontend/src/types/llm.ts`
- `frontend/src/components/LlmDiagnosticsPanel.tsx`
- `backend/tests/test_llm_gateway.py`
- `backend/tests/test_llm_evidence_s2_f03.py`
- `backend/tests/test_llm_verification_s2_f03.py`
- `backend/tests/test_assistant_r5_workflow_projection.py`
- `frontend/src/api/__tests__/llm.test.ts`
- `frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx`

Conditional only if required by compile/style verification:

- `backend/app/api/routes/llm.py`
- `frontend/src/api/llm.ts`
- `frontend/src/components/ControlTowerShell.module.css`
- `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`

### Files to create

- Production implementation: **none**.
- Tests: **none expected**; extend focused existing tests.
- This planning task created only `docs/plans/2026-08-09-llm-usage-token-consumption-v1.md`.

### Files to read only during implementation

- `backend/app/llm_gateway/contracts.py` unless an import/type adjustment becomes necessary.
- `backend/app/repositories/models/workflow.py`
- `backend/app/repositories/models/__init__.py`
- Analysis, Planning, Assistant, prompt-explanation, and repair caller services listed in section 5.
- `backend/app/api/router.py`
- `frontend/src/components/AuthoritativeRunDashboard.tsx`
- `frontend/src/components/control-tower/ControlTowerSidebar.tsx`
- `frontend/src/components/LlmUsagePanel.tsx`
- `frontend/src/types/generated/api.ts`

### Files that must not change

- Any Alembic migration or DB schema file.
- `backend/app/repositories/models/workflow.py` for this V1.
- Migration/repair execution routing and retry policy.
- Analysis, Planning, repair, Assistant, and prompt-explanation production callers, unless a separate persistence-correctness task is approved after measuring missing usage.
- `frontend/src/components/LlmUsagePanel.tsx` and the legacy/mock dashboard path.
- Final Migration Summary-owned UI/service files.
- Migration Timing-owned files.
- Pricing settings or a cost engine.

## 21. Verification plan

No verification commands were run during this planning-only audit. During implementation, use this dependency order:

1. Gateway focused tests:
   - provider `total_tokens` is preserved even if it differs from input + output;
   - missing/invalid usage values fail closed;
   - existing retry behavior is unchanged.
2. Service aggregation tests using an isolated test DB:
   - multiple roles/purposes/phases/stages;
   - second run with large values proving isolation;
   - one failed invocation with usage;
   - one failed invocation without usage;
   - one measured zero usage row;
   - one deterministic fallback row;
   - one invocation with retries;
   - all overall/breakdown reconciliation.
3. API tests:
   - existing fields remain;
   - new typed fields serialize;
   - 403 and 404 behavior remains;
   - historical completed rows need no recomputation.
4. Assistant projection focused test:
   - shared overall totals match the usage service.
5. Frontend API test:
   - client uses the existing endpoint and accepts the extended contract.
6. Frontend component tests:
   - loading;
   - actual zero;
   - populated totals and lists;
   - missing-usage warning;
   - usage API failure does not become zero and does not hide readiness/activity;
   - no advanced chart dependency.
7. Approved frontend typecheck and focused manual browser check.
8. Read-only final review, `git diff --check`, `git status --short`, and `git diff --stat`.

Do not run migrations for this feature because no migration exists.

## 22. Risks/regression boundaries

### Risk 1 — incomplete historical provider usage

Some failed or pre-success retry attempts consumed provider resources without a persisted usage row. V1 cannot recover those values safely. Mitigation: report `usage_unavailable_calls`, sum only persisted records, and state that totals are authoritative persisted usage rather than an Azure invoice.

### Risk 2 — retry semantic ambiguity

Transport retries, semantic repeats, and legacy repair seeding do not have one uniform representation. Mitigation: expose raw persisted `retry_calls`, count logical invocation rows separately, do not calculate provider calls, and label retries as recorded.

### Risk 3 — duplicate aggregation authorities

`/usage`, Assistant workflow projection, and a future Final Migration Summary could disagree. Mitigation: one session-scoped aggregation helper owned by this feature; all consumers reuse its four totals.

### Risk 4 — backward API compatibility

Changing `invocation_count` meaning could break diagnostics/tests. Mitigation: retain its existing usage-record-count meaning and add `llm_calls` with explicit semantics.

### Risk 5 — unavailable displayed as zero

The current UI falls back from run usage to the latest invocation and then zero. Mitigation: distinguish request failure/missing usage from a successful measured zero response.

### Regression boundaries

- Do not change provider selection, prompt/schema selection, response parsing beyond usage totals, retry loops, budgets, or execution state transitions.
- Do not write aggregation results back to DB.
- Do not modify immutable artifacts for historical runs.
- Do not join or aggregate the legacy `llm_usage_records` table.
- Do not derive role/purpose from prompts.
- Do not derive Angular stage from file paths or event timing.
- Do not let usage aggregation affect run status or completion.

## 23. Parallel-feature integration contract

This feature owns the only LLM usage aggregation. Migration Timing owns time; Final Migration Summary owns the final summary composition and presentation.

Reusable output:

```json
{
  "total_tokens": 138870,
  "input_tokens": 120450,
  "output_tokens": 18420,
  "llm_calls": 24
}
```

Rules:

- The four values come from the same run-scoped aggregate used by `/usage`.
- Final Migration Summary consumes the typed `LlmUsageTotals` result in-process; it does not sum `usage_cost_records`, invocation DTOs, artifacts, or frontend values.
- Missing usage affects token completeness but not `llm_calls`; Final Migration Summary may separately show the usage availability warning supplied by this feature if desired.
- Migration Timing does not add time fields to the usage contract.
- This feature does not modify Final Migration Summary or Timing files.

## 24. Web references

Accessed 2026-08-09. Official sources only.

1. [Microsoft Foundry REST Reference — Azure OpenAI Responses](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/responses)
   - Fact relied on: a Responses object can carry `OpenAI.ResponseUsage`; it contains `input_tokens`, `output_tokens`, `total_tokens`, and input/output token detail structures. The response-level `usage` member is optional, so missing usage must be represented as unavailable rather than invented.
2. [Microsoft Foundry — Use the Azure OpenAI Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses)
   - Fact relied on: official examples return `usage.input_tokens`, `usage.output_tokens`, `usage.output_tokens_details.reasoning_tokens`, and `usage.total_tokens` on a completed response.
3. [OpenAI API Reference — Responses object](https://platform.openai.com/docs/api-reference/responses/object)
   - Fact relied on: the upstream Responses contract uses the same three top-level usage totals and token-detail objects. Azure documentation is sufficient for the implementation; this source is corroboration, not a reason to add fields.
4. [FastAPI — Response Model / Return Type](https://fastapi.tiangolo.com/tutorial/response-model/)
   - Fact relied on: `response_model` validates, documents, serializes, and filters output to the declared Pydantic shape. The existing typed route should be extended rather than returning new untyped dictionaries.

## 25. Complexity estimate

Overall: **M**.

- Provider total preservation: S.
- Typed contracts and aggregation: M.
- Shared projection reuse: S.
- Frontend types and cards/lists: S.
- Focused backend/frontend verification: M.

Expected production change is concentrated in five required files plus one existing dashboard component and one frontend type file. No schema, migration, new service file, dependency, or chart is required.

## 26. Recommended implementation order

1. Lock the exact semantics and compatibility fields from sections 13-14.
2. Preserve provider `total_tokens` at the gateway and prove it with focused tests.
3. Add typed backend response/breakdown contracts.
4. Extend the existing usage aggregation with the same-run join, counts, availability, and deterministic groups.
5. Prove totals, retry/count semantics, run isolation, unavailable usage, and reconciliation in service/API tests.
6. Make `WorkflowProjectionService` reuse the shared totals; publish the four-field contract to the Final Migration Summary owner.
7. Extend frontend types; keep `getLlmUsage()` unchanged.
8. Extend `LlmDiagnosticsPanel` using existing layout primitives.
9. Run focused frontend tests/typecheck and the smallest manual UI check.
10. Perform final read-only diff/review checks and confirm no schema, runtime, or unrelated feature files changed.

This ordering keeps each layer dependent only on the layer below it and stops at the first existing abstraction that already holds.
