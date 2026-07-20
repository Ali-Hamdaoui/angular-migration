# AMFA-170 Implementation Audit

## 1. Audit Metadata and Preflight

Branch: hermes/02-stage-workspace-bootstrap
HEAD: 94065a498e0180ba980bbc0cd8209c6719dac749
Expected 94065a4 resolution: 94065a498e0180ba980bbc0cd8209c6719dac749
Upstream: origin/hermes/02-stage-workspace-bootstrap
Ahead/behind: 0 / 0
Sprint blob: 4c9a17670ce6d988bdcad48d43e805dbf9a0c53e
Reviewed baseline blob: cd793cf4fa81a92467fe963a4b984f5c74509fab
Initial tree: clean
Root authority: AGENTS.md only
Report existed before audit: False

All mandatory commands exited 0. Exact observed output:
git branch --show-current -> hermes/02-stage-workspace-bootstrap
git status --porcelain=v1 -uall -> empty output
git rev-parse HEAD -> 94065a498e0180ba980bbc0cd8209c6719dac749
git rev-parse '94065a4^{commit}' -> 94065a498e0180ba980bbc0cd8209c6719dac749
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' -> origin/hermes/02-stage-workspace-bootstrap
git rev-list --left-right --count 'HEAD...@{u}' -> 0 0
git log -1 --decorate --oneline -> 94065a4 (HEAD -> hermes/02-stage-workspace-bootstrap, origin/hermes/02-stage-workspace-bootstrap) docs: add reviewed repository audit baseline
git hash-object docs/sprint.md -> 4c9a17670ce6d988bdcad48d43e805dbf9a0c53e
git hash-object docs/audits/00_REPOSITORY_AUDIT_BASELINE.md -> cd793cf4fa81a92467fe963a4b984f5c74509fab
git ls-files AGENT.md AGENTS.md -> AGENTS.md
Test-Path docs/audits/01_AMFA-170_IMPLEMENTATION_AUDIT.md -> False

## 2. Scope, Non-Goals, and Source Hierarchy

Audit-only scope: AMFA-170. No production code, tests, migrations, configuration, dependencies, generated files, requirements, instructions, baseline, or other audit reports were changed. AMFA-110, AMFA-143, AMFA-171, and AMFA-173 completion was not assessed.

Authority order: docs/sprint.md; AGENTS.md; actual implementation; reviewed baseline as navigation; other documentation as navigation. Names, status, filenames, comments, test names, and documents are not proof.

## 3. Targeted Inputs Read

Read completely: AGENTS.md:1-410.
Read sprint only: docs/sprint.md:14-28, 32-104, 105-153, 577-602, 606-632.
Reused baseline only: sections 1-4, 7-11, 14-18, and the AMFA-170 requirements-index row at line 270.
No more-specific AGENTS.md exists.

## 4. Freshness and Baseline Reuse Decision

HEAD is the expected reviewed-baseline commit and the baseline blob matches the pinned hash. The reviewed source map was reused. Targeted reinspection covered the AMFA-170 service/domain/routes/models, workspace and sandbox paths, active-plan/G06 and Transition Service boundaries, and focused tests. Repository-wide orientation was not repeated.

## 5. Exact AMFA-170 Requirement Decomposition

These are faithful decompositions of docs/sprint.md:105-153, not invented requirements.

| ID | Requirement excerpt | Source and authority |
|---|---|---|
| AMFA-170-R01 | Authoritative stage-start path from current input verification through G07 and isolated sandbox readiness. | docs/sprint.md:113-115; stage/G07/workspace/Transition Service |
| AMFA-170-R02 | Current-version re-detection. | docs/sprint.md:117-118; deterministic input authority |
| AMFA-170-R03 | Exact current-stage resolution hook. | docs/sprint.md:117-119; active S2-F07 plan |
| AMFA-170-R04 | Active StageExecutionPlan lock. | docs/sprint.md:117-120; planning persistence |
| AMFA-170-R05 | Stage-start evidence package. | docs/sprint.md:117-120; artifact boundary |
| AMFA-170-R06 | Persistent G07 rules. | docs/sprint.md:117-120; G07 model/service/events |
| AMFA-170-R07 | Lease conflict checks. | docs/sprint.md:117-120; Transition Service lease authority |
| AMFA-170-R08 | WorkspaceManager physical copy. | docs/sprint.md:117-120; registered workspace authority |
| AMFA-170-R09 | Input and sandbox fingerprint verification. | docs/sprint.md:117-120; fingerprint/evidence authority |
| AMFA-170-R10 | Source-safety validation. | docs/sprint.md:117-120; path/link/source authority |
| AMFA-170-R11 | G07 binds state version, gate version, artifact-set checksum, active plan/profile, and input fingerprint; invalid G07 blocks sandbox creation; LangGraph coordinates, WorkspaceManager copies, and Transition Service changes state. | docs/sprint.md:122-125; fail-closed backend boundary |
| AMFA-170-R12 | Tests cover the listed prior-input, drift, duplicate, collision, interruption, lease, escape, mutation, stale replay, and restart scenarios. | docs/sprint.md:127-143; executable proof |

