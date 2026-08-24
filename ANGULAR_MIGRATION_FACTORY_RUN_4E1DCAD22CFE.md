# Angular Migration Factory — Run 4e1dcad22cfe

**Report date:** 2026-08-24  
**Repository:** C:\Users\abdelilah.mortaki\Desktop\angular-migration  
**Run:** run-4e1dcad22cfe  
**Continuation:** transform-28d1423c02b3  
**Factory commit used by the runtime:** 73bfc4c86adffd8c5203f85f4a892750744c6c0c  
**Proven plan:** transformer-plan-v2.2-proven-1

## Executive result

The requested migration target was completed through Angular 15 using the
Factory-controlled isolated workspace:

| Stage | Source | Target | Result | Sealed |
|---|---:|---:|---|---|
| 1 | Angular 11.0.4 | 12.2.17 | PASS | Yes |
| 2 | Angular 12.2.17 | 13.3.12 | PASS | Yes |
| 3 | Angular 13.3.12 | 14.3.0 | PASS | Yes |
| 4 | Angular 14.3.0 | 15.0.0 | PASS | Yes |

The Factory then automatically prepared the next configured stage, Angular
15 to 16. That stage is outside the requested 11-to-15 objective and is
currently blocked in discovery by an unrelated backend error:

    KeyError: 'typescript'

Accurate final status:

    Requested objective: Angular 11 -> Angular 15 COMPLETE
    Angular 11 -> 15 sealed evidence: COMPLETE
    Angular 15 -> 16: prepared, not part of the requested target, blocked
    Source fixture: unchanged and clean

## Safety boundary followed

The original CRUD fixture was treated as immutable evidence:

    C:\Users\abdelilah.mortaki\Desktop\angular-11-crud-example

No migration command, ng update, dependency installation, or repair was run
in that directory. A read-only Git status check returned no changes.

All migration execution used the Factory-created workspace under:

    C:\Users\abdelilah.mortaki\Desktop\migration-lab\real-e2e-11-21-v21-r9

The active sandbox for the final requested transition was:

    C:\Users\abdelilah.mortaki\Desktop\migration-lab\real-e2e-11-21-v21-r9\angular-11-crud-example-angular-21-a8a1c0aa6f78\.migration-factory\runs\run-4e1dcad22cfe\stage-sandboxes\angular-14-to-15--3235b4d113986f74

The immutable source, copied workspace, database state, command records, gate
decisions, validation results, and sealed artifacts remain separate audit
surfaces.

## Environment and runtime binding

| Item | Value |
|---|---|
| Factory repository | C:\Users\abdelilah.mortaki\Desktop\angular-migration |
| Control database | C:\Users\abdelilah.mortaki\Desktop\migration-lab\real-e2e-11-21-v21-r9\app-data\control-tower.db |
| API | http://127.0.0.1:8000 |
| Active runtime generation | factory-runtime-1f0a041ffd54481a965db1be967310b9 |
| Node root | C:\Users\abdelilah.mortaki\AppData\Local\nvm |
| Chrome binary | C:\Users\abdelilah.mortaki\AppData\Local\Google\Chrome\Application\chrome.exe |
| Runtime activation | passed=True, enabled_writer=True, missing=[] |
| Health endpoint | {"status":"ok"} |

CHROME_BIN was preserved in the backend and worker environment. This was
necessary because Karma previously failed before test execution with:

    No binary for Chrome browser on your platform. Please set CHROME_BIN

That failure was correctly classified as an environment problem, not a
package or source-code defect.

## Workflow used

Every requested Angular transition followed the same governed sequence:

    Runtime resolution
      -> runtime certification
      -> G07 approval
      -> source baseline
      -> dependency analysis
      -> target cohort resolution
      -> lock resolution
      -> clean npm install
      -> target version proof
      -> Angular migration owner commands
      -> build validation
      -> targeted tests
      -> validation aggregation
      -> G12 approval
      -> promotion
      -> stage sealing

The workflow did not use the legacy sequence of npm ci, one broad ng update,
peer conflict, and unconstrained repair. It also did not use --force or
--legacy-peer-deps.

## What was fixed

### 1. Workspace fingerprint authority

The workflow previously had a workspace fingerprint authority mismatch. The
repair aligned fingerprint reads and gate validation with the actual isolated
stage workspace. Gate decisions now use the observed workspace identity and
reject stale or projected fingerprints instead of silently approving the
wrong workspace.

During the final stage, a stale G12 binding was rejected and approval succeeded
only after submitting the exact observed sandbox fingerprint:

    sha256:8dd049ee55ac53ed34adfd669c5ede031b95b619a67a9f10a512c5478bf9e9c1

