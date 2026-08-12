# Transformer E2E Implementation Handoff

Authoritative implementation and runtime handoff for the Angular Migration Factory Transformer.

**Audit date:** 2026-08-09  
**Repository:** C:\Users\abdelilah.mortaki\Desktop\angular-migration  
**Expected branch:** backup/fix-transformer-repair-llm-wiring  
**Marker commit:** 36f8cb8a03bffcea463870f2dc074a0753ad1ff1  
**Primary proof run:** run-80ee6328670b  
**Operating mode:** read-only architecture/runtime audit followed by this one documentation write

## 0. Operating mode and evidence labels

This is an evidence-backed description of the current implementation. It is not a design proposal, changelog, migration replay, or production-readiness certification.

The audit inspected repository instructions, source, persisted SQLite state, immutable run artifacts, workspace paths, and workflow events. No backend, frontend, worker, migration, npm, build, test, or pytest process was started. The database was opened with SQLite read-only mode and query-only mode. The only intended write is this Markdown file.

Every material statement is tagged using one of these labels:

| Label | Meaning |
|---|---|
| SOURCE CODE | Current implementation or current repository instruction. |
| DATABASE | Read-only row, schema, count, or integrity result from the authoritative run database. |
| IMMUTABLE ARTIFACT | Finalized run artifact and its recorded checksum/metadata. |
| WORKSPACE | Read-only filesystem observation in the run root, sandbox, or sealed output. |
| WORKFLOW EVENT | Append-only event sequence persisted for the run. |
| INFERENCE | A conclusion derived by correlating two or more evidence types; the premises are named. |

When current source, database projection, and runtime output disagree, the disagreement is retained below rather than silently normalized.

## 1. Authoritative runtime discovery

### 1.1 Repository authority

| Item | Value | Source |
|---|---|---|
| Repository root | C:\Users\abdelilah.mortaki\Desktop\angular-migration | WORKSPACE |
| Branch | backup/fix-transformer-repair-llm-wiring | WORKSPACE |
| HEAD | 36f8cb8a03bffcea463870f2dc074a0753ad1ff1 | WORKSPACE |
| Marker | test(e2e): Angular 18-21 migration proven on two completed runs | WORKSPACE |
| Initial status | clean before this handoff was created | WORKSPACE |
| Repository rules | AGENT.md | SOURCE CODE |

AGENT.md establishes the important trust boundary: frontend projects the backend; SQLite plus StateTransitionService are durable truth; LangGraph coordinates; only CommandExecutor owns subprocess execution; artifacts are immutable; repairs are proposer-authored and reviewer/human-governed; external source is read-only; gates fail closed; commands are registry-defined and shell-disabled; state mutations require expected state versions, idempotency, and checksums.

### 1.2 Run authority

| Item | Value | Source |
|---|---|---|
| Run ID | run-80ee6328670b | DATABASE / IMMUTABLE ARTIFACT |
| Run root | C:\a\angular-crud-poc-angular-21-ea7cf8a66521\.migration-factory\runs\run-80ee6328670b | DATABASE / WORKSPACE |
| Source | C:\Users\abdelilah.mortaki\Desktop\angular-crud-poc | DATABASE / IMMUTABLE ARTIFACT |
| Target parent | C:\a | DATABASE / IMMUTABLE ARTIFACT |
| Generated output name | angular-crud-poc-angular-21-ea7cf8a66521 | DATABASE |
| Source snapshot | snapshot-955d71c32b7d | DATABASE / IMMUTABLE ARTIFACT |
| Source snapshot fingerprint | sha256:42b3d2a0...dc2dc26e | IMMUTABLE ARTIFACT |
| Runtime profile | environment-environment-d4fa9a9993e5 | DATABASE / IMMUTABLE ARTIFACT |
| Runtime profile checksum | sha256:4b672d4ede25f7aa0400eb2d5bd68ce11ba0ebf732f5c9a78623b1fe5342cf7c | IMMUTABLE ARTIFACT |

The run root contains the external layout recorded by output_layout.json: artifacts, baseline-sandbox, logs, reports, source-snapshot, stage-sandboxes, and temporary. The recorded aliases additionally name DELIVERY_CANDIDATE and MIGRATED_APP. The run root itself has no ordinary delivery payload at its top level.

### 1.3 How the database path was derived

The authoritative database was not inferred from the repository .env. Startup provenance was traced through run-fresh-backend.ps1 and scripts/dev-backend.ps1 to the configured application data root and database_path(get_settings().database_url). The fresh proof startup created a run-specific local data root during the run window:

    C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260809-012824\control-tower.db

The corresponding .db-shm and .db-wal sidecars were also present. The repository backend .env instead points to the older default root:

    C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower\control-tower.db

That older path is not the authoritative database for run-80ee6328670b. This distinction matters because reading the current .env target would produce a stale or different run view.

The authoritative database was opened using the backend virtual-environment Python with a SQLite URI containing mode=ro, followed by PRAGMA query_only=ON. No INSERT, UPDATE, DELETE, DDL, migration, checkpoint, WAL, or artifact write was performed.

## 2. Database schema and durable relationships

The database has 70 non-system tables. The Transformer is a durable SQL workflow with LangGraph as a dispatcher, not an in-memory graph whose state can be reconstructed from the frontend.

### 2.1 Core run and plan tables

| Table | Purpose and lifecycle | Key/relationships | Critical fields and observed values | Writer/consumer | Source |
|---|---|---|---|---|---|
| migration_runs | Run identity, policy, phase projection, output layout, and top-level lifecycle. | PK id; referenced by most run tables. | status, run_phase, state_version, source/target families, source_path, run_root, artifact_root, output paths, graph_thread_id, policy JSON, workspace_aliases. | Run services and StateTransitionService write; all projections read. | SOURCE CODE / DATABASE |
| migration_plans | Approved route-level plan. | PK id; FK run_id. | idempotency_key, request_checksum, version, plan JSON, checksum, artifact ids/checksums, state_version, event_sequence, status. | Planning/gate services write; continuation binds to it. | SOURCE CODE / DATABASE |
| migration_stages | One source-to-target hop. | PK id; FK run_id; stage_order unique per run. | source/target families and versions, status, current_agent, timestamps. | Stage planning/sealing write; worker/projection read. | SOURCE CODE / DATABASE |
| transformation_continuations | Durable worker cursor and lease state. | PK id; FK run_id/current_stage_id/g06_approval_id/plan ids/waiting_execution_id. | thread_id, status, current_node, worker/lease fields, wake_sequence, state_version, attempt/max_attempts, last_error, cancellation fields. | TransformationContinuationService writes using CAS; worker and API read. | SOURCE CODE / DATABASE |
| stage_execution_plans | Frozen per-stage plan. | PK id; FK run, migration_plan, migration_stage. | stage_plan JSON, checksum, version, request/idempotency, artifacts, state_version/event sequence. | Stage planning/gates write; stage services bind to it. | SOURCE CODE / DATABASE |
| stage_steps | Logical step projection and attempt lineage. | PK id; FK run/stage; execution_id references command execution. | name, status, component_type, attempt_id, idempotency_key, input/output checksums, workspace_fingerprint, artifact ids, state_version. | Stage services write; validation and projection read. | SOURCE CODE / DATABASE |
| workflow_events | Append-only audit/event stream. | PK id; FK run/stage; run sequence in payload/sequence field. | event_type, idempotency_key, actor, reason, sequence, payload JSON, occurred_at. | StateTransitionService and workflow services append; SSE/API read. | SOURCE CODE / DATABASE |
| run_event_sequences | Per-run event sequence allocator. | PK/FK run_id. | last_sequence. | StateTransitionService writes transactionally. | SOURCE CODE / DATABASE |

### 2.2 Workspace, checkpoint, gate, and prompt tables

| Table | Purpose and critical fields | Relationships and workflow role | Source |
|---|---|---|---|
| stage_workspace_bindings | Binds a stage alias to a confined path and input/output fingerprints. | FK run/stage/source_checkpoint; active binding is the current mutable workspace identity. | SOURCE CODE / DATABASE |
| stage_checkpoints | Safe restore/resume point plus seal lineage. | FK run/stage/source_checkpoint; created_from_execution_id is intended to FK command_executions. Stores manifest artifact/checksum, workspace alias/path/fingerprint, safe_for_resume, sealed, state_version. | SOURCE CODE / DATABASE |
| stage_gate_packages | Immutable package presented for a gate decision. | FK run/stage/plan/stage plan; binds package checksum, artifact-set checksum, expected state version, workspace fingerprint, and stale_at. | SOURCE CODE / DATABASE |
| stage_gate_decisions | Human or operator decision over a gate package. | FK gate package/run/stage; stores decision, actor, comment, request/idempotency checksum, package/workspace binding, expected state version, reason_code, accepted. | SOURCE CODE / DATABASE |
| stage_prompt_requests | Durable prompt/decision boundary for detected ambiguity. | FK run/stage/execution/checkpoint/attempt; stores normalized prompt/options/context artifacts, fingerprints, status, selected option and reconstruction checkpoint. | SOURCE CODE / DATABASE |
| approval_gates | Route-level gate record; G01 was approved in this run. | Run-level approval policy record. | DATABASE |
| g02_approvals, g03_approvals, g04_approvals, g05_approvals, g06_approvals, g06_decisions | Planning and intake approvals/decisions. | Run foreign keys and package/checksum bindings as defined by each model. | DATABASE |

### 2.3 Command, repair, LLM, and evidence tables

| Table | Purpose and critical fields | Observed count/role | Source |
|---|---|---|---|
| command_authorization_audits | Immutable permission decision before queueing. | 41 rows; all accepted under s3-f01-v1. Stores command/template/version, literal args, reasons, actor, policy, request hash, expected state, runtime/workspace/network bindings. | DATABASE / SOURCE CODE |
| command_executions | Durable command intent, claim, process result, and lineage. | 49 rows; statuses include succeeded and failed. Stores executable/args, alias, runtime profile, shell, timeout, stdout/stderr/log artifacts, exit/failure, fingerprints, state/event versions, authorization/template/plan links, parent_execution_id and attempt_number. | DATABASE / SOURCE CODE |
| command_log_chunks | Append-only bounded stdout/stderr chunks. | 75 rows. | DATABASE |
| command_log_summaries | Final log rollup. | 45 rows; finalized/truncated/redaction and byte counts. | DATABASE / SOURCE CODE |
| repair_attempts | Repair lifecycle, lineage, proposal/review/apply/validation evidence, and budget identity. | 7 rows. Stores stage/checkpoint/failure fingerprint, diagnosis/route, attempt number/status, artifact IDs/checksums, proposer/reviewer invocations, parent revision, pre/post fingerprints, validation targets, state version. | DATABASE / SOURCE CODE |
| llm_invocations | Provider-neutral durable LLM invocation and diagnostics. | 18 completed rows: 2 planning/analysis roles and 14 repair proposer/reviewer roles. | DATABASE / SOURCE CODE |
| usage_cost_records | Usage/cost ledger for LLM invocations. | 18 rows; 160,060 input, 28,424 output, 188,484 total tokens, recorded cost 0.0 under the run pricing snapshot. | DATABASE |
| artifact_metadata | Immutable artifact catalog. | 499 rows; all marked immutable; 0 missing files, 0 checksum mismatches, 0 missing sidecars in the read-only verifier. | DATABASE / WORKSPACE |
| execution_profiles | Selected runtime and environment policy. | 1 row; binds Node/npm/npx paths, allowlist, network/cache profile, and checksum. | DATABASE |
| environment_capability_snapshots | Environment capability capture. | 1 row; no run FK by schema, but referenced by runtime evidence. | DATABASE |
| compatibility_catalogues | Version support catalogue. | 1 row. | DATABASE |
| compatibility_registry_snapshots | Run-bound catalogue/registry snapshot. | 1 row, registry-run-80ee6328670b-14b9d909d408. | DATABASE |
| compatibility_resolutions | Resolved source/target compatibility route and selected profile. | 1 row; binds catalogue/registry checksums, runtime candidate, route, blockers/warnings, artifacts, workspace and plan. | DATABASE |
| stage_reconstruction_records | Durable restore events after interrupted/mutating command paths. | 4 rows, all with pre/post fingerprints. | DATABASE |
| run_assurance_statuses | Optional assurance projection table. | 0 rows in this run; absence is a known projection/debt signal, not proof that validation did not occur. | DATABASE / INFERENCE |

### 2.4 Compact ER-style model