## 6. Requirement Verdict Matrix

| ID | Status | Proof | Ownership | Finding |
|---|---|---|---|---|
| AMFA-170-R01 | PARTIALLY_IMPLEMENTED | STATIC_CODE_TRACE | AMFA-170_LOCAL | Stage events, copy, G07 scaffolding, and responses exist; authoritative plan/G06 resolution and gate-before-ready path do not. |
| AMFA-170-R02 | MISSING | NO_EVIDENCE | AMFA-170_LOCAL | No current-version re-detection call/symbol found in inspected stage paths. |
| AMFA-170-R03 | MISSING | STATIC_CODE_TRACE | AMFA-170_LOCAL | Request values are used; active-plan resolver is not called. |
| AMFA-170-R04 | INCORRECT | STATIC_CODE_TRACE | AMFA-170_LOCAL | Local StageExecutionPlan is constructed instead of selecting ActivePlanVersionModel/StageExecutionPlanModel. |
| AMFA-170-R05 | PARTIALLY_IMPLEMENTED | STATIC_CODE_TRACE | AMFA-170_LOCAL | Copy evidence exists, but package plan data is reconstructed from stage/workspace fields. |
| AMFA-170-R06 | PARTIALLY_IMPLEMENTED | STATIC_CODE_TRACE | AMFA-170_LOCAL | G07 model/builder/decision/routes/events exist; current binding, expiry, and stale invalidation are not enforced. |
| AMFA-170-R07 | MISSING | NO_EVIDENCE | AMFA-170_LOCAL | Lease methods exist but prepare/sandbox/G07 never call them. |
| AMFA-170-R08 | PARTIALLY_IMPLEMENTED | STATIC_CODE_TRACE | AMFA-170_LOCAL | Direct copytree exists, bypassing registered workspace authority and recovery controls. |
| AMFA-170-R09 | PARTIALLY_IMPLEMENTED | STATIC_CODE_TRACE | AMFA-170_LOCAL | Fingerprints compare, but hash names only and persist zero counts/sizes. |
| AMFA-170-R10 | INCORRECT | STATIC_CODE_TRACE | AMFA-170_LOCAL | Links are preserved; containment and source-mutation checks are absent. |
| AMFA-170-R11 | INCORRECT | STATIC_CODE_TRACE | AMFA-170_LOCAL | create_sandbox never reads G07; package plan/profile are not authoritative; code emits STAGE_PREPARING while sprint names PREPARING. |
| AMFA-170-R12 | PARTIALLY_IMPLEMENTED | EXISTING_TEST_NOT_EXECUTED | AMFA-170_LOCAL | Basic tests exist, but most listed negatives are absent. The focused pytest command failed during collection before test execution because `sqlalchemy` was unavailable; this is recorded separately as an environment limitation. |

## 7. Backend End-to-End Static Trace

HTTP prepare: backend/app/api/routes/stages.py:30-35 prepare_stage -> StagePrepareRequest -> StagePreparationApplicationService.

Preparation: backend/app/services/stage_preparation_service.py:68-90 checks run and state then creates a random MigrationStageModel. Lines 92-102 build a local plan from request values. This is the first broken link: no active plan or G06 resolution and no durable lock.

Transitions: lines 104-129 call StateTransitionService for STAGE_CREATED and STAGE_PREPARING. StateTransitionService.apply_transition at backend/app/state/transition_service.py:69-115 owns run state version and event append.

Sandbox HTTP: backend/app/api/routes/stages.py:38-43 -> StageSandboxRequest -> create_sandbox. Lines 145-179 replay an existing workspace by run/stage but do not revalidate request, plan, G06, or physical contents. Lines 181-198 derive destination and select newest SourceSnapshotModel or run.source_path.

Copy: lines 200-205 call direct shutil.copytree with symlinks preserved. There is no containment, atomic publication, cancellation, cleanup, or source mutation comparison. Lines 207-229 compute name-only fingerprints and verification; lines 231-258 write workspace_copy_report.json and metadata. Lines 260-306 emit STAGE_PLAN_LOCKED and STAGE_WAITING_APPROVAL and persist StageWorkspaceModel.

G07: lines 341-403 reconstruct a plan with hard-coded npm-ci and workspace.policy_version, then build a checksum package. Lines 405-469 emit G07 events and persist G07ApprovalModel. Approved G07 changes the stage to sandbox_ready, but sandbox copying already happened and create_sandbox never checks G07. The end-to-end trace is therefore broken at active-plan/G06 resolution and at the gate precondition.

## 8. Active Plan and G06 Dependency Consumption