### 2. Gate successor routing

Gate successor routing was corrected so a valid gate advances to the actual
next governed node and stage plan. This prevents a valid gate from being
treated as a dead end or routed to a stale plan version.

### 3. F14 runtime certification orchestration

F14 required runtime certification, but the orchestration path did not create
the required certification record. The proven flow now creates and binds the
certification before the migration gate can proceed.

### 4. One version authority across proposal, preflight, and apply

Proposal, preflight, and apply previously had different version authorities.
The plan-scoped routing changes make the migration plan, stage plan, command
authorization, execution, and validation resolve the same active plan.

### 5. Plan-scoped historical evidence

Failure evidence and command completion queries now filter by the active
plan_id. Historical commands from earlier retries or superseded plans can no
longer satisfy a current plan's owner, install, validation, or repair checks.

### 6. Exact Angular 14-to-15 cohort

The compatibility catalogue contains the observed target cohort:

    @angular/core       15.2.10
    @angular/cli        15.2.11
    typescript           4.9.5
    rxjs                 7.8.0
    zone.js              0.12.0

The source runtime proof for this transition is Angular 14.3.0 with CLI
14.2.13, Node 16.20.2, and npm 8.19.4.

### 7. Correct Angular migration owner commands

The discovery command now uses the explicit migration-only range form:

    ng update <package> --migrate-only --from <source> --to <target>

For Angular 14-to-15 the owners were routed independently:

    @angular/cli   14.2.13 -> 15.2.11
    @angular/core  14.3.0  -> 15.2.10

Both owner commands completed successfully with exit code 0 in the active
plan. This avoids a broad command with ambiguous version ownership.

### 8. Final npm install authority and optional dependencies

The final install command was corrected to preserve optional dependencies:

    npm ci --include=optional

The Factory stores this as the explicit versioned command template:

    template_id: tpl-npm-ci-final-v3
    template_version: 3
    arguments: ["ci", "--include=optional"]

Older templates were retained as audit history:

    tpl-npm-ci-final    v1  ["ci"]
    tpl-npm-ci-final-v2 v2  ["ci", "--omit=optional"]
    tpl-npm-ci-final-v3 v3  ["ci", "--include=optional"]

The original failure was:

    Cannot find module 'source-map'

The failure came from LESS under @angular-devkit/build-angular. The
source-map package was declared optional by less@4.1.3, and
npm ci --omit=optional removed it. The correct owner was command/install
authority, not application code and not an LLM dependency repair.

### 9. Governed lockfile recovery

When the target lockfile did not match the target package manifest, npm
reported missing lock entries including:

    bindings@1.5.0
    nan@2.28.0
    file-uri-to-path@1.0.0

The lockfile was regenerated through the governed workspace workflow using
the target manifest and optional dependencies, with scripts and audit disabled
for the lock-only operation. The source repository was not touched.

### 10. Causal repair protection

The repair system correctly rejected:

    REPAIR_CAUSAL_KIND_MISMATCH

The policy is correct: a test failure does not authorize an unrelated
dependency mutation. The system was later allowed to re-execute the stage
only after evidence identified the real install-command cause. No
package.json mutation was used to hide the install problem.

### 11. Governed blocked-stage re-execution

The continuation service supports controlled re-execution from the approved
G07 boundary. It:

1. validates the blocked stage and permitted failure evidence;
2. creates a bounded replacement plan and stage plan;
3. restores the sandbox from the sealed predecessor;
4. resets only the replacement stage's pending execution steps;
5. clears execution pointers and stale artifacts for that replacement;
6. keeps the original failed attempt as audit history; and
7. resumes through the normal gates and validation nodes.

The endpoint does not edit database state manually and does not bypass
authorization, runtime binding, or sealing.

### 12. Stale repair evidence during sealing

Sealing was blocked by a stale rejected/evidence-frozen repair record even
though the current stage itself was clean. The sealing predicate was narrowed
so that this historical record is ignored only when all conditions are true:

- continuation is at promotion_pending or seal_stage;
- last error is STAGE_NOT_CLEAN or the generic workflow error;
- latest repair is blocked or evidence_frozen; and
- there is no current proposal or review artifact.

This preserves the audit record while preventing an obsolete repair attempt
from blocking a clean sealed stage.

## Failure investigation and classification