~~~mermaid
erDiagram
    migration_runs ||--o{ migration_stages : contains
    migration_runs ||--o{ workflow_events : emits
    migration_runs ||--o{ command_executions : owns
    migration_runs ||--o{ repair_attempts : records
    migration_stages ||--o{ stage_steps : has
    migration_stages ||--o{ stage_checkpoints : creates
    migration_stages ||--o{ stage_workspace_bindings : binds
    migration_stages ||--o{ stage_gate_packages : packages
    stage_gate_packages ||--o{ stage_gate_decisions : decides
    stage_checkpoints ||--o{ stage_reconstruction_records : restores
    stage_checkpoints ||--o{ repair_attempts : anchors
    command_executions ||--o{ command_log_chunks : logs
    command_executions ||--o| command_log_summaries : summarizes
    command_executions ||--o{ command_authorization_audits : authorized_by
    repair_attempts ||--o{ llm_invocations : proposes_or_reviews
    migration_runs ||--o{ artifact_metadata : catalogs
    migration_runs ||--o{ transformation_continuations : drives
    migration_stages ||--o{ transformation_continuations : resumes
~~~

The foreign-key relationship shown for stage_checkpoints.created_from_execution_id is conceptually correct but not clean in the authoritative database: six rows contain a sha256 fingerprint in that FK column instead of a command execution ID. See section 33.

## 3. Production implementation file map

The following map is based on current files and symbols, not old documentation.

### 3.1 Orchestration and stage execution

| File / symbol | Responsibility | Inputs, outputs, mutations, collaborators | Source |
|---|---|---|---|
| backend/app/orchestration/transformer_worker.py — TransformerWorker | Polling/claiming driver. | Claims a command first, otherwise claims a continuation; invokes CommandExecutorService or TransformerOrchestrator; wakes waiters; reconciles expired executions/stuck waiters; run_forever is polling. | SOURCE CODE |
| backend/app/orchestration/transformer_graph.py — TransformerOrchestrator / TransformerWorkflow | Durable node dispatch. | Reads continuation.current_node and SQL state, dispatches deterministic services, returns a next-node/status decision; LangGraph has a single advance node and END, while SQL is durable state. | SOURCE CODE |
| backend/app/orchestration/transformer_sealing_flow.py — TransformerSealingFlow | Route sealing and completion. | Verifies every route stage, required gates, no active work, then records STAGED_MIGRATION_COMPLETED and completes the continuation/run. | SOURCE CODE |
| backend/app/services/transformer_stage_service.py | Stage lifecycle and stage-step orchestration. | Prepares/binds stage workspaces, creates steps/checkpoints, coordinates stage plan and deterministic services. | SOURCE CODE |
| backend/app/services/stage_execution_application_service.py | Application boundary for stage execution commands. | Binds request checksums, stage plans, command policy, and state versions before persistence. | SOURCE CODE |
| backend/app/services/validation_runner.py — ValidationRunner | Validation target execution and aggregation inputs. | Executes final install/build/test/lint targets through CommandExecutor and records step/execution/artifact bindings; failures route to classification. | SOURCE CODE |
| backend/app/services/lockfile_generation_runner.py — LockfileGenerationRunner | Controlled package-lock generation. | Pre-proves package/workspace checksums, executes package-lock-only install, writes lockfile verification, uses CAS and successor logic. | SOURCE CODE |
| backend/app/services/dependency_transition_runner.py — DependencyTransitionRunner | Durable detach/update/reinstall closure. | Phase machine keyed to repair attempt: uninstall, Angular update, normalize lockfile, reinstall, npm ci, closure verification. | SOURCE CODE |

### 3.2 Repair and deterministic policy

| File / symbol | Responsibility | Source |
|---|---|---|
| backend/app/services/repair_application_service.py — RepairApplicationService | Validates and applies typed operations: replace_text, create_text_file, delete_text_file, dependency_change, dependency_add, dependency_transition. It is the only proposer-candidate application boundary. | SOURCE CODE |
| backend/app/services/repair_lifecycle_service.py | Reconciles repair rows with later evidence and decides whether historical work is active, superseded, passed, or blocking. | SOURCE CODE |
| backend/app/services/causal_review.py | Applies causal/semantic policy to proposed repair routes and rejects unsupported commands or force-oriented reasoning. | SOURCE CODE |
| backend/app/services/dependency_addition_policy.py — DependencyAdditionPolicy | Validates package-name grammar, dependencies/devDependencies section, registry semver intent, and rejects URL/git/file/workspace/npm-alias/dist-tag forms. | SOURCE CODE |
| backend/app/services/dependency_closure_service.py | Verifies manifest, lockfile, and installed dependency closure; contains the intentional static compatible reinstall bundles for transitions. | SOURCE CODE |
| backend/app/services/failure_evidence_service.py | Normalizes command failure evidence, fingerprints it, and records route context/artifacts. | SOURCE CODE |
| backend/app/services/patch_apply_service.py — PatchApplyService | Applies bounded preimage-checked text operations and verifies postimage; it does not accept arbitrary free-form file writes. | SOURCE CODE |

### 3.3 Governance, execution, artifacts, and LLM

| File / symbol | Responsibility | Source |
|---|---|---|
| backend/app/services/stage_gate_service.py — StageGateService | Creates immutable gate packages and applies idempotent, stale-protected decisions; maps accepted gates to next nodes. | SOURCE CODE |
| backend/app/services/command_registry_service.py — CommandRegistryService / CommandPolicyEngineService | Resolves the 18 registry templates, validates executable aliases, token/literal args, plan membership, runtime, alias, network, timeout, shell, and idempotency bindings. | SOURCE CODE / DATABASE |
| backend/app/services/command_executor_service.py — CommandExecutorService | Persists/claims authorized commands, handles bounded retry/recovery, and wakes continuations. It closes the DB session before process execution. | SOURCE CODE |
| backend/app/command_execution/worker.py — ExecutionWorker | The only Transformer subprocess worker path; uses subprocess.Popen with shell=False, bounded logs, redaction, timeout/cancellation, and process-tree termination. | SOURCE CODE |
| backend/app/services/migration_workspace_layout_service.py | Derives external output layout and confines aliases/path roots. | SOURCE CODE |
| backend/app/artifact_store/local_store.py — LocalFilesystemArtifactStore | Writes finalized immutable content plus metadata sidecar, SHA-256, safe relative path, and atomic replacement. | SOURCE CODE |
| backend/app/llm_gateway/azure_gateway.py / contracts.py / redaction.py | Governed Azure OpenAI transport, structured response contract, provider diagnostics, bounded response, and redaction. | SOURCE CODE |
| backend/app/services/transformer_prompt_service.py | Prompt registry and role/task routing for proposer/reviewer prompts, context binding, and semantic retries. | SOURCE CODE |

### 3.4 Persistence, API, frontend, and configuration

| File / symbol | Responsibility | Source |
|---|---|---|
| backend/app/repositories/models/workflow.py | SQLAlchemy workflow models for run, stages, continuation, checkpoints, gates, commands, repairs, LLM, and artifacts. | SOURCE CODE |
| backend/app/state/transition_service.py — StateTransitionService | CAS-guarded state mutation plus transactional workflow event/idempotency append. | SOURCE CODE |
| backend/app/api/routes/transformation.py — _projection | Authoritative transformation projection assembled from continuation, stage, checkpoint, binding, command, repair, gate, and evidence rows. | SOURCE CODE |
| backend/app/api/routes/runs.py | Run creation/start/cancel/state/event stream and source-intake controls. | SOURCE CODE |
| backend/app/api/routes/run_commands.py | Durable command submission, status, logs, SSE stream, cancellation, active command/lease views. | SOURCE CODE |
| frontend/src/api/transformation.ts | Typed transformation projection and human-decision calls. | SOURCE CODE |
| frontend/src/hooks/useTransformation.ts | Refreshes projection and commands; preserves last authoritative projection on refresh failure. | SOURCE CODE |
| frontend/src/types/transformation.ts | Projection contract including gate, repair, dependency, validation, runtime, seal, and historical diagnostics. | SOURCE CODE |
| frontend/src/components/TransformationPanel.tsx / TransformationSections.tsx | Renders backend truth and human actions; enforces UI-side stale/error handling without becoming authority. | SOURCE CODE |
| backend/app/core/config.py / database.py | Data-root/database defaults, external output roots, runtime limits, WAL/busy timeout, schema compatibility. | SOURCE CODE |

## 4. Complete Transformer architecture

The current ownership chain is:

~~~mermaid
flowchart LR
    F[Frontend projection and human decisions] --> A[FastAPI API]
    A --> D[(SQLite durable state)]
    D --> W[Transformer worker]
    W --> G[LangGraph durable node dispatcher]
    G --> S[Deterministic stage and policy services]
    S --> Q[Command authorization]
    Q --> E[CommandExecutor]
    E --> X[Isolated stage workspace]
    X --> R[Immutable artifacts]
    R --> V[Validation and gates]
    V --> Z[Seal checkpoint and continuation]
    Z --> D
~~~

Ownership is explicit:

| Owner | Owns | Does not own | Source |
|---|---|---|---|
| Frontend | Projection rendering and human decisions. | Durable state, command permission, repair truth, or version truth. | SOURCE CODE |
| SQLite/state services | Durable state, CAS, event sequence, idempotency, leases, and lineage. | Process execution or UI interpretation. | SOURCE CODE |
| LangGraph | Node dispatch/coordinator shape. | The authoritative workflow state. | SOURCE CODE |
| TransformerWorker | Continuation/command claim and progress driving. | Arbitrary subprocess invocation. | SOURCE CODE |
| Deterministic services | Policy, binding, exact command rendering, validation, fingerprints, repair application, sealing. | LLM judgment or human approval. | SOURCE CODE |
| Repair proposer LLM | Typed candidate repair intent and explanation. | Direct filesystem, command, lockfile, gate, or completion authority. | SOURCE CODE |
| Reviewer LLM | Independent accept/request_changes/reject critique and limitations. | Authoring or applying a candidate. | SOURCE CODE |
| Human/operator | G02-G06/G10/G11 decisions where the policy requires them. | Bypassing checksums, state versions, or command policy. | SOURCE CODE |
| CommandExecutor/ExecutionWorker | Authorized subprocess lifecycle and logs. | Choosing unapproved commands. | SOURCE CODE |
| Artifact store | Immutable evidence materialization and catalog. | Mutable workspace state. | SOURCE CODE |
| Stage workspace | Mutable per-stage execution state. | Source authority or final publication authority. | SOURCE CODE |

## 5. Full continuation state machine

The domain enum TransformationNode contains the current node vocabulary, including stage_workspace_ready, baseline_install, validate_g06, prepare_workspace, resolve_runtime, dependency_preflight, collect_known_decisions, create_g07, wait_g07, bootstrap_install, verify_bootstrap, angular_update, handle_prompt, wait_prompt_decision, target_inspection, version_verify, transformation_evidence, create_g08, wait_g08, final_install, build, test, aggregate_validation, create_g09, wait_g09, classify_failure, propose_repair, review_repair, create_g10, wait_g10, approved_pending_execution, apply_repair, verify_repair, retry_migration, dependency_transition, angular_update_retry, repair_revalidate, create_g11, wait_g11, create_g12, wait_g12, seal_stage, materialize_next_stage, complete_run, stage_completed, blocked, cancel, and terminal. TransformationStatus separately includes queued, running, waiting_command, waiting_gate, waiting_prompt, waiting_retry, waiting_repair_revision, cancelling, cancelled, blocked, failed, and completed.

~~~mermaid
flowchart TD
    A[stage_workspace_ready] --> B[prepare_workspace]
    B --> C[create_g07 / wait_g07]
    C --> D[bootstrap_install]
    D --> E[angular_update]
    E --> F{peer or command failure}
    F -- no --> G[version_verify]
    F -- yes --> H[classify_failure]
    H --> I{repairable route}
    I -- no --> T[blocked or terminal]
    I -- yes --> J[propose_repair]
    J --> K[review_repair]
    K --> L{review decision}
    L -- request_changes --> J2[child revision attempt]
    J2 --> J
    L -- reject --> T
    L -- accept --> M[create_g10 / wait_g10]
    M --> N{human decision}
    N -- request changes --> J2
    N -- reject --> T
    N -- approve --> O[apply_repair]
    O --> P{dependency operation}
    P -- transition --> Q[dependency_transition]
    P -- add or change --> R[lockfile_generation]
    P -- text --> S[verify_repair]
    Q --> R
    R --> U[repair final_install npm ci]
    S --> U
    U --> V[affected validation]
    V --> W[full validation replay]
    W --> X{pass}
    X -- no progress or failure --> H
    X -- yes --> G
    G --> Y[create_g08 / wait_g08]
    Y --> Z[final_install]
    Z --> AA[build and test]
    AA --> AB[aggregate_validation]
    AB --> AC[create_g11 / wait_g11]
    AC --> AD[seal_stage]
    AD --> AE{next stage}
    AE -- yes --> AF[materialize_next_stage]
    AF --> A
    AE -- no --> AG[complete_run]
    AG --> AH[terminal]
    R -. restart recovery .-> AR[checkpoint restore and successor]
    D -. timeout or stale execution .-> AR
    AR --> H
~~~

Node contract summary:

| Node group | Entry precondition | Durable state/artifacts | Exit condition and next node | Source |
|---|---|---|---|---|
| Workspace/bootstrap | Binding exists, input fingerprint matches, G07 approved. | Stage binding, checkpoint, command authorization/execution, logs, bootstrap result. | npm ci succeeds -> Angular update; command failure -> normalized failure. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Angular update/version | Bootstrap complete and command policy permits the stage template. | Update command lineage, package/lock artifacts, version evidence. | Success -> version verify; peer conflict -> dependency transition/repair. | SOURCE CODE / WORKFLOW EVENT |
| Dependency transition | Failure route identifies a compatible peer blocker and approved repair. | Durable phase rows, uninstall/update/reinstall/lockfile/npm ci executions, closure evidence. | Closure agrees -> validation; ERESOLVE/failure -> classify. | SOURCE CODE / DATABASE |
| Dependency add/change | G10-approved manifest intent and proposal bindings. | Apply evidence, package.json checksum, lockfile verification, npm ci, closure/validation evidence. | Materialized -> affected then full validation. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Text repair | One typed preimage-checked operation and approved G10. | Candidate diff, apply-prepared/applied, pre/post fingerprints. | Postimage matches -> affected/full validation. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Validation | Required install/build/test targets are bound to the stage and attempt. | Command results, validation summary, target set, workspace fingerprint. | Pass -> G11; failure/no progress -> classify. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Gates | Gate package binds evidence, plan, expected state, and workspace. | Package and decision rows/artifacts. | G07 -> bootstrap, G08 -> final validation, G10 -> apply, G11 -> seal. | SOURCE CODE / DATABASE |
| Seal/complete | All required evidence and approvals exist; no active work. | Seal checkpoint, output-manifest.json, seal.json, chain hash. | More route stages -> next-stage materialization; otherwise STAGED_MIGRATION_COMPLETED -> COMPLETED -> terminal. | SOURCE CODE / WORKFLOW EVENT |
| Recovery | Expired/failed command or stale waiter is found. | Reconstruction record, restored checkpoint, successor command/step, no historical command deletion. | Reconciled -> retry/classify/continue. | SOURCE CODE / DATABASE |

The implementation also has explicit terminal paths for cancellation, blocked policy, exhausted budget, reviewer rejection, human rejection, no-progress fingerprints, and stale state/checksum conflicts.

## 6. Angular 18 -> 21 route proven by the latest run

### 6.1 Shared runtime and route facts

| Field | Value | Source |
|---|---|---|
| Node | v22.23.1 at C:\nvm4w\nodejs\node.exe | IMMUTABLE ARTIFACT / DATABASE |
| npm | 10.9.8 | IMMUTABLE ARTIFACT / DATABASE |
| npx | 10.9.8 | IMMUTABLE ARTIFACT / DATABASE |
| Angular CLI execution | npx; angular_cli_exact was null in the profile | IMMUTABLE ARTIFACT |
| Network | approved-registries-only; approved cache; certificate validated; no configured proxy | IMMUTABLE ARTIFACT |
| Source snapshot | 120 files, 2,309,541 bytes, snapshot-955d71c32b7d | IMMUTABLE ARTIFACT |
| Route | angular-18.x -> angular-19.x -> angular-20.x -> 21.x | DATABASE / WORKFLOW EVENT |

The runtime profile is shared by all three stages. The target policy is strict-functional-parity, target Angular family 21.x.

### 6.2 Stage proof table

| Stage | Stage ID | Version evidence | Workspace and result | Repairs/gates | Final fingerprint and seal | Source |
|---|---|---|---|---|---|---|
| 18 -> 19 | angular-18-to-19--a13150e1f4a00ffd | Source 18.0.0; target package.json 19.0.0; installed/core metadata 19.2.25; CLI 19.2.27; package-lock resolved 19.2.25. | Bootstrap npm ci passed. Angular update failed twice, then v3 retry passed. Final install, build, and tests passed. | G07, G08, two G10 repair paths (first orphaned, second passed), G11 approved. | sha256:a7eca3...d077; seal-angular-18-to-19--a131...; manifest artifact artifact-0657d7c2541b437ab0a60ce40f632024. | DATABASE / IMMUTABLE ARTIFACT / WORKFLOW EVENT |
| 19 -> 20 | angular-19-to-20--1b0df364be437ce7 | Source 19.2.25; target package.json 20.0.0; installed/core metadata 20.3.27; CLI 20.3.33; lock resolved versions agree. | Bootstrap npm ci passed. Angular update had one failed attempt, then transition/retry passed. Final install, build, and tests passed. | G07, G08, one successful dependency-transition repair/G10, G11 approved. | sha256:e667dc...9bd8; seal-angular-19-to-20--1b0...; manifest artifact artifact-359d6d598c954506879c1bfa1bfc377b. | DATABASE / IMMUTABLE ARTIFACT / WORKFLOW EVENT |
| 20 -> 21 | angular-20-to-21--e7d2fe320c40ffee | Source 20.3.27; target package.json 21.0.0; installed/core metadata 21.2.19; CLI 21.2.20; build-angular 21.x; lock and installed closure agree. | Bootstrap npm ci passed. Angular update first failed and later succeeded. Repair sequence included transition, dependency_add, reviewer revision, and final text repair. Final npm ci, build, and tests passed. | G07, G08, four recorded repair attempts, G10 decisions including request changes and final approval, G11 approved. | sha256:cea16c...d02b; seal-angular-20-to-21--e7d...; manifest artifact artifact-f8a481e08b2e4bc295ea2833bdd68f13. | DATABASE / IMMUTABLE ARTIFACT / WORKFLOW EVENT |

### 6.3 Route lineage

Stage bindings show the following immutable handoff:

    source snapshot
      -> stage 18-to-19 workspace (input sha256:1e47...e9a945e8)
      -> sealed 18-to-19 output (sha256:a7eca3...d077)
      -> stage 19-to-20 workspace (input sha256:a7eca3...d077)
      -> sealed 19-to-20 output (sha256:e667dc...9bd8)
      -> stage 20-to-21 workspace (input sha256:e667dc...9bd8)
      -> sealed 20-to-21 output (sha256:cea16c...d02b)

The stage 1 and stage 2 bindings are inactive after sealing; the stage 3 binding is active in the final route projection. All 28 checkpoints are marked safe_for_resume. Four reconstruction records show durable restore behavior.

## 7. Command execution architecture

The production pipeline is:

    command intent
      -> registry template renderer
      -> policy validation
      -> command_authorization_audits
      -> queue_authorized_command
      -> command_executions
      -> ExecutionWorker
      -> subprocess.Popen(shell=False)
      -> bounded/redacted stdout and stderr
      -> command result/log artifacts
      -> continuation wake and resume

The policy binds the executable alias, literal/token argument grammar, template id/version, plan/stage membership, runtime profile, workspace alias and safe relative directory, network profile, timeout, cancellation policy, expected state version, request payload hash, and idempotency key. The frontend and LLM submit intent; neither supplies an arbitrary shell string.

The worker execution path is separate from the transformer worker. TransformerWorker claims durable work and calls CommandExecutorService. ExecutionWorker alone creates the process. It uses shell=False, pipes output, bounds output and log chunks, redacts sensitive patterns, and terminates a process tree on cancellation/timeout.

### 7.1 E2E command shapes

| Operation | Recorded shape | Example execution IDs | Source |
|---|---|---|---|
| Bootstrap/final install | npm.cmd ci | execution-faba23...; exec-5918f7376ee6; exec-8bb38ed2e255; exec-a173f15d3e16 | IMMUTABLE ARTIFACT / DATABASE |
| Angular update | npx.cmd ng update with the stage plan's exact v3 renderer | exec-8f4f33f1ff34, exec-2d19e6881b67, exec-86561b4148e4, exec-3e06b607cf2b, exec-e3436f72bcaa, exec-337db367e048, exec-0e462390394f | DATABASE |
| Version check | npx.cmd ng version | exec-9c4df5289e60, exec-077a8133749a, exec-7ca806437ef3 | DATABASE |
| Build | npm.cmd run build -- --configuration production | exec-9595e34ad86f, exec-3880944c4afa, exec-bcfb45b307c2 | DATABASE |
| Test | npm.cmd run test -- --watch=false | exec-8304f1f65374, exec-1729d8093d3e, exec-3d87ddd4b431 | DATABASE |
| Lockfile generation | npm.cmd install --package-lock-only --ignore-scripts --no-audit --no-fund | exec-a183bd2b63dc | DATABASE |
| Governed package operations | npm.cmd install/uninstall with registry template arguments | Multiple repair-bound executions; all authorized before queue. | DATABASE |

There is an explicit governance mismatch to resolve: the recorded stage plan uses template tpl-angular-update-exact-v3, whose historical renderer includes --allow-dirty. AGENT.md prohibits --allow-dirty. No recorded command used --force, and the causal checker rejects force-oriented repair reasoning. The run is therefore reproducible evidence of behavior, but the v3 template and current repository rule are not simultaneously compliant without a deliberate policy/template decision.

## 8. Idempotency, leases, and restart durability

Continuation durability is implemented in TransformationContinuationService:

1. Creation binds the run, G06 approval, route plan, stage plan, checksums, request checksum, and idempotency key.
2. claim_next uses optimistic state_version/CAS and a lease. Only one worker owner can claim a live continuation.
3. waiting states persist the waiting execution, prompt, gate, or checkpoint rather than relying on a call stack.
4. wake increments wake_sequence and requeues only when the expected durable condition is satisfied.
5. complete requires the final legal state and clears worker ownership.

Commands have their own claim and terminal state machine. A terminal command result is reused by the same idempotency identity rather than executed again. Retry generations create new execution rows linked with parent_execution_id and attempt_number; historical execution rows are retained. Claim retries are bounded at three in CommandExecutorService. Mutating work whose lease expires is not blindly replayed: it is marked for reconstruction, a checkpoint is restored, and a successor is created or the workflow is classified.

The idempotency-key overflow hardening changed key creation to a bounded deterministic representation rather than allowing the 128-character database limit to fail after business work was prepared. The key remains tied to a canonical operation/request identity and a digest; the exact current helper is the authority for the byte/character representation.

Lockfile generation has explicit V1 -> V2 successor behavior. A stale V1 precondition does not mutate or delete the historical execution. It creates at most one deterministic successor bound to the new proof/fingerprint, and replay of that successor reuses its terminal result. This is the same durable principle used for command recovery and repair materialization.

## 9. Workspace architecture

The workspace lifecycle is:

    external source (read-only)
      -> source snapshot
      -> baseline sandbox
      -> per-stage sandbox/binding
      -> checkpointed mutation
      -> validation
      -> sealed stage output
      -> next-stage input
      -> final sealed Angular 21 workspace

MigrationWorkspaceLayoutService derives an external output layout and rejects source/repository overlap. Aliases such as BASELINE_SANDBOX, STAGE_SANDBOX, STAGE_WORKSPACE_ANGULAR_18_TO_19__A13150E1F4A00FFD, STAGE_WORKSPACE_ANGULAR_19_TO_20__1B0DF364BE437CE7, STAGE_WORKSPACE_ANGULAR_20_TO_21__E7D2FE320C40FFEE, MIGRATED_APP, and DELIVERY_CANDIDATE are persisted in the run policy/output layout. Alias paths must remain under the output root.

Fingerprints exclude allowed volatile roots where the operation contract permits it. node_modules and the root package-lock are treated specially by lockfile-generation V2; package.json and nonvolatile source/config files remain pinned. The artifact store and sealing context reject symlink escapes and sensitive workspace entries including .env, .pem, .key, and .pfx. The source path is external and never becomes a writable stage target.

### 9.1 Runtime tree (important paths only)

    C:\a\angular-crud-poc-angular-21-ea7cf8a66521\
    +-- .migration-factory\
        +-- runs\
            +-- run-80ee6328670b\
                +-- artifacts\
                |   +-- 00_job_setup\
                |   +-- global\execution-profile\
                |   +-- global\source-snapshots\snapshot-955d71c32b7d\
                |   +-- 04_workflow_state\
                |   +-- 05_repairs\
                |   +-- 06_validation\
                |   +-- stages\
                +-- baseline-sandbox\
                +-- source-snapshot\
                +-- stage-sandboxes\
                +-- temporary\
                +-- logs\
                +-- reports\
                +-- delivery-candidate       (recorded alias; not materialized)
                +-- final-assurance-sandbox  (recorded layout; not materialized)
        +-- migrated-app                    (recorded DB path; not materialized)

This tree is a representation of recorded/observed paths, not a claim that every listed directory currently exists. The three sealed stage outputs are present under their sealed lineage in the stage artifact/workspace structure; the final delivery locations are not.

## 10. Artifact model

LocalFilesystemArtifactStore is the artifact authority. It writes run-relative paths under a fixed layout, calculates SHA-256, creates immutable content and metadata, rejects traversal/symlink escape, and finalizes through an atomic temporary-file replacement. artifact_metadata records the artifact id, run/stage binding, type, relative path, checksum, schema version, execution/owner reference, MIME/size, finalization, immutable/redacted/truncated flags, and safe metadata.

The run has 499 artifact_metadata rows. A read-only verifier found 499 recorded files, zero missing files, zero checksum mismatches, and zero missing metadata sidecars. Observed type counts were approximately JSON 296, command_log 50, text_log 100, report 45, diff 7, and markdown 1. Artifact IDs are durable references; the relative path and checksum are the content/provenance binding.

| Evidence category | Example in latest run | Purpose | Source |
|---|---|---|---|
| Job setup/layout | artifacts/00_job_setup/output_layout.json; run_policy_snapshot.json | Run roots, aliases, policy, source/target constraints. | IMMUTABLE ARTIFACT |
| Source/analysis | artifacts/global/source-snapshots/snapshot-955d71c32b7d/snapshot_manifest.json; source_analyses row | Source inventory and fingerprint. | IMMUTABLE ARTIFACT / DATABASE |
| Compatibility/runtime | artifacts/global/execution-profile/execution_profile.json; runtime_probe_report.json | Node/npm/npx and policy-selected profile. | IMMUTABLE ARTIFACT |
| Command authorization | 41 command_authorization_audits and authorization artifacts under 04_workflow_state | Permission, template, request, and expected-state proof. | DATABASE / IMMUTABLE ARTIFACT |
| Command logs/results | command log artifacts under 04_workflow_state/command_logs and command_executions | Bounded stdout/stderr, exit, duration, redaction, result. | DATABASE / IMMUTABLE ARTIFACT |
| Failure evidence/route | stage repair context and failure artifacts under 05_repairs | Normalized failure, fingerprint, route, and causal context. | IMMUTABLE ARTIFACT |
| Repair proposal/diff/review | 05_repairs/attempt-repair-angular-20-to-21--e7d2fe320c40ffee-2/proposal.json, candidate.diff, review.json | Typed proposer output and independent review. | IMMUTABLE ARTIFACT |
| G10 package/apply | gate package artifact; apply-prepared.json; apply-applied.json | Human-approved checksum-bound candidate and postimage. | IMMUTABLE ARTIFACT |
| Lockfile verification | LockfileGenerationRunner emits lockfile-verification.json where that route ran. | Package/lock/workspace mutation proof. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Dependency-add verification | No dedicated dependency-add-verification.json was found in this run. | The generic source contract exists, but artifact closure should be standardized. | SOURCE CODE / WORKSPACE / INFERENCE |
| Validation | artifacts/.../validation/summary.json for each stage | Required final_install/build/test target result and fingerprint. | IMMUTABLE ARTIFACT |
| G11 | G11 package/decision artifacts and rows | Human approval of post-state/seal eligibility. | DATABASE / IMMUTABLE ARTIFACT |
| Seal/output manifest | seal checkpoints and output-manifest.json; stage seal manifest artifacts | Chain-bound sealed output and lineage. | DATABASE / IMMUTABLE ARTIFACT |

Example final stage repair artifacts are under:

    artifacts/05_repairs/attempt-repair-angular-20-to-21--e7d2fe320c40ffee-2/
      proposal.json
      candidate.diff
      review.json
      apply-prepared.json
      apply-applied.json

The absence of a dedicated dependency-add verification file is an artifact-contract gap, not evidence that the package was absent from the final workspace. The run does contain an apply ledger, lockfile/npm-ci executions, package/lock output, closure-related validation, and final seal evidence.

## 11. Failure evidence and classification

The failure path is:

    command terminal failure
      -> normalized failure evidence
      -> immutable failure fingerprint
      -> prior-fingerprint comparison
      -> causal/failure route
      -> deterministic repair or terminal block

Command execution failure means the process result was non-success, for example COMMAND_EXIT_NONZERO. Classification explains what failed and chooses a route. A repair semantic rejection means a typed proposal was invalid or not causally supported. A governance rejection means policy, checksum, stale state, workspace, network, or approval conditions failed. A terminal workflow blocker means no permitted next transition remains. These are different states and must not be collapsed into “the command failed.”

Failure fingerprints are computed from normalized failure evidence and relevant command/context inputs, then compared with prior attempts. NO_PROGRESS exists to stop repeated repairs that reproduce the same failure without changing the causal state. The runtime continuation retained a last_error_code of COMMAND_EXIT_NONZERO and a stale test message from an earlier failure; section 33 records why that is projection residue after completion.

Observed historical failures in the primary run include Angular peer-resolution failures, a failed jest-preset-angular install, a missing jest-environment-jsdom test environment, and the legacy jest-preset-angular/setup-jest import. Each became an evidence-bound repair route rather than an arbitrary retry.

## 12. Repair architecture

The complete repair pipeline is:

    failure
      -> frozen failure/context pack
      -> proposer invocation
      -> semantic binding and causal review
      -> proposal artifact and candidate diff
      -> independent reviewer
      -> G10 package and human decision
      -> typed apply
      -> deterministic materialization/revalidation
      -> G11
      -> stage seal

RepairApplicationService supports only typed, bounded operations. replace_text requires exactly one preimage match and preserves the intended newline/content contract. Dependency operations mutate approved package manifest sections through policy; lockfiles are never directly patched as a free-form diff. A candidate diff is evidence of the proposed change, not permission to apply it.

Observed repair statuses in run-80ee6328670b were:

| Status | Meaning in the run | Source |
|---|---|---|
| executing | An attempt had entered execution; stage 1 attempt 1 remains as a historical orphan. | DATABASE |
| validation_passed | Repair application and required validation completed successfully. | DATABASE |
| migration_retried | A repaired stage returned to route validation/retry. | DATABASE |
| superseded | A prior attempt was replaced by a later approved revision or successful later lineage. | DATABASE |

The source lifecycle service defines ACTIVE_REPAIR_STATUSES exactly as evidence_frozen, proposed, review_accepted, waiting_g10, applying, applied, revalidating, and revalidating_affected. It reconciles older active history when a later successful attempt has approved G10, apply evidence, validation summary, and approved G11. It does not include executing, validation_failed, or approved_pending_execution in that exact active set. The omission is a known correctness gap even though this run completed.

Automatic attempts and human revisions share repair_attempts but retain lineage. A request_changes action creates a child with parent_attempt_id and the parent review artifact/checksum. Superseded attempts remain immutable historical records. A passed attempt has validation evidence; migration_retried denotes route retry rather than a clean validation terminal.

## 13. Dependency transition

Dependency transition is for an existing package whose peer constraints block Angular update. The deterministic route is:

    peer failure
      -> identify blocking dependency
      -> detach/uninstall
      -> retry Angular update
      -> normalize lockfile if required
      -> reinstall compatible bundle
      -> npm ci
      -> dependency closure verification

DependencyClosureService contains the intentional static authority _COMPATIBLE_REINSTALL_BUNDLES:

| Target family | Bundle authority observed |
|---|---|
| Angular 19 | @angular-builders/jest -> 19.0.0; jest-preset-angular -> 14.4.0 |
| Angular 20 | jest-preset-angular -> 14.6.2 |
| Angular 21 | jest 30.4.2, jsdom 26.1.0, @types/jest 30.0.0 when present, jest-preset-angular 16.1.3 |

This static table is intentionally different from dynamic dependency_add. It is a compatibility bundle for known transition closure, with exact versions required by the transition policy. The runner is durable and keyed by repair attempt. Each phase is a persisted successor-safe operation, so an ERESOLVE or restart can resume from a checkpoint instead of repeating an unbound shell action. The observed update retry executions include stage 1 exec-86561b4148e4, stage 2 exec-e3436f72bcaa, and stage 3 exec-0e462390394f.

## 14. Dynamic dependency_add

The current generic dependency_add architecture is intentionally not a package-specific Angular exact-version map:

1. The LLM proposes a package name, package section, and semver intent/range.
2. DependencyAdditionPolicy validates grammar and governance only. It rejects non-registry forms such as URLs, git, file, workspace, npm aliases, and dist-tags.
3. Backend binds the proposal, stage plan, workspace fingerprint, request checksum, and candidate diff.
4. G10 approves the manifest intent.
5. Backend applies package.json only through the typed operation.
6. LockfileGenerationRunner generates package-lock with npm, rather than an LLM or static table choosing the exact resolved version.
7. npm ci materializes node_modules.
8. Backend observes exact lockfile and installed versions and verifies manifest/lock/install agreement.

Conceptually:

    DependencyAdditionPolicy
      -> approved_version_spec
      -> package-lock exact resolved version
      -> installed version
      -> dependency-add verification

The run exercised this path with jest-environment-jsdom in devDependencies and intent ^30.0.0. The proposal was recorded in repair attempt 2 for stage 3, reviewed as low risk, applied, followed by lockfile generation and npm ci. The later test still failed because the setup import was a separate source/text issue, which led to a human revision and final replace_text repair. Production logic is generic; there is no package-specific jest-environment-jsdom exact-version branch in DependencyAdditionPolicy.

The missing dedicated dependency-add-verification.json artifact is a real contract gap. The source verification functions and focused tests exist, and final closure/build/test/seal evidence exists, but a future run should emit and bind the named verification artifact whenever dependency_add is applied.

## 15. dependency_change

dependency_change applies to an existing package:

    existing package
      -> LLM semver intent
      -> package.json typed mutation
      -> reviewer and G10
      -> lockfile generation
      -> npm ci materialization
      -> affected validation
      -> full validation replay
      -> closure/version verification

It differs from dependency_add because the package must already be present and the operation changes an existing manifest entry. It differs from dependency_transition because it is not the fixed detach/update/reinstall closure for a peer blocker. All three routes share proposal checksum, workspace fingerprint, G10, lockfile scope, npm ci ordering, and validation authority.

Stage 3 attempt 3 proposed a jest-preset-angular dependency change to ^17.0.0, was reviewed, then superseded by the human revision that fixed setup-jest.ts. The attempt remains useful evidence of reviewer/request-change lineage, not final proof of the chosen solution.

## 16. Source/text repair

The final stage repair used replace_text against setup-jest.ts. The old legacy import was replaced with:

~~~typescript
import { setupZoneTestEnv } from 'jest-preset-angular/setup-env/zone';

setupZoneTestEnv();
~~~

The route was:

    replace_text
      -> exact preimage hash
      -> candidate.diff
      -> independent review
      -> G10 package/decision
      -> PatchApplyService
      -> postimage/fingerprint verification
      -> npm ci/build/test
      -> G11

The final stage 4th repair attempt is validation_passed and carries proposal artifact 8f4b..., review artifact 987..., apply artifact 392..., and validation artifact 042d.... The artifact files for the stage 3 repair are in the attempt-...-2 directory for the earlier dependency_add; the final text-repair artifacts are bound through the repair_attempt row and its artifact IDs. Arbitrary free-form writes are not permitted because the operation must identify the file, exact preimage, postimage, path confinement, and target validation.

## 17. LLM architecture

The LLM boundary is implemented by backend/app/llm_gateway/azure_gateway.py, contracts.py, redaction.py, and services/transformer_prompt_service.py. The gateway uses the governed Azure OpenAI endpoint and a deployment alias from configuration; the audit did not expose endpoint secrets or credential values.

The role/task router observed in llm_invocations was:

| Role | Task | Count | Responsibility |
|---|---|---:|---|
| phase_proposer | analysis_summary, plan_rationale | 2 | Produce structured planning content. |
| phase_reviewer | analysis_review, planning_review | 2 | Independently critique planning content. |
| repair_proposer | repair_diagnosis | 7 | Produce typed repair candidate intent/context. |
| repair_reviewer | repair_review | 7 | Critique the candidate and propose accept/request_changes/reject. |

All 18 invocations are completed. Structured JSON schema/version and prompt version are persisted with idempotency, request/correlation identity, input hashes, output/error artifacts, state/event versions, retry/latency data, and sanitized provider diagnostics. Responses are bounded at 4 MB. Redaction covers authentication/API tokens, environment secrets, connection strings, and production URLs.

The LLM is explicitly not allowed to own truth, exact command rendering, package-lock content, direct process execution, state mutation, gate approval, workspace escape, or final validation. The backend treats prompt context as untrusted, binds output to the current plan/checkpoint/fingerprint, and fail-closes malformed or semantically unsupported output.

## 18. Independent Reviewer

The reviewer receives immutable proposal/evidence context and returns a structured accept, request_changes, or reject result. It cannot author a new candidate or apply a change. Causal review checks that the candidate addresses the recorded failure route, names permitted operations, identifies validation targets, and does not smuggle in force or arbitrary command behavior.

The reviewer result is checksum-bound to the proposal, candidate diff, plan/stage plan, workspace fingerprint, and G10 package. Reviewer limitations are not discarded: G10 can require an override comment when a reviewer raised concerns. In the run, stage 1 attempt 1, stage 1 attempt 2, and stage 3 attempt 1 had request-change/override handling; the final stage 3 attempt 4 had an accepted low-risk review after human revision.

## 19. Human-in-the-loop gates

G10 approves a concrete repair package, not an abstract “fix.” The package binds:

- proposal and review artifacts/checksums;
- candidate diff and apply intent;
- plan/stage-plan identifiers and checksums;
- expected continuation state version;
- current workspace fingerprint;
- parent revision lineage when applicable;
- repair attempt and validation-target contract.

The gate decision includes actor, decision, comment, idempotency/request checksum, expected state version, package checksum, and observed workspace fingerprint. A stale or tampered package cannot be applied. Request changes creates a child repair attempt; reject is terminal for that route.

G11 approves post-state evidence: validation summary, dependency closure/version evidence, final workspace fingerprint, and seal eligibility. The sealing flow then checks that the approved evidence still matches before writing the seal.

This run had approved G07/G08/G11 for each of the three stages. G10 decisions were present for the repair attempts, including stage 3 request changes and final approval. G09/G12 were not required for this route and had no latest-run rows.

## 20. Repair budget

The implementation deliberately separates:

    attempt_number = immutable monotonic audit sequence
    repair_budget() = causal/lifecycle consumption authority

The continuation row has worker attempt/max_attempts values (0 and 3 in the final row); those are lease/retry controls and must not be confused with repair budget. Repair budget evaluates lifecycle and causal progress: an evidence-free recovery or reconciliation should not automatically consume the same budget as an applied repair; an accepted/applied or repeated no-progress repair does. Human revision remains a child in the same causal lineage and is checked against the lifecycle-aware budget.

The primary run has seven repair_attempt rows across three stages:

| Stage | Attempts | Final relevant state |
|---|---:|---|
| 18 -> 19 | 2 | Attempt 1 historical executing residue; attempt 2 validation_passed. |
| 19 -> 20 | 1 | Attempt 1 validation_passed. |
| 20 -> 21 | 4 | Attempt 1 migration_retried; attempt 2 superseded dependency_add; attempt 3 superseded request-change parent; attempt 4 validation_passed. |

No budget-exhaustion terminal was recorded. No-progress fingerprint comparison remains the safety stop if repeated repairs fail to change causal state.

## 21. Lockfile generation V2

LockfileGenerationRunner uses the governed command:

    npm install --package-lock-only --ignore-scripts --no-audit --no-fund

Before queueing, it proves package.json checksum, package-lock checksum, workspace/binding fingerprint, and fingerprint_scope. The allowed volatility is the root package-lock and configured volatile names such as node_modules and hidden package-manager metadata. package.json and nonvolatile source/config files remain pinned. Shrinkwrap and unsynchronized/missing artifacts fail closed.

V1 behavior rejected or stalled when a stale baseline was detected. V2 creates a successor with new pre-command proof, deterministic idempotency, one-successor maximum, and a verification artifact. It does not rewrite or delete historical command executions. CAS protects the step/binding from concurrent mutation.

## 22. Repair materialization

For manifest repair the required ordering is:

    dependency manifest apply
      -> lockfile generation
      -> repair-specific final_install/npm ci
      -> affected validation
      -> full validation replay

npm ci must precede affected tests because tests against the old node_modules would prove the wrong dependency closure. The dependency_add flow in stage 3 follows this ordering: manifest intent, lockfile-only generation, npm ci, then test/build evidence; the remaining test failure led to the setup-jest text repair.

Recovery recognizes persisted validation-key forms, including the historical doubled-group shape, reconciles the attempt, resets the affected StageStep when necessary, and creates a new command generation. It never deletes historical CommandExecution rows. This is the recovery path for stale pre-materialization validation.

## 23. Validation architecture

ValidationRunner binds final_install, builds, tests, and configured lint targets to StageStepModel and the current attempt. Each target has an attempt/idempotency identity, command execution, input/output checksum, workspace fingerprint, and artifact references. A validation summary aggregates target results and the final fingerprint. Any failure is routed through classify_failure rather than marking the stage clean.

For run-80ee6328670b, stage validation summaries passed with these required final executions:

| Stage | final_install | build | test | Result | Source |
|---|---|---|---|---|---|
| 18 -> 19 | exec-5918f7376ee6 | exec-9595e34ad86f | exec-8304f1f65374 | passed | IMMUTABLE ARTIFACT |
| 19 -> 20 | exec-8bb38ed2e255 | exec-3880944c4afa | exec-1729d8093d3e | passed | IMMUTABLE ARTIFACT |
| 20 -> 21 | exec-a173f15d3e16 | exec-bcfb45b307c2 | exec-3d87ddd4b431 | passed | IMMUTABLE ARTIFACT |

Intermediate stage 3 failures included missing jest-environment-jsdom and the legacy setup import. Those failures were not erased; they remain in command/repair evidence and were followed by successful later generations.

## 24. Version verification

Version truth is cross-checked from runtime profile, package.json, package-lock, installed package metadata, and Angular CLI output. ANSI normalization was added so npx ng version output can be parsed without terminal escape codes. Missing or contradictory expected evidence fails closed.

| Stage | package.json target | installed Angular core/ng metadata | CLI | Lockfile/closure | Source |
|---|---|---|---|---|---|
| 18 -> 19 | 19.0.0 | 19.2.25 / 19.2.25 | 19.2.27 | package-lock resolved 19.2.25 | IMMUTABLE ARTIFACT |
| 19 -> 20 | 20.0.0 | 20.3.27 / 20.3.27 | 20.3.33 | lock and installed versions agree | IMMUTABLE ARTIFACT |
| 20 -> 21 | 21.0.0 | 21.2.19 / 21.2.19 | 21.2.20 | lock and installed versions agree; build-angular 21.x | IMMUTABLE ARTIFACT |

The final stage package root contained Angular runtime packages at ^21.0.0, platform-browser-dynamic 21.2.19, RxJS ~7.8.0, zone.js ~0.15.1, TypeScript ~5.9.3, CLI/build/compiler-cli ^21.0.0, Jest 30.4.2, jest-preset-angular 16.1.3, jsdom 26.1.0, and jest-environment-jsdom ^30.0.0. This is evidence of the sealed stage package, not a claim that a public delivery directory exists.

## 25. Stage sealing

StageSealingService and TransformerSealingFlow implement:

    passed validation
      -> approved G11
      -> clean sealing context
      -> seal checkpoint
      -> output-manifest.json
      -> seal.json
      -> workspace fingerprint and chain hash
      -> immutable sealed output
      -> next-stage materialization

The sealing context refuses active commands/prompts/repairs, verifies the expected workspace fingerprint, rejects symlink/sensitive-file violations, and binds the previous seal hash, stage plan checksum, G12 checksum when applicable, output manifest checksum, and validation summary checksum. The observed sealed manifests are:

| Stage | Seal checkpoint | Manifest artifact | Chain checksum | Source |
|---|---|---|---|---|
| 18 -> 19 | seal-angular-18-to-19--a131... | artifact-0657d7c2541b437ab0a60ce40f632024 | sha256:f5241e5e...08738 | DATABASE / IMMUTABLE ARTIFACT |
| 19 -> 20 | seal-angular-19-to-20--1b0... | artifact-359d6d598c954506879c1bfa1bfc377b | sha256:b5706b5e...99cd | DATABASE / IMMUTABLE ARTIFACT |
| 20 -> 21 | seal-angular-20-to-21--e7d... | artifact-f8a481e08b2e4bc295ea2833bdd68f13 | sha256:67f65ba2...d555 | DATABASE / IMMUTABLE ARTIFACT |

The seal is a stage/output lineage proof. It is not, by itself, an external publication or delivery record.

## 26. Completion

TransformerSealingFlow.complete enforces these invariants before final completion:

1. The planned route exists.
2. Every route stage is sealed.
3. Required per-stage gates are approved: G07, G08, and G11, or the alternate G09/G12 path where the policy selects it.
4. No active command remains.
5. No active prompt remains.
6. No active repair work remains according to the lifecycle reconciliation.
7. The run transitions through STAGED_MIGRATION_COMPLETED to COMPLETED.
8. The continuation transitions to terminal.

The exact source constant ACTIVE_REPAIR_STATUSES is:

    evidence_frozen
    proposed
    review_accepted
    waiting_g10
    applying
    applied
    revalidating
    revalidating_affected

The source does not include executing, validation_failed, or approved_pending_execution in that set. The primary run contains stage 1 attempt 1 with status executing, yet the route sealed and completed. This is a residual architectural gap: the completion contract can ignore an orphaned historical execution status if reconciliation does not explicitly classify it. The successful E2E behavior proves the route reached its intended terminal path; it does not prove the lifecycle set is complete.

## 27. Delivery

Transformer completion and external delivery are separate contracts.

| Delivery question | Observation | Verdict | Source |
|---|---|---|---|
| Did all route stages seal? | Yes, 3 of 3 sealed. | Proven. | DATABASE / IMMUTABLE ARTIFACT |
| Is the final stage workspace/seal present? | Yes, stage 20 -> 21 seal/fingerprint/manifest evidence exists. | Proven. | DATABASE / IMMUTABLE ARTIFACT |
| Does DB migrated_app_path exist? | It projects C:\a\angular-crud-poc-angular-21-ea7cf8a66521\migrated-app. | Projection only. | DATABASE |
| Does that migrated-app directory exist? | No. | Not proven. | WORKSPACE |
| Does delivery-candidate exist/materialize? | Recorded alias points under the run root, but the directory is absent and artifacts/delivery is empty. | Not proven. | DATABASE / WORKSPACE |
| Is there a final delivery/publication record? | No final delivery artifact/record was found. | Not proven. | DATABASE / WORKSPACE |

**Delivery verdict: NOT DELIVERED / NOT PROVEN.** The latest run proves transformer stage completion and sealed route evidence, not materialization/publication at migrated_app_path or delivery-candidate.

## 28. Frontend projection

Transformation routes build the projection in backend/app/api/routes/transformation.py::_projection. It joins continuation state, current stage, bindings, checkpoints, active command, prompts, repairs, dependency operation, validation artifacts, sealed chain, route history, and runtime profile. The frontend does not calculate an authoritative state machine.

The UI's 01-09 evidence surfaces in TransformationPanel/TransformationSections cover:

1. backend truth/current continuation and stage;
2. worker/command status and bounded logs;
3. current human gate/action;
4. prompt and reconstruction context;
5. dependency/version/runtime evidence;
6. validation targets and results;
7. governed repair proposal/review/apply state;
8. seal/checkpoint/route lineage;
9. historical diagnostics and completion/delivery projection.

useTransformation uses Promise.allSettled for projection and command refresh. If refresh fails, it preserves the last authoritative projection rather than inventing a new state. A 409 causes authoritative reload. TransformationPanel disables G10 approval without evidence and requires an override comment when reviewer concerns require it. The frontend still exposes stale backend projection fields where the backend row is stale: for this run, last_error_code/message and waiting_execution_id can remain visible after successful completion.

## 29. API contract

The router prefix is /api/v1. The table lists the current Transformer-relevant routes.

| Method | Route | Purpose | Important request fields | Response/authority | Mutation/human action | Source |
|---|---|---|---|---|---|---|
| GET | /runs/{run_id}/transformation | Authoritative Transformer projection. | Path run_id. | Continuation, stage, commands, gates, prompts, repairs, validation, seals, runtime, history. | No. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/gates/{gate_id}/decisions | Record gate decision. | decision, comment, expected_state_version, idempotency_key, package_checksum, workspace_fingerprint, correlation_id. | Authoritative mutation result/projection. | Yes; human/operator. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/repairs/{attempt_id}/revisions | Request repair revision. | Parent attempt, parent review/proposal bindings, expected state/checksum, idempotency, revision context. | Child attempt and authoritative state. | Yes; human. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/repairs/{attempt_id}/reject | Reject repair. | Expected state, idempotency, reason/comment. | Authoritative state. | Yes; human/reviewer. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/prompts/{prompt_id}/decision | Select prompt option. | Option, expected state, idempotency, observed fingerprint/correlation. | Authoritative continuation state. | Yes; human. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/cancel | Request Transformer cancellation. | Expected state/idempotency/correlation. | Authoritative cancellation state. | Yes. | SOURCE CODE |
| POST | /runs/{run_id}/transformation/restart | Request durable restart/recovery. | Expected state/idempotency/correlation. | Authoritative continuation/recovery state. | Yes. | SOURCE CODE |
| POST | /runs/{run_id}/commands | Queue an operator command subject to policy. | Template/intent, args, alias, expected state, idempotency, request checksum. | CommandExecution reference. | Yes, policy-governed. | SOURCE CODE |
| GET | /runs/{run_id}/commands | List command executions. | Run and status filters. | Durable command rows. | No. | SOURCE CODE |
| GET | /runs/{run_id}/commands/{execution_id} | Read command execution. | Path IDs. | Durable status/result/lineage. | No. | SOURCE CODE |
| GET | /runs/{run_id}/commands/{execution_id}/logs | Read bounded logs. | Path IDs/stream options. | Log chunks. | No. | SOURCE CODE |
| GET | /runs/{run_id}/commands/{execution_id}/logs/summary | Read log summary. | Path IDs. | Counts, truncation, redaction, finalization. | No. | SOURCE CODE |
| GET | /runs/{run_id}/commands/{execution_id}/logs/stream | SSE command log stream. | Path IDs/Last-Event-ID. | Ordered chunks/heartbeat. | No. | SOURCE CODE |
| POST | /runs/{run_id}/commands/{execution_id}/cancel | Cancel command. | Expected state/idempotency/correlation. | Durable cancellation. | Yes; policy-governed. | SOURCE CODE |
| GET | /runs/{run_id}/active-command | Current active command projection. | Run id. | Durable command. | No. | SOURCE CODE |
| GET | /runs/{run_id}/active-lease | Current active worker lease. | Run id. | Durable lease. | No. | SOURCE CODE |
| GET | /migrations/{run_id}/artifacts | List artifacts. | Run id. | Artifact references/checksums. | No. | SOURCE CODE |
| GET | /migrations/{run_id}/artifacts/{artifact_path} | Open run-relative artifact. | Safe relative path. | Artifact content if immutable and authorized. | No. | SOURCE CODE |
| GET | /artifacts/{artifact_id} | Open artifact by ID. | Artifact id. | Artifact content/metadata. | No. | SOURCE CODE |
| GET | /runs/{run_id}/state | Run-level authoritative state. | Run id. | Run status/phase/version. | No. | SOURCE CODE |
| GET | /runs/{run_id}/events | Ordered run event stream. | Run id, Last-Event-ID. | SSE events/heartbeat. | No. | SOURCE CODE |

Run routes also provide POST /runs, POST /runs/{run_id}/start, POST /runs/{run_id}/retry-source-intake, and POST /runs/{run_id}/cancel. All mutation paths use authenticated_actor/authorize_run and expected-state/idempotency/checksum controls appropriate to the operation.

## 30. Security and governance invariants

### 30.1 Trust-boundary matrix

| Decision | Allowed authority | Evidence/guard | Not allowed |
|---|---|---|---|
| Source contents | Source snapshot/read-only intake | Snapshot manifest/fingerprint | Transformer or frontend mutation |
| Command executable/args | Registry/policy renderer | Template/version, literal/token grammar, authorization audit | LLM/frontend shell string |
| Process creation | ExecutionWorker through CommandExecutor | Authorized command, shell=False, alias confinement | Any other service's subprocess |
| Network/package source | Policy-selected registry/network profile | Approved registries, runtime profile | Arbitrary URL/git/file/workspace dependency |
| Repair intent | Proposer LLM | Structured schema, failure context, proposal checksum | Direct apply |
| Repair acceptability | Independent reviewer plus causal policy | Review checksum, limitations, route binding | Proposer self-approval |
| Repair application | Deterministic backend plus approved G10 | Preimage/postimage, stage plan, workspace fingerprint | Free-form write or lockfile patch |
| Human change | G10/G11 decision API | Package/checksum/state/fingerprint CAS | Stale or tampered package |
| Durable transition | StateTransitionService | expected_state_version, legal transition, idempotency | Frontend-only state |
| Evidence | Artifact store | SHA-256, immutable finalized metadata/sidecar | In-place overwrite |
| Final route completion | SealingFlow | All seals/gates/no-active-work/final evidence | E2E pass alone |

The run's command policy used shell disabled, a PATH/HTTP_PROXY/HTTPS_PROXY environment allowlist, approved-registry network profile, safe relative working directories, bounded timeouts/output, and 41 accepted authorization audits. The command catalogue contains 18 templates. The repository rule against --force/--allow-dirty must be reconciled with the historical v3 Angular update template before accepting that template as current governance.

## 31. Final E2E run proof

### 31.1 Run and continuation

| Proof item | Value | Source |
|---|---|---|
| Run status | COMPLETED | DATABASE |
| Run phase | FEASIBILITY_PLANNING (stale projection despite completion) | DATABASE |
| Run state_version | 88 | DATABASE |
| Created | 2026-08-09 00:30:25.901135 | DATABASE |
| Updated/completed | 2026-08-09 01:57:16.992108 | DATABASE |
| Continuation | transform-d6569843ad50 | DATABASE |
| Continuation status | completed | DATABASE |
| Current node | terminal | DATABASE |
| Continuation state_version | 389 | DATABASE |
| Wake sequence | 61 | DATABASE |
| Completion events | STAGED_MIGRATION_COMPLETED then TRANSFORMATION_CONTINUATION_COMPLETED | WORKFLOW EVENT |

### 31.2 Final route, gates, repairs, and artifacts

| Proof item | Value | Source |
|---|---|---|
| Stages | 3; all sealed | DATABASE / IMMUTABLE ARTIFACT |
| Gate route | G07, G08, G10, G11 per stage as applicable | DATABASE / WORKFLOW EVENT |
| Repair attempts | 7 total | DATABASE |
| Repair terminal successes | stage 1 attempt 2; stage 2 attempt 1; stage 3 attempt 4 | DATABASE / IMMUTABLE ARTIFACT |
| Command executions | 49 | DATABASE |
| Authorization audits | 41, all accepted | DATABASE |
| Workflow events | 629 | DATABASE |
| LLM invocations | 18, all completed | DATABASE |
| Artifact metadata | 499, all immutable; verifier found no missing/mismatched files | DATABASE / WORKSPACE |
| Final stage fingerprint | sha256:cea16c...d02b | DATABASE / IMMUTABLE ARTIFACT |
| Final seal manifest | artifact-f8a481e08b2e4bc295ea2833bdd68f13 | IMMUTABLE ARTIFACT |

### 31.3 Final Angular/runtime/validation

| Item | Value | Source |
|---|---|---|
| Angular target | package.json 21.0.0; installed/core metadata 21.2.19 | IMMUTABLE ARTIFACT |
| Angular CLI | 21.2.20 | IMMUTABLE ARTIFACT |
| build-angular | 21.x in final sealed package | IMMUTABLE ARTIFACT |
| Node/npm | v22.23.1 / 10.9.8 | IMMUTABLE ARTIFACT |
| final npm ci | exec-a173f15d3e16, passed | IMMUTABLE ARTIFACT |
| final build | exec-bcfb45b307c2, passed | IMMUTABLE ARTIFACT |
| final tests | exec-3d87ddd4b431, passed | IMMUTABLE ARTIFACT |
| lint | No separate final lint target was required by the stage validation summary. | IMMUTABLE ARTIFACT |
| final output path | Sealed stage lineage exists; migrated-app and delivery-candidate are absent. | WORKSPACE / DATABASE |

**Runtime verdict:** PROVEN staged E2E completion through Angular 18 -> 19 -> 20 -> 21, including repair, validation, G11, and three seals.  
**Delivery verdict:** NOT PROVEN / NOT DELIVERED.

## 32. Defects discovered and fixed during E2E hardening

Only issues with source/history/runtime evidence are listed.

| Symptom | Root cause | Generic fix | Why safe | Current status | Source |
|---|---|---|---|---|---|
| Runtime schema lacked fields required by Transformer evolution. | Migration-history/schema drift. | Required transformer tables/LLM failure columns are checked by database startup compatibility; migrations were brought to current heads in the proof setup. | Startup fails closed on incompatible schema. | Historical hardening; verify migration state before merge. | SOURCE CODE / WORKFLOW EVENT |
| Angular toolchain behavior varied by environment. | Compatibility profile was implicit. | Persisted execution profile selects Node 22.23.1/npm 10.9.8/npx and allowlist/network policy. | Runtime is evidence-bound and reproducible. | Proven for this run. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Peer conflict was not consistently routed. | Failure output/parsing did not identify the blocking package. | Normalized failure/fingerprint plus causal dependency transition route. | Repair only follows a supported route. | Proven by all three stage transitions. | SOURCE CODE / DATABASE |
| Causal checker treated prose containing force as an executable force request. | Over-broad prose token match. | Causal review distinguishes command tokens from explanatory text. | Registry still rejects actual forbidden args. | Fixed; no --force in run commands. | SOURCE CODE / DATABASE |
| Transition retries duplicated or lost install phases. | Dynamic install had no durable successor identity. | Phase-persisted DependencyTransitionRunner and idempotent successor generation. | Historical rows remain; replay reuses terminal results. | Proven across stages. | SOURCE CODE / DATABASE |
| ng version parser failed on ANSI output. | CLI output included terminal escape codes. | Normalize ANSI before parsing; fail closed when evidence is missing. | Parser remains evidence-based. | Proven in three stage checks. | SOURCE CODE / IMMUTABLE ARTIFACT |
| Repair could not add a missing dependency. | Earlier path lacked generic dependency_add. | Typed DependencyAdditionPolicy and backend-controlled closure verification. | Package intent is semver-governed; npm resolves exact version. | Source/tests present; run exercised jest-environment-jsdom. | SOURCE CODE / DATABASE |
| dependency_add used a static exact-version map. | Prototype conflated dynamic addition with compatibility transition. | Dynamic add accepts a governed semver intent; static authority remains only for compatible reinstall bundles. | Exact version is observed from lock/install after approval. | Current source verified; artifact contract has a gap. | SOURCE CODE / IMMUTABLE ARTIFACT |
| G10 revision lineage rejected equivalent raw/Pydantic values. | Equality/binding mismatch across representations. | Normalize revision context and bind parent artifacts/checksums. | Child cannot claim an unrelated parent. | Proven by stage 3 request-change lineage. | SOURCE CODE / DATABASE |
| Gate errors were only transient. | StageGateError was not durable. | Persist gate package/decision/status/reason and project it. | Restart preserves human boundary. | Current durable gate path. | SOURCE CODE / DATABASE |
| Long idempotency keys overflowed storage. | Canonical key exceeded 128-character limit. | Bounded deterministic keys with digest identity. | Same operation remains idempotent within schema. | Focused regression present. | SOURCE CODE |
| Lockfile verifier saw hidden package-manager mutation. | node_modules/.package-lock.json was outside mutation scope. | V2 fingerprint scope explicitly allows volatile node_modules metadata and root lockfile only. | Nonvolatile workspace remains pinned. | Current source/tests present. | SOURCE CODE |
| Stale lockfile proof blocked replay. | V1 could not create a safe successor. | One-successor V2 generation with new proof; historical command retained. | No overwrite/deletion. | Current source/tests present. | SOURCE CODE |
| Tests ran before dependency materialization. | Repair flow did not always npm ci before affected validation. | Enforce manifest -> lockfile -> npm ci -> affected/full validation. | Tests observe the approved closure. | Proven in stage 3 later generations. | SOURCE CODE / DATABASE |
| Validation recovery rejected persisted key shape. | Historical keys had a doubled group form. | Reconcile supported key grammar, reset step, preserve execution history. | Recovery is idempotent and auditable. | Current source/tests present. | SOURCE CODE |
| Repair budget used raw attempt number. | Audit sequence was treated as consumption. | Separate immutable attempt_number from lifecycle-aware repair_budget(). | Recovery/history does not consume budget accidentally. | Current source/tests present. | SOURCE CODE |
| Historical repair could block a later success. | Lifecycle reconciliation did not supersede all obsolete history. | Reconcile later approved apply/validation/G11/seal evidence. | Older evidence remains immutable. | Partially fixed; executing omission remains. | SOURCE CODE / DATABASE |

## 33. Current known debt

| Issue | Severity | Runtime impact | Evidence | Recommended follow-up |
|---|---|---|---|---|
| Six broken foreign-key references in stage_checkpoints.created_from_execution_id. | High data-integrity debt | Conceptual checkpoint provenance is clear from fingerprints, but FK integrity is not clean. | PRAGMA integrity_check=ok; PRAGMA foreign_key_check returned six rows, each with a sha256 value in the FK column. | Add a repair migration/constraint-safe backfill in a separate authorized change; never edit this proof DB in place. |
| Orphan stage 1 repair attempt with status executing. | High lifecycle debt | Completion can ignore active-looking historical work. | DATABASE row attempt 1; source ACTIVE_REPAIR_STATUSES omits executing. | Add explicit reconciliation for executing/approved_pending_execution/validation_failed and regression tests. |
| ACTIVE_REPAIR_STATUSES incomplete. | High | Seal/complete active-work invariant is weaker than the status vocabulary. | SOURCE CODE / DATABASE | Define active, historical, terminal sets centrally and test every status. |
| continuation.waiting_execution_id stale after success. | Medium projection debt | UI/debugging may show a final command as still awaited. | DATABASE points to exec-3d87ddd4b431 while continuation is terminal. | Clear waiting fields in every wake/complete path; add projection invariant. |
| continuation.last_error_code/message stale after success. | Medium projection debt | Completed UI can display an old test failure. | DATABASE has COMMAND_EXIT_NONZERO and missing jest-preset-angular/setup-jest message after final success. | Clear or scope last-error to current active generation; preserve historical diagnostics separately. |
| migration_runs.run_phase and resolved-version fields stale. | Medium projection debt | Run-level summary says FEASIBILITY_PLANNING and null target_version_resolved/source_angular_version despite sealed stages. | DATABASE; stage rows and artifacts prove actual versions. | Reconcile run projection on stage completion and finalization. |
| Stage 1/2 lockfile_generation steps remain PENDING. | Medium data/projection debt | Sealed stages contain residue that conflicts with an all-required-steps interpretation. | DATABASE stage_steps: lockfile_generation pending for stages 1 and 2. | Define whether step is optional for transition route; otherwise reconcile to a terminal status with evidence. |
| Duplicate/pending historical G04/G05 records. | Medium audit clarity | Projection may show superseded planning gate attempts. | DATABASE counts show multiple G04/G05 rows and event history includes earlier pending then final approved. | Mark superseded decisions explicitly and project only the current package. |
| No materialized migrated-app/delivery candidate. | High release gap | Transformer completion cannot be handed to a consumer as a delivered output. | WORKSPACE missing paths; artifacts/delivery empty; DB aliases only. | Implement/verify delivery materialization and a durable delivery record before release claims. |
| No rows in run_assurance_statuses. | Medium assurance projection debt | Optional assurance consumer has no durable row. | DATABASE count 0. | Decide whether table is required for the current contract; emit or remove ambiguity. |
| Active run claim and worker lease are expired/stale. | Low cleanup debt | No final owner remains, but stale lease rows confuse operations. | DATABASE claim/lease expiry precedes final completion. | Reconcile/close leases at terminal completion and expose expiry reason. |
| Dependency-add verification artifact absent. | Medium evidence-contract gap | Closure is inferable but not directly addressable by the named artifact. | WORKSPACE artifact search; source verifier/tests exist. | Emit dependency-add-verification.json and bind its checksum to G11/seal. |
| --allow-dirty in historical v3 renderer conflicts with AGENT.md. | High governance gap | A replay can violate current repository policy even if this run passed. | SOURCE CODE command.py / AGENT.md / DATABASE command args. | Replace or explicitly re-authorize the template under current policy; add command-policy regression. |
| LangGraph allowed_objects deprecation/branch not found. | Medium maintenance gap | Future LangGraph upgrade may remove a compatibility path or stale assumption. | SOURCE CODE search found no allowed_objects symbol under backend/app. | Confirm current LangGraph API and remove stale docs/compatibility assumptions if any. |
| Static compatibility authority remains. | Intentional but bounded | Transition compatibility is deterministic; future packages need catalogue updates. | SOURCE CODE _COMPATIBLE_REINSTALL_BUNDLES. | Keep it limited to transition bundles; do not reuse it for dependency_add. |
| Very large orchestration/service files. | Medium maintainability debt | Review and change risk are concentrated. | transformer_graph.py ~187,892 bytes/3,824 lines; repair_application_service.py ~210,829 bytes; workflow.py 967 lines. | Extract bounded application services/contracts incrementally without changing state authority. |

The six FK rows were:

    stage_checkpoints seq 5, 8, 10 across stages
    created_from_execution_id = sha256:<workspace fingerprint>

SQLite PRAGMA integrity_check returned ok, which means the file is structurally readable; it does not negate the non-empty foreign_key_check result.

## 34. Test coverage and focused regressions

Tests were inspected but not run, as required. The following focused coverage exists and should be kept as the minimum regression set:

| Contract | Test area / node names | Source |
|---|---|---|
| dependency_add policy | test_dependency_add_absent_preserves_approved_version_spec; test_dependency_add_already_present_fails_closed; test_dependency_add_rejects_non_registry_specs; test_dependency_add_verification_agrees_on_observed_exact_version; test_dependency_add_verification_fails_closed_on_lock_installed_mismatch; test_dependency_add_policy_validates_intent_never_resolves_version | SOURCE CODE |
| G10 revision lineage | Parent request_changes lineage, wrong/tampered parent rejection, attempt budget, G10/G11 plan/version binding tests. | SOURCE CODE |
| bounded idempotency | Long-key/canonical idempotency regression and idempotent continuation/command creation tests. | SOURCE CODE |
| lockfile V2 | Governed scope, queue checksums, shrinkwrap block, CAS/replay, mutation rejection, V1 -> V2 successor/restart tests. | SOURCE CODE |
| pre-materialization recovery | Validation-key grammar, doubled-group reconciliation, StageStep reset, no execution deletion. | SOURCE CODE |
| repair request-change budget | Child attempt, parent checksum, budget consumption, superseded lineage, no-progress tests. | SOURCE CODE |
| completion reconciliation | All route stage/gates; supersedes older repair after later success; keeps active repair blocking when incomplete. | SOURCE CODE |
| repair application | Safe preimage/path, dependency exact stage plan, no package.json unified diff, proposer/reviewer schemas, stale/tampered artifacts, force/lockfile protection. | SOURCE CODE |
| continuation/worker | Single-owner claim, expired claim, durable wait/wake/cancel, command recovery, worker wake. | SOURCE CODE |
| frontend | frontend/src/components/TransformationPanel.test.tsx cases for empty/planning/waiting gates, evidence, seal chain, and repair actions. | SOURCE CODE |

Before merge, add a direct regression for an orphan executing repair plus a completed continuation, the six-checkpoint FK shape, clearing waiting_execution_id/last_error at terminal completion, and delivery materialization. No test command was executed in this audit.

## 35. Schemas and contracts

The following are compact contracts; the persisted models in backend/app/repositories/models/workflow.py are authoritative for fields and relationships.

| Contract | Required content/authority | Lifecycle binding | Source |
|---|---|---|---|
| RepairProposal | Typed operation(s), diagnosis/route, rationale, preimage/context, validation targets, plan/stage/fingerprint/checksum binding. | Proposer artifact -> reviewer -> G10. | SOURCE CODE / IMMUTABLE ARTIFACT |
| RepairOperation | replace_text, create_text_file, delete_text_file, dependency_change, dependency_add, dependency_transition; each has operation-specific governed fields. | Applied only through RepairApplicationService. | SOURCE CODE |
| RepairReview | accept/request_changes/reject, causal concerns, limitations, validation targets, proposal checksum. | Independent reviewer -> G10. | SOURCE CODE / IMMUTABLE ARTIFACT |
| FailureEvidence | Normalized command failure, code/message/context, command/artifact references, failure fingerprint. | Failure -> classifier/repair. | SOURCE CODE / IMMUTABLE ARTIFACT |
| FailureRoute | Supported diagnosis/route such as peer conflict, repairable source, dependency add/change, no-progress, terminal block. | Classifier -> node selection. | SOURCE CODE / DATABASE |
| DependencyAdditionIntent/policy result | Registry package grammar, dependencies/devDependencies section, semver intent/range, policy version; no exact-version resolution. | Proposal -> G10 -> lock/install observation. | SOURCE CODE |
| Command policy request | Template/intent, executable/args, plan/stage, alias, runtime/network, expected state, idempotency/request checksum. | Policy -> authorization audit. | SOURCE CODE |
| Command authorization | Accepted/rejected decision, reasons, policy/template versions, actor, bindings and request hash. | Must precede execution. | SOURCE CODE / DATABASE |
| Command execution | Durable intent/status/claim/process/result/log/fingerprint/lineage/recovery fields. | Authorization -> worker -> wake. | SOURCE CODE / DATABASE |
| Stage gate package | Gate id/version/status, artifact set/package checksum, plan/stage plan, expected state, workspace fingerprint. | Package -> decision. | SOURCE CODE / DATABASE |
| Gate decision | Decision, actor/comment, idempotency/request checksum, expected version, package/workspace binding, reason. | Human -> next node. | SOURCE CODE / DATABASE |
| Continuation | Thread/current node/status, current stage, plan/G06 checksums, leases, wake sequence, state/error/cancel fields. | Worker cursor. | SOURCE CODE / DATABASE |
| Repair attempt | Monotonic attempt number/status, checkpoint/failure fingerprint, proposer/reviewer/apply/validation artifacts, parent lineage, state and budget fields. | Repair lifecycle. | SOURCE CODE / DATABASE |
| Artifact envelope | Artifact id, safe relative path, type/schema, SHA-256, run/stage/owner/execution, size/finalization/immutable/redaction metadata. | Evidence store. | SOURCE CODE / DATABASE |
| Workspace binding/checkpoint/seal manifest | Alias/path, input/current fingerprints, source checkpoint, safe resume, manifest/seal/chain checksums, previous seal and validation bindings. | Stage lineage. | SOURCE CODE / DATABASE / IMMUTABLE ARTIFACT |

## 36. Required sequence diagrams

The handoff contains the following Mermaid diagrams: full route, worker loop, command authorization, normal stage, repair, dependency_transition, dependency_add, request changes, restart/recovery, seal/next-stage/completion, plus the ER model in section 2 and architecture/state diagrams above.

### 36.1 Full Angular route

~~~mermaid
sequenceDiagram
    participant S as Source 18
    participant W19 as Stage 18-to-19
    participant W20 as Stage 19-to-20
    participant W21 as Stage 20-to-21
    participant Z as SealingFlow
    S->>W19: snapshot and bind
    W19->>Z: validate, G11, seal
    Z->>W20: materialize sealed 19 input
    W20->>Z: validate, G11, seal
    Z->>W21: materialize sealed 20 input
    W21->>Z: validate, G11, seal
    Z->>Z: STAGED_MIGRATION_COMPLETED
    Z->>Z: COMPLETED and terminal
~~~

### 36.2 Worker/continuation loop

~~~mermaid
flowchart TD
    A[Poll] --> B{Authorized command claim?}
    B -- yes --> C[CommandExecutorService]
    C --> D[ExecutionWorker]
    D --> E[Persist result and wake waiter]
    B -- no --> F{Continuation claim?}
    F -- no --> A
    F -- yes --> G[Dispatch current_node]
    G --> H{Waiting condition?}
    H -- yes --> I[Persist waiting state]
    H -- no --> J[Advance or complete]
    I --> A
    J --> A
    C -. expired mutating claim .-> K[Reconstruct checkpoint]
    K --> A
~~~

### 36.3 Command authorization and execution

~~~mermaid
sequenceDiagram
    participant N as Deterministic node
    participant R as Registry and policy
    participant A as Authorization audit
    participant Q as CommandExecution
    participant X as ExecutionWorker
    participant P as Process
    N->>R: render template and exact args
    R->>A: accept with policy/template/checksum bindings
    A->>Q: queue authorized command
    Q->>X: claim with lease
    X->>P: Popen shell false
    P-->>X: stdout/stderr/exit
    X->>Q: persist logs, result, fingerprint
    Q-->>N: wake continuation
~~~

### 36.4 Normal successful stage

~~~mermaid
sequenceDiagram
    participant C as Continuation
    participant G as GateService
    participant E as Executor
    participant V as ValidationRunner
    participant S as SealingFlow
    C->>G: create and wait G07
    G-->>C: G07 approved
    C->>E: bootstrap npm ci
    C->>E: Angular update
    C->>E: version verify
    C->>G: create and wait G08
    G-->>C: G08 approved
    C->>V: final_install, build, test
    V-->>C: validation summary passed
    C->>G: create and wait G11
    G-->>C: G11 approved
    C->>S: seal stage
~~~

### 36.5 Failure to repair to G11

~~~mermaid
sequenceDiagram
    participant E as CommandExecutor
    participant F as FailureEvidence
    participant P as Proposer
    participant R as Reviewer
    participant H as Human
    participant A as Apply and validate
    E-->>F: nonzero or timeout
    F->>P: frozen context and fingerprint
    P-->>R: typed proposal and candidate diff
    R-->>H: accept, concerns, or request_changes
    H->>A: G10 approve bound package
    A->>A: apply and materialize
    A->>A: affected and full validation
    A-->>H: G11 package
    H->>A: G11 approve
~~~

### 36.6 dependency_transition

~~~mermaid
sequenceDiagram
    participant C as Continuation
    participant T as TransitionRunner
    participant E as Executor
    participant V as ClosureVerifier
    C->>T: peer blocker and approved transition
    T->>E: uninstall/detach
    T->>E: Angular update retry
    T->>E: normalize lockfile if required
    T->>E: reinstall compatible bundle
    T->>E: npm ci
    T->>V: manifest lock installed closure
    V-->>C: agree or route failure
~~~

### 36.7 dependency_add

~~~mermaid
sequenceDiagram
    participant L as LLM proposer
    participant P as AdditionPolicy
    participant H as G10 human
    participant A as ApplyService
    participant N as npm
    participant V as ClosureVerifier
    L->>P: package section semver intent
    P-->>H: governed candidate diff
    H->>A: approve manifest intent
    A->>N: package-lock-only generation
    N-->>A: exact resolved lock version
    A->>N: npm ci
    N-->>V: installed exact version
    V-->>H: closure and G11 evidence
~~~

### 36.8 Human Request changes

~~~mermaid
sequenceDiagram
    participant H as Human
    participant API as Transformation API
    participant S as StateTransitionService
    participant L as RepairLifecycle
    participant P as Proposer
    H->>API: POST revisions with parent checksums
    API->>S: CAS and idempotent child request
    S->>L: preserve parent lineage
    L-->>P: child attempt context
    P-->>H: revised proposal
    H->>API: G10 decision for child
~~~

### 36.9 Restart and recovery

~~~mermaid
flowchart TD
    A[Worker or backend restarts] --> B[Read continuation and commands]
    B --> C{Expired claim or interrupted mutation?}
    C -- no --> D[Claim with CAS and continue]
    C -- yes --> E[Restore safe checkpoint]
    E --> F[Record reconstruction]
    F --> G[Create bounded successor if needed]
    G --> D
    D --> H[Wake or wait durably]
~~~

### 36.10 Seal, next stage, and complete

~~~mermaid
sequenceDiagram
    participant V as Validation
    participant H as G11 human
    participant S as SealingFlow
    participant N as NextStage
    participant R as Run
    V->>H: validation and fingerprint package
    H->>S: approve G11
    S->>S: clean context and chain-bound seal
    S->>N: materialize next-stage input
    N-->>S: next stage sealed
    S->>R: STAGED_MIGRATION_COMPLETED
    R->>R: COMPLETED
~~~

## 37. Directory structure

### 37.1 Source repository

    backend/app/
    +-- api/
    |   +-- routes/transformation.py
    |   +-- routes/runs.py
    |   +-- routes/run_commands.py
    |   +-- routes/artifacts.py
    +-- artifact_store/local_store.py
    +-- command_execution/worker.py
    +-- domain/command.py
    +-- domain/transformation.py
    +-- llm_gateway/
    |   +-- azure_gateway.py
    |   +-- contracts.py
    |   +-- redaction.py
    +-- orchestration/
    |   +-- transformer_worker.py
    |   +-- transformer_graph.py
    |   +-- transformer_sealing_flow.py
    +-- repositories/models/workflow.py
    +-- services/
    |   +-- command_executor_service.py
    |   +-- command_registry_service.py
    |   +-- dependency_addition_policy.py
    |   +-- dependency_closure_service.py
    |   +-- dependency_transition_runner.py
    |   +-- failure_evidence_service.py
    |   +-- lockfile_generation_runner.py
    |   +-- migration_workspace_layout_service.py
    |   +-- patch_apply_service.py
    |   +-- repair_application_service.py
    |   +-- repair_lifecycle_service.py
    |   +-- stage_gate_service.py
    |   +-- validation_runner.py
    |   +-- transformer_stage_service.py
    +-- state/transition_service.py
    +-- core/config.py
    +-- core/database.py
    frontend/src/
    +-- api/transformation.ts
    +-- hooks/useTransformation.ts
    +-- types/transformation.ts
    +-- components/TransformationPanel.tsx
    +-- components/TransformationSections.tsx

### 37.2 Runtime run root

    run-80ee6328670b/
    +-- artifacts/
    |   +-- 00_job_setup/
    |   +-- 04_workflow_state/
    |   |   +-- authorization/
    |   |   +-- command_executions/
    |   |   +-- command_logs/
    |   |   +-- stages/
    |   +-- 05_repairs/
    |   +-- 06_validation/
    |   +-- global/execution-profile/
    |   +-- global/source-snapshots/snapshot-955d71c32b7d/
    |   +-- stages/
    +-- baseline-sandbox/
    +-- source-snapshot/
    +-- stage-sandboxes/
    +-- temporary/
    +-- logs/
    +-- reports/
    +-- delivery-candidate/       (recorded, absent)
    +-- final-assurance-sandbox/  (recorded layout, absent)

artifacts/00_job_setup describes roots and aliases. global contains run-wide source/runtime evidence. 04_workflow_state contains command/gate/stage evidence. 05_repairs contains proposal/review/apply lineage. 06_validation contains validation summaries. stage sandboxes are mutable execution workspaces; sealed outputs are immutable lineage outputs. logs/reports are run-level containers. The output layout records MIGRATED_APP under the target root, but the observed directory is absent.

## 38. New developer: where to start

Recommended reading order:

1. AGENT.md for authority, safety, and mutation rules.
2. backend/app/domain/transformation.py for node/status vocabulary.
3. backend/app/orchestration/transformer_worker.py for the polling/claim loop.
4. backend/app/orchestration/transformer_graph.py for node dispatch and service boundaries.
5. backend/app/services/transformer_stage_service.py and stage_execution_application_service.py for stage flow.
6. backend/app/services/command_registry_service.py, command_executor_service.py, and command_execution/worker.py for the only subprocess path.
7. backend/app/state/transition_service.py and repositories/models/workflow.py for CAS/event/schema authority.
8. backend/app/services/repair_lifecycle_service.py and repair_application_service.py for repair lineage/application.
9. dependency_transition_runner.py, dependency_addition_policy.py, dependency_closure_service.py, and lockfile_generation_runner.py for dependency routes.
10. stage_gate_service.py and transformer_sealing_flow.py for G10/G11/seal/completion.
11. llm_gateway/* and transformer_prompt_service.py for proposer/reviewer boundaries.
12. transformation.py API routes and frontend TransformationPanel/Sections/types for projection/human action.
13. This run's 00_job_setup, execution-profile, 04_workflow_state, 05_repairs, 06_validation, and seal artifacts for runtime proof.

Start with the DB continuation and stage rows, then follow its artifact IDs to immutable evidence. Do not begin with a frontend screenshot or a stale run-level phase field.

## 39. Operational runbook

The repository contains current operational scripts, but they were not executed in this audit:

| Operation | Repository evidence | Safe operational note | Source |
|---|---|---|---|
| Backend/API and Transformer worker | scripts/dev-backend.ps1 | Starts API/worker using configured data/output roots; inspect environment before use. | SOURCE CODE |
| Fresh proof setup | run-fresh-backend.ps1 | Creates a fresh local application-data root and target layout; use only for an authorized new proof run. | SOURCE CODE |
| Frontend | frontend package scripts/configuration | Start through the repository's documented frontend command after confirming target API/config; not run here. | SOURCE CODE |
| TargetRoot | run-fresh-backend.ps1 and output layout configuration | Supply the externally scoped target parent/output policy; do not point at the repository or source tree. | SOURCE CODE |
| Locate DB | startup data-root provenance -> application data root -> control-tower.db | Derive the path for the specific run; do not assume the repository .env is current. | SOURCE CODE / DATABASE |
| Locate artifacts | migration_runs.artifact_root and output_layout.json | Use artifact_metadata relative_path and checksum; do not edit files. | DATABASE / IMMUTABLE ARTIFACT |
| Inspect events | workflow_events ordered by run sequence or GET /runs/{run_id}/events | Resume from sequence/Last-Event-ID for an ordered view. | SOURCE CODE / DATABASE |
| Stop/restart worker | durable lease/recovery path in TransformerWorker/CommandExecutorService | Stop only through the authorized process/service operation; after restart inspect leases, commands, checkpoints, and reconstruction records before resuming. | SOURCE CODE |

No secret value, token, credential, or private provider payload is included in this handoff. Do not copy backend .env contents into tickets or logs.

## 40. Debugging runbook

| Symptom | Inspect first | Source service/event | Likely interpretation |
|---|---|---|---|
| UI says Blocked | transformation_continuations.status/current_node, last_error; latest stage_gate_decisions; failure/route artifacts. | Transformer graph, StageGateService, classify_failure; BLOCKED/terminal events. | Policy/repair budget/checksum/human rejection, not necessarily a process failure. |
| Command failed | command_executions status/exit/failure_code, command_log_summary/chunks, authorization audit. | CommandExecutor/ExecutionWorker; COMMAND_FAILED/COMMAND_SUCCEEDED. | Normalize failure before choosing repair. |
| No command projected | continuation current_node/waiting_execution_id, command executions by run/stage, active lease. | TransformerWorker; CONTINUATION_WAITING/RESUMED. | Worker has not queued, command is terminal/stale, or projection is stale. |
| Worker repeatedly claims | continuation state_version/wake_sequence/lease, command claim_attempt/claim_expires_at. | TransformationContinuationService/CommandExecutor. | CAS contention, expiry, or a non-idempotent transition bug. |
| waiting_gate | stage_gate_packages/decisions, package checksum, expected state, workspace fingerprint. | StageGateService; G07/G08/G10/G11_CREATED/APPROVED. | Human decision absent, stale, rejected, or not bound to current evidence. |
| G10 unavailable | repair_attempt status, proposal/review/apply artifacts, current fingerprint, gate package. | RepairApplicationService/causal_review. | Proposal incomplete, reviewer concerns, stale lineage, or no supported route. |
| G11 unavailable | validation summary, final install/build/test executions, dependency closure/version evidence, fingerprint. | ValidationRunner/SealingFlow. | Post-state evidence incomplete or changed after package creation. |
| Repair stuck | repair_attempt status/attempt_number/parent, llm_invocations, gate decisions, continuation node. | RepairLifecycleService; REPAIR/LLM/G10 events. | Active status, request_changes child, provider failure, or stale lifecycle residue. |
| Lockfile generation stuck | lockfile step, command execution, package/lock checksums, binding fingerprint, successor idempotency. | LockfileGenerationRunner; reconstruction/successor events. | V1 stale proof, V2 successor, shrinkwrap/volatile-scope rejection, or CAS conflict. |
| Validation repeats | StageStepModel attempt/idempotency keys, parent/child command lineage, workspace fingerprint, validation summary. | ValidationRunner/recovery; COMMAND_FAILED and continuation resumed events. | Old node_modules or stale validation key; verify npm ci materialization first. |
| Completion blocked | all route stage statuses/seals, required gates, ACTIVE_REPAIR_STATUSES rows, active command/prompt. | TransformerSealingFlow; STAGED_MIGRATION_COMPLETED absent. | A real invariant failure or lifecycle projection gap. |
| Frontend looks stale | GET /transformation response, refresh error, event sequence/Last-Event-ID, stale projection fields. | useTransformation; workflow_events. | UI deliberately preserved last projection or backend fields were not cleared. |

For every incident, correlate DB row -> artifact checksum -> workspace fingerprint -> workflow event sequence. Do not use a log line alone as authority.

## 41. Source-of-truth matrix

| Question | Authoritative source | Supporting evidence | Source label |
|---|---|---|---|
| Current workflow state | transformation_continuations | StateTransitionService/events | DATABASE / SOURCE CODE |
| Current stage | continuation.current_stage_id plus migration_stages | Stage bindings/checkpoints | DATABASE |
| Legal run transition | StateTransitionService._LEGAL_RUN_TRANSITIONS | workflow_events | SOURCE CODE / DATABASE |
| Current command | command_executions | active-command route, logs, lease | DATABASE |
| Command permission | command_authorization_audits | template/policy artifact | DATABASE / IMMUTABLE ARTIFACT |
| Repair proposal | proposal artifact bound to repair_attempt | failure context/fingerprint | IMMUTABLE ARTIFACT / DATABASE |
| Reviewer result | review artifact and repair_attempt reviewer reference | proposal checksum | IMMUTABLE ARTIFACT / DATABASE |
| Human approval | stage_gate_packages plus stage_gate_decisions | expected state/package/workspace checksum | DATABASE / IMMUTABLE ARTIFACT |
| Workspace identity | stage_workspace_bindings | checkpoint and fingerprint | DATABASE / WORKSPACE |
| Version | version-verification artifact plus package/lock/installed/CLI evidence | runtime profile | IMMUTABLE ARTIFACT |
| Validation | command executions plus validation summary | StageStepModel | DATABASE / IMMUTABLE ARTIFACT |
| Failure route | normalized failure evidence/fingerprint and route record | causal review | IMMUTABLE ARTIFACT / DATABASE |
| LLM provenance | llm_invocations and invocation artifacts | prompt/schema/input hashes | DATABASE / IMMUTABLE ARTIFACT |
| Final stage output | sealed checkpoint plus output manifest and seal.json | chain hash/fingerprint | DATABASE / IMMUTABLE ARTIFACT |
| Final delivery | durable delivery record plus existing target/delivery workspace | delivery artifact/checksum | DATABASE / WORKSPACE |
| Live operator view | backend transformation projection | event stream and command stream | SOURCE CODE / DATABASE |

The most important practical rule is: a stale run-level projection cannot overrule a current stage seal, and a stage seal cannot overrule the absence of a delivery artifact when the question is publication.

## 42. Final architectural assessment

### What is now proven

- The current source has a durable Transformer worker/continuation architecture with SQL state, CAS, leases, command lineage, checkpoints, typed repairs, gates, validation, and chain-bound stage sealing.
- run-80ee6328670b completed the Angular 18 -> 19 -> 20 -> 21 route.
- All three route stages are sealed with final fingerprints, output manifests, validation summaries, approved G07/G08/G11 evidence, and repair lineage.
- The final Angular 21 stage passed final npm ci, build, and tests on the persisted Node 22.23.1/npm 10.9.8 profile.
- Command authorization, immutable artifact verification, reviewer/human gates, and four durable workspace reconstructions are evidenced.

### What remains deterministic backend authority

State transitions, command policy/rendering, exact execution, workspace confinement, fingerprints, repair application, dependency closure, version verification, lockfile scope, validation aggregation, gate binding, seal eligibility, and final completion invariants.

### What remains LLM-driven

Structured analysis/repair diagnosis, typed candidate operations, explanations, and independent review decisions within the prompt/schema/policy boundary. The LLM does not choose arbitrary commands or exact package-lock resolutions.

### What remains human-controlled

Run/planning approvals where required, G10 repair approval/rejection/revision, prompt decisions, and G11 post-state/seal approval.

### What remains static/hardcoded intentionally

Command registry templates, legal transformation nodes/statuses, compatibility catalogue/registry snapshots, _COMPATIBLE_REINSTALL_BUNDLES for known dependency transitions, operation schemas, policy versions, and validation route requirements.

### What remains dynamic

Source/project inventory, selected runtime profile evidence, LLM repair intent, semver intent for dependency_add/change, npm lockfile resolution, installed closure, failure fingerprints, workspace fingerprints, and stage/repair lineage.

### What is still technical debt

The orphan executing repair and incomplete ACTIVE_REPAIR_STATUSES, six broken checkpoint foreign keys, stale continuation/run projections, pending historical steps/gates, absent assurance rows, expired leases, missing dedicated dependency-add verification artifact, absent delivery materialization, historical --allow-dirty governance conflict, and concentrated large orchestration/service modules. These are not hidden by the successful E2E.

### What is required before merging this branch

At minimum, reconcile the --allow-dirty template against AGENT.md, add lifecycle/delivery/FK/projection regressions, decide how pending optional steps are represented, and standardize dependency-add verification artifact emission. Preserve the proof run as immutable evidence; perform any database repair only through a separately reviewed migration on the intended environment.

### What is required before calling the Transformer production-ready

Prove external delivery materialization/publication with a durable delivery record; make completion fail closed for every active repair status; cleanly reconcile leases and stale projection fields; resolve checkpoint FK integrity; define the assurance projection contract; validate the command template governance conflict; and run a fresh authorized E2E plus focused regression suite with no known contract gaps.

**Final assessment: E2E transformer route proven; implementation is handoff-ready with explicit correctness and delivery debt; production-ready and delivered claims are not justified by this run alone.**

## 43. Document quality and evidence boundaries

This handoff is intended to stand alone for a senior engineer. It distinguishes:

- **CURRENT DESIGN:** source ownership, contracts, nodes, services, API, and frontend projection.
- **PROVEN RUNTIME:** database/artifact/workspace/event facts from run-80ee6328670b.
- **HISTORICAL FIX:** E2E hardening defects with a generic fix and current status.
- **KNOWN DEBT:** conflicts or omissions still visible in current source/runtime.

The primary proof is run-80ee6328670b. The older run run-d3d0222baf58 is intentionally not used as proof and is not needed to establish the route described here. If it is consulted later for historical comparison, it must remain labelled historical and cannot override the latest run.

No secrets are included. Provider credentials, tokens, raw .env values, and unredacted provider payloads were excluded. Artifact paths and IDs are included only where they help a future engineer follow immutable provenance.

## 44. Validation performed before handoff

The document was written after the read-only investigation and validated by:

- checking the repository root, expected branch, marker HEAD, and pre-write clean status;
- confirming all named major production files exist;
- confirming named classes/functions through source inspection;
- checking that run-80ee6328670b, not the old run, is used as primary proof;
- checking run artifact metadata/checksum/file presence without mutation;
- checking Mermaid fence balance and diagram shape;
- checking for credential/token values and excluding secrets;
- checking git status and the handoff-specific diff without staging.

No tests, pytest, npm install, npm ci, build, frontend/backend service, Transformer worker, migration resume, database write, artifact mutation, commit, or push was performed.

## 45. Handoff conclusion

The next engineer can safely start with the durable continuation and stage rows, follow the artifact/checksum bindings, read the Transformer worker and graph dispatch, then inspect repair/gate/seal services. The decisive conclusion is:

**run-80ee6328670b proves the Transformer can migrate and seal Angular 18 -> 19 -> 20 -> 21 with governed repair and successful final validation. It does not prove final delivery/publication, and the recorded lifecycle/FK/projection/governance debt must be resolved before a production-ready claim.**