The upstream active-plan resolver exists at backend/app/services/planning_review_evidence_application_service.py:797-824. It reads ActivePlanVersionModel, MigrationPlanModel, and StageExecutionPlanModel; _require_active_binding at :826-834 checks plan checksum, stage checksum, and plan version. Models are backend/app/repositories/planning_models.py:12-64,80-91.

The upstream G06 authority exists at backend/app/services/planning_review_application_service.py:367-447. It validates pending status, gate/package/artifact/plan/stage-plan/workspace bindings and rejects missing approval or stale bindings.

AMFA-170 consumes neither. StagePrepareRequest at backend/app/api/stage_contracts.py:12-20 carries request-derived families and plan_version. prepare_stage at backend/app/services/stage_preparation_service.py:92-102 constructs a separate plan. decide_g07 at :367-381 reconstructs another plan, hard-codes npm-ci, and uses workspace.policy_version. This is a local AMFA-170 bypass of available upstream authority, not an AMFA-110 absence.

## 9. Stage State and Transition Authority

The sprint names PREPARING at docs/sprint.md:46-52. Code defines StageStatus.PREPARING = preparing at backend/app/domain/contracts.py:83-92 but emits WorkflowEventType.STAGE_PREPARING = STAGE_PREPARING at :357-362. The service directly assigns stage status at backend/app/services/stage_preparation_service.py:79-86,295-297,454-456 instead of passing next_stage_status through Transition Service.

The observed event sequence is STAGE_CREATED -> STAGE_PREPARING -> STAGE_PLAN_LOCKED -> STAGE_WAITING_APPROVAL -> G07_CREATED -> G07_APPROVED -> STAGE_SANDBOX_READY. Transition Service owns durable run state/events, but this is not a valid gate sequence because copy occurs before G07 lookup/decision.

## 10. G07 Package and Decision Boundary

Implemented scaffolding: G07ApprovalPackageBuilder checksum at backend/app/domain/stage_workspace.py:143-184; decision vocabulary and checksum rejection at :186-217; durable G07ApprovalModel at backend/app/repositories/stage_workspace_models.py:12-38; routes at backend/app/api/routes/stages.py:46-66.

Defects: package plan data is reconstructed; exact source/target/profile/approved commands are absent; active G06 is not validated; expiry/stale invalidation is absent; create_sandbox ignores G07; and replay at backend/app/services/stage_preparation_service.py:333-339 does not validate changed bindings. AMFA-171 completion is not assessed.

## 11. Workspace and Sandbox Creation

backend/app/workspaces/services.py:23-47 provides WorkspaceService and non-overlap validation. `backend/app/workspaces/baseline.py:BaselineSandboxService` provides registered-root containment, unsafe-link rejection, temporary publication, cancellation cleanup, and reconstruction. The workspace and sandbox README guidance states new mutation behavior must use dedicated workspace modules.

AMFA-170 uses direct copytree at backend/app/services/stage_preparation_service.py:200-205. Symlinks are preserved; containment/non-overlap is absent; collisions are checked non-atomically; partial copy is not cleaned; cancellation/restart is absent; source mutation is not checked; and fingerprints are names-only. This is CONFIRMED_BYPASS, AMFA-170_LOCAL.

The resolved implementation authority is the existing `backend/app/workspaces/baseline.py:BaselineSandboxService`, reused through a thin stage adapter/coordinator in `StagePreparationApplicationService`. `WorkspaceService` in `backend/app/workspaces/services.py` remains the registered workspace boundary and its non-overlap/alias concepts are reused. `BaselineSandboxService` supplies registered-root containment, source-boundary fingerprint verification, unsafe-link rejection, temporary publication, cancellation cleanup, and reconstruction. AMFA-170 must add only stage-specific orchestration: resolve the authoritative snapshot, pass the approved input fingerprint and registered run root, persist the returned copy evidence, and coordinate Transition Service/G07 state. The prohibited path is direct `shutil.copytree` (or another stage-local copier) in `stage_preparation_service.py`; no competing third copy authority is permitted.

The fingerprint boundary is intentionally split. Before copy, the G07 package binds state version, gate version, artifact-set checksum, active plan/profile, authoritative input-workspace or source-snapshot fingerprint, and the intended registered destination identity when that identity is part of the package contract. The resulting sandbox fingerprint cannot be a pre-copy G07 prerequisite. After approved G07, `BaselineSandboxService` performs the copy; AMFA-170 calculates and verifies the sandbox fingerprint, persists post-copy verification evidence, and emits `SANDBOX_READY` only after successful verification. AMFA-144 supplies the broader workspace-fingerprint context; AMFA-170 explicitly requires the input fingerprint at the G07 authorization boundary and input/sandbox fingerprint verification across the complete operation.

## 12. Idempotency, Replay, Lease, and Cancellation