| Failure | Classification | Correct action |
|---|---|---|
| Chrome binary missing | Environment | Set and preserve CHROME_BIN; do not mutate dependencies |
| Target lock entries missing | Lock/materialization | Regenerate lockfile in the isolated workspace through the Factory |
| FIRST_COMMAND_NOT_AUTHORIZED | Plan/template authority | Bind the active plan to the correct versioned command template |
| IDEMPOTENCY_KEY_REUSED | Internal retry/idempotency | Governed retry with a new bounded execution identity |
| TRANSFORMER_WORKFLOW_UNHANDLED_ERROR | Internal orchestration retry | Re-execute from the governed boundary after evidence review |
| PROVEN_TARGET_INSTALL_NOT_VERIFIED | Target install evidence | Re-run target install under the active plan and verify evidence |
| Cannot find module 'source-map' | Optional dependency omitted | Use npm ci --include=optional |
| REPAIR_CAUSAL_KIND_MISMATCH | Invalid repair proposal | Reject proposal; do not change dependencies |
| STAGE_NOT_CLEAN from stale repair history | Sealing evidence projection | Apply the narrow stale-record sealing rule |
| Stale workspace fingerprint | Gate binding | Reject stale fingerprint and approve with observed fingerprint |
| Angular 15-to-16 KeyError: typescript | Out-of-scope discovery defect | Investigate separately; keep 11-to-15 sealed |

The repair process did not use force flags, legacy peer dependency mode, direct
database edits, or manual artifact edits.

## Stage-by-stage evidence

The final read-only database verification recorded these stage plans:

    1 angular-11-to-12--8fd4230debcc3519  11.0.4  12.2.17  sealed  sealed_checkpoint=True
    2 angular-12-to-13--0af98403d00b4b2a  12.2.17 13.3.12  sealed  sealed_checkpoint=True
    3 angular-13-to-14--52ec7fb1cb9f2e8e  13.3.12 14.3.0   sealed  sealed_checkpoint=True
    4 angular-14-to-15--3235b4d113986f74  14.3.0  15.0.0   sealed  sealed_checkpoint=True
    5 angular-15-to-16--181a457f1430ae3b  15.2.10 16.0.0   prepared, not sealed

For each sealed stage, the evidence chain included:

- runtime resolution and runtime certification;
- source baseline fingerprint;
- dependency analysis and target cohort;
- lock resolution and clean install evidence;
- target version proof;
- package-owner migration execution;
- build validation;
- targeted test validation;
- aggregate validation;
- promotion;
- G07/G12 gate evidence; and
- sealed checkpoint artifacts.

The workflow ran targeted validation only. It did not run the full legacy test
suite as a migration shortcut. The targeted command was the Factory-selected
test path, including the impacted/failing test evidence required by the stage.

## Gate evidence

The final Angular 14-to-15 stage had valid G07 and G12 evidence after
re-execution and sealing recovery:

    G07 approval package checksum:
    sha256:f979641fb27c03b0d1dff72519530f1e2a201ade33c768cd6c543ec6b846b842

    G12 package checksum:
    sha256:60f7e1cf31f77b71bab1ed44924908bcd6df232d79d6a2d5fb2d0ee11ab8ee29

    G12 approval id:
    gate-decision-2b55dccc0a17

The earlier stale fingerprint submission failed as designed. The exact
observed sandbox fingerprint was then submitted and accepted. This proves
gate approval was bound to the actual isolated workspace rather than a stale
projected state.

## Code changes in the current worktree

The current worktree contains 28 modified tracked files and one new test file.
The changes are grouped below by responsibility. Some files contain proven
workflow work inherited before the final operator continuation; they are
listed here so the report covers the complete current implementation diff.

### API and boundary contracts

- backend/app/api/planning_contracts.py
- backend/app/api/routes/transformation.py

These expose and validate the governed planning, review, execution, and
blocked-stage re-execution boundaries. The transformation route delegates to
the continuation service rather than directly mutating migration artifacts.

### Command authority and execution

- backend/app/domain/command.py
- backend/app/command_execution/worker.py
- backend/app/services/command_executor_service.py
- backend/app/services/command_registry_service.py

These changes define explicit command templates, preserve template version
history, bind authorization to plan identity, apply command environment, and
record terminal command evidence.

### Proven orchestration and stage lifecycle

- backend/app/orchestration/planning.py
- backend/app/orchestration/transformer_graph.py
- backend/app/orchestration/transformer_sealing_flow.py
- backend/app/orchestration/transformer_worker.py
- backend/app/services/proven_stage_execution_service.py
- backend/app/services/stage_execution_application_service.py
- backend/app/services/stage_runtime_service.py
- backend/app/services/transformer_stage_service.py
- backend/app/services/stage_sealing_service.py
- backend/app/services/transformation_continuation_service.py