Prepare has no idempotency lookup and creates a random stage each call. Sandbox replay is run/stage based but does not validate request, current plan, G07, or physical contents. G07 replay is run/idempotency-key based but does not compare payload identity or current bindings. Expected state versions and Transition Service event idempotency are present.

Existing lease authority is backend/app/state/transition_service.py:137-164, but stage preparation never calls it. Existing cancellation authority is :166-190, but copy has no cancellation hook. Missing broader process cancellation contracts remain AMFA-143_DEPENDENCY only where relevant; the local omission remains local. No stage restart/reconstruction path was found.

## 13. Persistence, API, Event, and Evidence Boundaries

MigrationStageModel is backend/app/repositories/models/workflow.py:53-69. StageWorkspaceModel is backend/app/repositories/stage_workspace_models.py:41-64. G07ApprovalModel is :12-38. Copy evidence is created at backend/app/services/stage_preparation_service.py:231-250. Events are appended by StateTransitionService at backend/app/state/transition_service.py:105-115.

Migration backend/alembic/versions/20260720_01_stage_workspace_g07.py was inspected, not executed. API contracts are backend/app/api/stage_contracts.py:12-72 and routes are backend/app/api/routes/stages.py:30-66. The durable boundary lacks active-plan/G06 binding, source path, and accurate counts/sizes. AMFA-171 API/evidence completion is outside scope.

## 14. Security and Fail-Closed Review

Explicit local findings: missing roots fail; existing destinations are rejected; copy OSError fails but partial output remains; G07 is not required before copying; invalid G07 states are not checked; and active plan/profile/commands are not validated.

The following are explicit AMFA-170 requirements or explicit required test behaviors from `docs/sprint.md:123-146`: input/sandbox fingerprint verification, source-safety validation, interrupted copy, path escape, link escape, source mutation, stale gate replay, and restart. They are therefore implementation gaps where absent, not merely architectural lenses.

`ARCHITECTURAL_LENS_NOT_REQUIREMENT` is retained only for implementation choices not dictated by the requirement text: the exact atomic-publication mechanism, exact registered-root plumbing, exact hashing algorithm, and exact internal reparse-point representation. Those choices constrain the implementation authority but do not add separate requirements.

## 15. Existing Test and Proof Assessment

backend/tests/test_stage_workspace.py:109-289 asserts G07 builder/decisions, fingerprints, and checksums. Lines 326-449 and 546-595 assert basic prepare/copy/G07/stale-state behavior. It does not assert active plan/G06, redetection, exact bindings, leases, containment, link escape, source mutation, interrupted recovery, stale replay, duplicate prepare, or restart. Lines 459-491 manually insert workspace/G07 rows.

Executed from backend:
`python -m pytest tests/test_stage_workspace.py`
Result: exit code 1; pytest collected 0 items and failed during collection before test execution with `ModuleNotFoundError: No module named sqlalchemy`. This is an environment readiness limitation, not an ownership transfer. The tests listed in `docs/sprint.md:127-143` are explicit AMFA-170 requirements; missing assertion-level coverage remains `AMFA-170_LOCAL`. AMFA-173 owns later cross-layer validation, security campaign evidence, manual proof, frontend/API coverage, and documentation, but does not replace these focused backend tests. No dependency installation or broad tests were run.

## 16. Duplicate or Bypass Authority Findings

| Comparison | Classification | Evidence |
|---|---|---|
| Active pointer vs request-derived plan | CONFIRMED_BYPASS | stage_preparation_service.py:92-102 versus planning_review_evidence_application_service.py:797-834 |
| Direct copy vs workspace authority | CONFIRMED_BYPASS | stage_preparation_service.py:200-205 versus workspaces/services.py:WorkspaceService and workspaces/baseline.py:BaselineSandboxService |
| sandbox vs workspaces modules | DISTINCT_RESPONSIBILITY | Existing baseline behavior and documented dedicated-workspace direction |
| Direct status writes vs Transition Service | CONFIRMED_BYPASS | stage_preparation_service.py:295-297,454-456 |
| Request values vs exact persisted authority | CONFIRMED_BYPASS | stage_contracts.py:12-20 versus domain/planning.py:116-136 |
| G07 builder versus decision authority | UNRESOLVED | Builder exists but package and readiness ordering are wrong |
| Fingerprints | CONFIRMED_DUPLICATE | stage name-only hash versus sandbox content hash |
| Mock workflow leakage | UNRESOLVED | rg search for mock_nodes, mock-workflow, and stage imports found no inspected call |

## 17. Consolidated Gap Register

All ten implementation gaps are `AMFA-170_LOCAL`; the only consumed dependency is `AMFA-110 / S2-F07` for GAP-002. AMFA-173 is a later validation consumer, not the owner of these AMFA-170 implementation requirements. Counts: 3 BLOCKER, 5 HIGH, 2 MEDIUM; ownership count: 10 AMFA-170_LOCAL.

| Gap | Affected requirements | Title / status / severity | Ownership | Consumed dependency | Evidence (file, symbol, lines) | Observed behavior | Required behavior | Architectural consequence | Exact likely files and symbols | Focused tests required | Prerequisites | Blocks completion? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMFA-170-GAP-001 | R01, R03, R04, R11 | Active plan bypass; INCORRECT; BLOCKER | AMFA-170_LOCAL | — | `backend/app/services/stage_preparation_service.py`, `prepare_stage`, 92-102; upstream resolver `planning_review_evidence_application_service.py`, 797-834 | Request fields build a local plan. | Select and lock the active exact plan/profile/commands/checksum. | AMFA-170 must consume planning authority and cannot make request data authoritative. | `backend/app/services/stage_preparation_service.py`, `prepare_stage`/`decide_g07`; planning resolver integration; related stage persistence models. | plan/profile drift, exact lock, replay identity | Confirm upstream service contract and persisted binding fields. | Yes |
| AMFA-170-GAP-002 | R01, R06, R11 | G06 authority not consumed; MISSING; HIGH | AMFA-170_LOCAL | `AMFA-110 / S2-F07` | `backend/app/services/planning_review_application_service.py`, G06 authority, 367-447; AMFA-170 stage path, 92-102 and 367-403 | Existing approved G06 authority is never read by AMFA-170. | Require current approved G06 and reject missing, rejected, stale, or invalidated bindings. | Local AMFA-170 consumption defect; not an upstream implementation blocker. | `stage_preparation_service.py`, `prepare_stage`/`create_sandbox`/`decide_g07`; G06 binding lookup/validation seam. | missing/rejected/stale G06, G06 drift, approved replay | Use S2-F07 authoritative package and binding contract. | Yes |
| AMFA-170-GAP-003 | R01, R06, R11 | Sandbox not G07-gated; INCORRECT; BLOCKER | AMFA-170_LOCAL | — | `stage_preparation_service.py`, `create_sandbox`, 132-205; `decide_g07`, 454-466 | Copy occurs before G07 lookup and approval. | No sandbox progression or ready state without current approved G07. | Gate ordering must be enforced at the application boundary; LangGraph cannot substitute for it. | `stage_preparation_service.py`, `create_sandbox` and G07 transition path; stage state/event persistence. | pending/rejected/expired/stale G07 blocks copy; approved G07 permits it | GAP-001/002 bindings and valid transition contract. | Yes |
| AMFA-170-GAP-004 | R01, R07, R11 | Lease not consumed; MISSING; HIGH | AMFA-170_LOCAL | — | `backend/app/state/transition_service.py`, lease methods, 137-164; stage service has no call site | Lease authority exists but prepare/sandbox/G07 never invokes it. | Detect lease conflict before stage mutation/copy and use Transition Service authority. | Prevents concurrent stage operations from bypassing workflow truth. | `stage_preparation_service.py`, preparation/sandbox entry points; `TransitionRequest` integration. | lease conflict and permitted lease replay | Establish operation/lease identity and expected state version. | Yes |
| AMFA-170-GAP-005 | R01, R08, R10, R12 | Unsafe direct copy; INCORRECT; BLOCKER | AMFA-170_LOCAL | — | `stage_preparation_service.py`, `create_sandbox`, 200-205; `backend/app/workspaces/baseline.py`, `BaselineSandboxService.create`, 20-96 | Direct `copytree` preserves links, leaves partial output, and lacks registered containment. | Reuse one registered copy authority with containment, link safety, collision handling, cancellation cleanup, and reconstruction. | Removes the confirmed bypass and forbids a competing stage copier. | `backend/app/services/stage_preparation_service.py`, `create_sandbox`; thin adapter around `BaselineSandboxService`; `WorkspaceService` boundary. | interrupted copy, path escape, link escape, collision, source mutation | Resolve snapshot/fingerprint and registered run root. | Yes |
| AMFA-170-GAP-006 | R01, R09, R10, R12 | Weak fingerprint/evidence; PARTIALLY_IMPLEMENTED; HIGH | AMFA-170_LOCAL | — | `stage_preparation_service.py`, 207-229 and 279-289 | Hashes are compared but counts/sizes are zero and source mutation is not checked. | Verify content-bound input/sandbox fingerprints with accurate counts/sizes and fail closed on unavailable or mismatched evidence. | Evidence must be checksum-bound to immutable source and published workspace. | `stage_preparation_service.py`, fingerprint/evidence construction; `StageWorkspaceModel` persistence fields. | missing/mismatch fingerprint, source mutation, accurate metadata | GAP-005 copy result and stable snapshot evidence. | Yes |
| AMFA-170-GAP-007 | R05, R06, R09, R11 | Incomplete G07 binding/replay; PARTIALLY_IMPLEMENTED; HIGH | AMFA-170_LOCAL | — | `stage_preparation_service.py`, `decide_g07`, 367-403 and 333-339 | Package plan/profile and source/target data are reconstructed; replay checks only key. | Bind state/gate/artifact/plan/G06/input/workspace values and compare replay payload identity/current bindings. | G07 evidence cannot authorize a different physical or logical workspace. | `stage_preparation_service.py`, `decide_g07`; G07 model/package fields; replay lookup. | stale gate replay, payload mismatch, plan/artifact/input drift | GAP-001/002 and the authoritative pre-copy input-fingerprint portion of GAP-006; GAP-005 and post-copy sandbox evidence are downstream. | Yes |
| AMFA-170-GAP-008 | R01, R11 | State vocabulary/transition bypass; INCORRECT; MEDIUM | AMFA-170_LOCAL | — | `stage_preparation_service.py`, direct status writes, 79-86 and 295-297/454-456; `transition_service.py`, 69-115 | Direct writes and `STAGE_PREPARING` event vocabulary are not consistently aligned with the sprint contract. | Use exact vocabulary and Transition Service for durable state/event mutation. | SQLite/Transition Service remains workflow truth; service-local writes cannot diverge. | `stage_preparation_service.py`, all stage status writes; `domain/contracts.py`, status/event mapping; transition calls. | transition sequence, stale expected version, restart reconstruction | Confirm canonical event/status names. | Yes |
| AMFA-170-GAP-009 | R01, R08, R12 | Prepare/restart recovery absent; MISSING; HIGH | AMFA-170_LOCAL | — | `stage_preparation_service.py`, 68-129 and 200-205; no stage restart/reconstruction call found | Duplicate prepare creates random stages; interrupted copy has no durable recovery path. | Idempotently replay prepare, classify interruption, clean/reconstruct temporary state, and recover after restart. | Recovery must be durable and must not rerun unsafe copy or duplicate events. | `stage_preparation_service.py`, prepare/copy orchestration; workspace copy-status persistence; restart loader/reconstructor. | duplicate prepare/sandbox, interrupted copy, restart | GAP-005 authority and persistence contract. | Yes |
| AMFA-170-GAP-011 | R12 | Required scenario assertion coverage incomplete; PARTIALLY_IMPLEMENTED; MEDIUM | AMFA-170_LOCAL | — | `docs/sprint.md`, 127-146; `backend/tests/test_stage_workspace.py`, 326-595 | Existing tests omit many explicitly listed scenarios. | Add focused backend assertions for every sprint-listed scenario; AMFA-173 later adds cross-layer/security/manual/API proof. | AMFA-170 completion cannot rely on later cross-layer validation to replace local behavior tests. | `backend/tests/test_stage_workspace.py`; focused stage/workspace test fixtures and service seams. | prior input, stale input, drift, missing fingerprint, duplicates, collision, interruption, lease, path/link escape, mutation, stale replay, restart | Implement corresponding production seams and restore test imports. | Yes |