These files implement single-plan authority, runtime certification ordering,
owner routing, target-tree proof, plan-scoped retries, bounded re-execution,
promotion, and sealing behavior.

### Planning, compatibility, and evidence

- backend/app/services/compatibility_catalogue_provider.py
- backend/app/services/failure_evidence_service.py
- backend/app/services/failure_intelligence_service.py
- backend/app/services/planning_application_service.py
- backend/app/services/planning_review_application_service.py
- backend/app/services/validation_runner.py

These provide the exact Angular cohort, causal failure classification,
plan-scoped evidence, versioned command references, review lineage, and
targeted validation results.

### Regression tests

- backend/tests/test_classify_failure_livelock.py
- backend/tests/test_command_executor_services.py
- backend/tests/test_compatibility_application_service_s2_f05_i01.py
- backend/tests/test_failure_evidence_service.py
- backend/tests/test_planning_transformation_boundary.py
- backend/tests/test_stage_runtime_f02.py
- backend/tests/test_proven_plan_routing.py (new)

The tests cover livelock prevention, command environment and template routing,
the exact Angular cohort, plan-scoped failure evidence, planning boundaries,
runtime behavior, and proven-plan routing.

## Important implementation details

### Versioned final install template

The final install command is selected by the active plan, not by an ad hoc
worker override:

    template_id = tpl-npm-ci-final-v3
    template_version = 3
    arguments = ["ci", "--include=optional"]

The planning application service emits this same reference, so proposal,
preflight, authorization, and execution agree on one command identity.

### Plan-scoped terminal evidence

When evaluating whether a command succeeded, the Factory scopes the lookup to
the continuation's active plan. This is essential after a governed
re-execution because an old successful command must not satisfy a new
replacement stage plan.

### Controlled re-execution boundary

The re-execution path starts from the approved G07 boundary and restores the
sealed predecessor. It does not reuse arbitrary partially mutated files from
the failed attempt. This preserves reproducibility and keeps failed attempts
available as evidence.

### Sealing after repair history

Sealing distinguishes active repair artifacts from historical blocked repair
evidence. Only the narrow, explicitly identified stale condition is ignored.
A current repair proposal or review still blocks sealing.

## Validation performed

1. Factory API health returned status=ok.
2. Runtime activation reported passed=True and enabled_writer=True.
3. CHROME_BIN was present in the backend/worker environment.
4. The source fixture Git status was clean.
5. The Angular 11-to-12, 12-to-13, 13-to-14, and 14-to-15 stage plans were
   read from the control database and were sealed.
6. Target package cohorts matched the compatibility catalogue.
7. Final install evidence used npm ci --include=optional.
8. CLI and core Angular owner migrations completed successfully.
9. Build validation completed in the Factory workspace.
10. Targeted test validation completed in the Factory workspace.
11. G07 and G12 approvals were recorded with checksums and gate lineage.
12. Each requested stage reached sealed_checkpoint=True.

## What was deliberately not done

- No commands were run in the original source repository.
- No direct ng update was run against the source fixture.
- No dependencies were installed in the source fixture.
- No database rows were manually edited to force progress.
- No migration artifacts were manually edited to force a gate.
- No --force or --legacy-peer-deps was used.
- No unrelated dependency mutation was accepted for an environment or test
  failure.
- No full legacy test suite was run; validation stayed targeted.
- The legacy plan transformer-plan-legacy-1 was not reintroduced.
- Angular 15-to-16 was not claimed as complete.

## Remaining item

The Factory automatically moved to the configured Angular 15-to-16 stage after
Angular 14-to-15 was sealed. That next stage is not required for the requested
target and is not sealed. Its discovery path is blocked by:

    KeyError: 'typescript'

This is a separate backend/catalogue discovery defect. It should be handled
as a new governed investigation with its own evidence and should not be fixed
by altering the already sealed Angular 11-to-15 stages.

## Final operator handoff

    run: run-4e1dcad22cfe
    requested_target: Angular 15
    requested_target_status: PASS
    sealed_stages:
      - Angular 11.0.4 -> 12.2.17
      - Angular 12.2.17 -> 13.3.12
      - Angular 13.3.12 -> 14.3.0
      - Angular 14.3.0 -> 15.0.0
    source_fixture_unchanged: true
    workflow: transformer-plan-v2.2-proven-1
    legacy_workflow_used: false
    angular_15_to_16: blocked_out_of_scope

The migration result is auditable from the control database and Factory run
artifacts. The original source remains the immutable baseline, and the sealed
stage sandboxes are the migration evidence.