## 18. Implementation-Ready Remediation Plan

The following units are ordered and implementation-ready. They describe changes only; they do not authorize implementation in this audit.

1. **RM-1 — Resolve authoritative plan, G06, current input, and input fingerprint (GAP-001, GAP-002, GAP-006; R01-R04, R06, R09, R11).** Owner: AMFA-170_LOCAL. Files/symbols, in order: `backend/app/services/stage_preparation_service.py:prepare_stage` -> active-plan resolver -> current-version/input resolver -> G06 validation seam -> stage plan/G06/input binding persistence. Reuse the existing planning resolver and AMFA-110/S2-F07 G06 authority. Prohibit request-derived plan reconstruction and local G06 replacement. Input contract: request identifiers select candidates; output is the exact plan/profile/commands, approved G06 binding, authoritative input fingerprint, and intended registered destination identity. State impact: no durable preparation until current input and expected state version are bound. Events: binding identities/checksums are recorded through Transition Service. Persistence/migration: add only proven missing durable binding fields. Failure/rollback: reject missing, stale, rejected, drifted, or mismatched authority without partial lock. Replay: identical payload replays; changed payload conflicts. Positive tests: current plan/G06/input lock. Negative tests: drift, missing/rejected/stale G06, stale input, missing fingerprint. Restart tests: reconstruct the durable lock without rebuilding from request. DoD: authoritative pre-copy inputs are persisted and revalidated. Prerequisites: upstream contracts and canonical PREPARING vocabulary.

2. **RM-4 — Establish lease and Transition Service authority (GAP-004, GAP-008; R01, R07, R11).** Owner: AMFA-170_LOCAL. Files/symbols, in order: `stage_preparation_service.py:prepare_stage/create_sandbox/decide_g07` -> `backend/app/state/transition_service.py` lease and transition methods -> stage status/event models. Reuse Transition Service lease conflict, expected-version, and event idempotency behavior. Prohibit service-local authoritative status mutation or an independent lease store. Input/output: operation identity and expected version produce a durable transition result. Runtime impact: resolve input/plan, then acquire/check lease, then perform durable PREPARING transition before G07 generation. Events: canonical PREPARING/locked/waiting/ready vocabulary and ordered sequences. Persistence/migration: no new store unless a contract gap is proven. Failure/rollback: conflicts fail before mutation/copy; failed transitions do not advance state. Replay: stable idempotency keys replay identical transition payloads. Positive tests: valid lease and sequence. Negative tests: lease conflict and stale state. Restart tests: transition reconstruction. DoD: workflow truth changes pass through Transition Service. Prerequisites: RM-1 and canonical state vocabulary.

3. **RM-2 — Generate and decide G07 against authoritative pre-copy bindings (GAP-003, GAP-007, GAP-008; R01, R05-R06, R09, R11).** Owner: AMFA-170_LOCAL. Files/symbols, in order: `stage_preparation_service.py:prepare_stage` -> `decide_g07` -> `G07ApprovalPackageBuilder`/`G07ApprovalService` -> Transition Service calls -> G07/stage persistence. Reuse the existing builder, decision service, and Transition Service. Prohibit copying or emitting ready state before current approved G07, reconstructed package plans, and direct stage status writes. Pre-copy package contract: bind state version, gate version, artifact-set checksum, active plan/profile, authoritative input-workspace or source-snapshot fingerprint, and intended registered destination identity when already part of the package contract. Do not require the resulting sandbox fingerprint here. State: pending/rejected/expired/stale/technically blocked gates stop progression. Events: generate current G07, approve current G07, and only then permit the copy command. Persistence/migration: bind package to plan/G06/state/gate/artifact/input/destination values; no duplicate rows on replay. Failure/rollback: reject before publication and invalidate stale packages. Replay: compare idempotency payload and all current pre-copy bindings. Positive tests: current approved package permits copy authorization. Negative tests: every invalid gate and package drift; sandbox fingerprint absent from pre-copy package. Restart tests: rehydrate the pre-copy gate sequence. DoD: no copy path is callable without a current approved G07 package. Prerequisites: RM-1 and RM-4.

4. **RM-3 — Execute the approved safe copy and verify the sandbox (GAP-005, GAP-006, GAP-009; R01, R08-R10, R12).** Owner: AMFA-170_LOCAL. Files/symbols, in order: `stage_preparation_service.py:create_sandbox` -> thin adapter/coordinator -> `backend/app/workspaces/baseline.py:BaselineSandboxService.create/reconstruct` -> `backend/app/workspaces/services.py:WorkspaceService` -> post-copy evidence and ready transition. Reuse registered-root/non-overlap validation plus temporary publication, unsafe-link rejection, cancellation cleanup, reconstruction, and content fingerprinting. Prohibit `shutil.copytree` or a competing copier in stage service. Runtime order: after approved G07, invoke `BaselineSandboxService`; calculate and verify the sandbox fingerprint; persist post-copy verification evidence; then emit durable `SANDBOX_READY`. Input/output: adapter maps authoritative snapshot, approved input fingerprint, registered run root, destination, and cancellation into `BaselineSandboxRecord`; output contains the verified sandbox fingerprint, counts/sizes, and evidence checksum. State/events: copy status is pending/completed/recovered and ready is emitted only after verification. Persistence/migration: retain source/destination, pre-copy input fingerprint, post-copy sandbox fingerprint, counts/sizes, copy status, and evidence checksum; add fields only if required by the contract. Failure/rollback: clean temporary/partial outputs, reject escapes/links/mutation/collision, and reconstruct from immutable snapshot. Replay: matching verified workspace replays; conflicting physical or request identity fails closed. Positive tests: approved safe copy, accurate post-copy fingerprint/evidence. Negative tests: interrupted copy, path escape, link escape, source mutation, collision. Restart tests: reconstruction of temporary/failed copy. DoD: one registered authority performs every copy and no ready event precedes successful verification. Prerequisites: RM-1, RM-4, RM-2, and registered run-root resolution.

5. **RM-5 — Execute complete AMFA-170 focused proof (GAP-011; R12).** Owner: AMFA-170_LOCAL. Files/symbols, in order: `backend/tests/test_stage_workspace.py` focused fixtures/assertions, then the stage/workspace seams covered by RM-1–RM-4. Reuse existing test models/builders and AMFA-170 test boundary. Prohibit replacing assertion-level backend tests with later cross-layer evidence or manual claims. Input/output: each sprint scenario has a deterministic fixture and assertion. State/events/persistence: assert versions, event order, durable replay, and recovery. Failure/rollback: assert fail-closed behavior and cleanup. Replay: duplicate and changed-payload cases. Positive tests: correct prior input, approved bindings, lease success, approved G07, safe copy, post-copy verification. Negative tests: stale/drift/missing fingerprint, duplicate, collision, interruption, lease, path/link escape, mutation, stale replay, and no pre-copy sandbox fingerprint. Restart tests: process/repository reconstruction. DoD: all `docs/sprint.md:127-146` scenarios execute and assert behavior. Prerequisites: RM-1 through RM-4 complete and a prepared backend environment with `sqlalchemy` available; environment readiness is not an implementation gap.

## 19. Audit Limitations and Unverified Claims

### Audit Environment Limitation

Focused pytest collection failed before execution with `ModuleNotFoundError: No module named sqlalchemy`; no test result was obtained. Dependency installation was prohibited during the audit. The AMFA-170 implementation task must use a prepared backend environment with the required dependencies available. This limitation is not an implementation gap and is not assigned to `AMFA-170_LOCAL`.

No migration, build, broad suite, service, manual scenario, or OpenAPI generation ran. Static inspection cannot prove runtime integration or database ancestry. NOT_FOUND searches are limited to prescribed/directly related paths using rg for redetect, current_version, ActivePlanVersion, G06, lease, JobSupervisor, ProcessController, and stage terms. AMFA-110, AMFA-143, AMFA-171, and AMFA-173 completion was not assessed.

## 20. Independent Reviewer Verdict

PARTIALLY_IMPLEMENTED

The path has partial scaffolding, but active plan and G06 are bypassed, G07 does not gate sandbox creation, leases are unused, direct copy bypasses workspace authority, fingerprints are insufficient, state/event vocabulary conflicts, and focused proof is unavailable. Existing upstream authorities exist, so the primary failures are local authority-consumption defects.

Adversarial self-review performed; independent reviewer unavailable.

## 21. Final Integrity Record

The direct Markdown validator is the report-content authority. `git diff --check` is only a Git diff check and does not validate an entirely untracked report. The report hash is deliberately not embedded: recording it after final writing is the final operation, so embedding it would change the file again.

Exact validator command: `python -c "import re; from pathlib import Path; p=Path(r'docs/audits/01_AMFA-170_IMPLEMENTATION_AUDIT.md'); raw=p.read_bytes(); s=raw.decode('utf-8'); h=['Audit Metadata and Preflight','Scope, Non-Goals, and Source Hierarchy','Targeted Inputs Read','Freshness and Baseline Reuse Decision','Exact AMFA-170 Requirement Decomposition','Requirement Verdict Matrix','Backend End-to-End Static Trace','Active Plan and G06 Dependency Consumption','Stage State and Transition Authority','G07 Package and Decision Boundary','Workspace and Sandbox Creation','Idempotency, Replay, Lease, and Cancellation','Persistence, API, Event, and Evidence Boundaries','Security and Fail-Closed Review','Existing Test and Proof Assessment','Duplicate or Bypass Authority Findings','Consolidated Gap Register','Implementation-Ready Remediation Plan','Audit Limitations and Unverified Claims','Independent Reviewer Verdict','Final Integrity Record']; got=[x.split('. ',1)[1] for x in s.splitlines() if x.startswith('## ') and x[3:4].isdigit()]; parts=s.split(chr(96)*3); oldpath='backend/app/'+'sandbox/'+'baseline.py'; oldgap='AMFA-170-GAP-'+'010'; assert raw.decode('utf-8') and not any(ord(c)<32 and c not in (chr(10),chr(13)) for c in s) and chr(9) not in s and len(parts)%2==1 and all(part.count(chr(96))%2==0 for part in parts[::2]) and got==h and not re.search('[A-Za-z]:'+'['+chr(92)+'/]',s) and chr(92) not in s and all(x not in s for x in ('TO'+'DO','T'+'BD','FIX'+'ME')) and all(('AMFA-170-R%02d'%i) in s for i in range(1,13)) and 'Requirement Verdict Matrix' in s and 'Consolidated Gap Register' in s and 'Implementation-Ready Remediation Plan' in s and 'PARTIALLY_IMPLEMENTED' in s and oldpath not in s and oldgap+' |' not in s and '10 implementation gaps' in s and '3 BLOCKER, 5 HIGH, 2 MEDIUM' in s; print('MARKDOWN_VALID')"`

The final stable integrity outputs, recorded after final writing, are:

```text
git status --porcelain=v1 -uall -> ?? docs/audits/01_AMFA-170_IMPLEMENTATION_AUDIT.md (exit code 0)
git diff --check -> empty output (exit code 0)
git hash-object docs/sprint.md -> 4c9a17670ce6d988bdcad48d43e805dbf9a0c53e (exit code 0)
git hash-object docs/audits/00_REPOSITORY_AUDIT_BASELINE.md -> cd793cf4fa81a92467fe963a4b984f5c74509fab (exit code 0)
git diff --name-status -> empty output (exit code 0)
```

The validator must be run after the final report write and must exit 0 with output `MARKDOWN_VALID`. The final report hash is supplied only in the Codex handoff so this section remains stable.
