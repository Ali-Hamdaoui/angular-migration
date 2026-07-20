# Sprint Scope Snapshot — AMFA-144 / AMFA-145

## Document Metadata

- **Project:** AI Migration Factory - Angular
- **Repository:** `https://github.com/Ali-Hamdaoui/angular-migration.git`
- **Target branch:** `hermes/02-stage-workspace-bootstrap`
- **Jira project:** `AMFA`
- **Parent issues:** `AMFA-144`, `AMFA-145`
- **Subtasks:** `AMFA-170`, `AMFA-171`, `AMFA-172`, `AMFA-173`, `AMFA-174`, `AMFA-175`, `AMFA-176`, `AMFA-177`
- **Snapshot date:** `2026-07-20`
- **Document role:** Immutable local snapshot of the Jira scope for implementation assessment and delivery.

> **Source-of-truth rule**
>
> This file is the complete local snapshot of the Jira requirements supplied for branch
> `hermes/02-stage-workspace-bootstrap`.
>
> Jira remains the upstream product source of truth. The requirements in this file must not
> be silently reinterpreted, relaxed, amended, shortened, or replaced by assumptions derived
> from the current implementation.
>
> Existing code, filenames, commits, tests, documentation, or Jira statuses are not proof that
> a requirement is implemented. Every requirement must be verified against the actual runtime
> path, persistence, APIs, events, evidence, frontend behavior, security controls, and tests.
>
> Codex and reviewers must not modify this file during implementation work. Any future Jira
> change requires an explicit regeneration or reviewed update of this snapshot.

---

# AMFA-144

## S3-F05 — Prepare a dedicated stage sandbox and decide G07 stage start

- **Issue key:** `AMFA-144`
- **Status:** À faire
- **Priority:** Must
- **Estimate:** M
- **Risk:** Medium

## Description

### Outcome

A reviewer can inspect the current stage input fingerprint, exact resolved plan/profile, dedicated destination, and risks, approve G07, and then create the isolated stage sandbox.

### Scope

StagePreparationService, current-version re-detection, later-stage exact-resolution hook, active StageExecutionPlan lock, G07 evidence package, WorkspaceManager stage copy, fingerprint validation, and lease checks.

### API / Events / Evidence

#### API

- `POST /api/v1/runs/{id}/stages/{stageId}/prepare`
- `POST /api/v1/runs/{id}/approvals/G07/decisions`
- `POST /api/v1/runs/{id}/stages/{stageId}/sandbox`

#### Events

- `STAGE_CREATED`
- `PREPARING`
- `PLAN_LOCKED`
- `WAITING_APPROVAL`
- `SANDBOX_READY`

#### Evidence

- stage-start package
- exact plan/profile
- copy report
- input manifest/fingerprint
- sandbox verification

### Frontend

Stage-start review page with plan/profile/input tabs, workspace alias, risks, G07 controls, copy progress, and ready/blocked states.

### Gate and Authority

G07 is persistent and bound to state version, gate version, artifact-set checksum, active plan version, and workspace fingerprint. Pending, rejected, modification-requested, expired, or stale G07 blocks sandbox creation and stage progression. The original source remains unchanged.

### Dependencies

- `S2-F07`
- `S3-F04`

### Risks

- Stale prior-stage output
- Plan drift
- Approval before fingerprint
- Sandbox collision
- Copy interruption
- Lease conflict
- Source-link escape

### Estimate

M. Priority: Must. Risk: Medium.

---

# AMFA-170

## S3-F05-I01 — Backend: Implement stage preparation, G07, and sandbox creation

- **Issue key:** `AMFA-170`
- **Parent:** `AMFA-144`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Medium

## Description

### Technical Story

Implement the authoritative stage-start path from current input verification through G07 and isolated sandbox readiness.

### Scope

StagePreparationService, current-version re-detection, exact current-stage resolution hook, active StageExecutionPlan lock, stage-start evidence package, persistent G07 rules, lease conflict checks, WorkspaceManager physical copy, input/sandbox fingerprint verification, and source-safety validation.

### Gate and Authority

G07 binds state version, gate version, artifact-set checksum, active plan/profile, and input fingerprint. Sandbox creation is rejected when G07 is pending, rejected, modification-requested, expired, stale, or technically blocked. LangGraph coordinates only; WorkspaceManager performs copies and Transition Service changes state.

### Tests

Cover:

- correct prior-stage input
- stale prior-stage input
- plan/profile drift
- missing fingerprint
- duplicate prepare request
- duplicate sandbox request
- sandbox collision
- interrupted copy
- lease conflict
- path escape
- link escape
- source mutation
- stale gate replay
- restart

### Dependencies / Estimate

S2-F07 and S3-F04. Estimate: M. Risk: Medium.

---

# AMFA-171

## S3-F05-I02 — API/Evidence: Persist stage-start, G07, and sandbox evidence

- **Issue key:** `AMFA-171`
- **Parent:** `AMFA-144`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Medium

## Description

### Technical Story

Persist migration-stage preparation, active stage plan, fingerprints, G07 decisions, sandbox records, events, and immutable evidence.

### Scope

Alembic models/indexes for migration_stages, active stage-plan/version, stage input and sandbox workspaces/fingerprints, gate versions, append-only decisions, idempotency, correlations, and artifacts. Implement stage prepare, G07 decision, and sandbox creation APIs. Persist STAGE_CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL/SANDBOX_READY after durable writes. Finalize stage-start package, exact plan/profile, copy report, input manifest/fingerprint, and sandbox verification.

### Acceptance and Tests

Test:

- Alembic upgrade
- Alembic rollback
- stale state
- stale plan
- stale fingerprint
- stale gate
- duplicate decisions
- duplicate copies
- event order
- artifact failure
- interrupted copy evidence
- restart
- authorization
- protected-transition blocking

Old G07 decisions never satisfy changed bindings.

### Dependencies / Estimate

S3-F05-I01. Estimate: M. Risk: Medium.

---

# AMFA-172

## S3-F05-I03 — Frontend: Build G07 stage-start and sandbox review page

- **Issue key:** `AMFA-172`
- **Parent:** `AMFA-144`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Low

## Description

### Technical Story

Build the authoritative review and interaction surface for current-stage locking, G07, and sandbox creation.

### Scope

Plan/profile/input tabs, exact source/target versions, input fingerprint and evidence, workspace alias, risk notices, gate version/status, comment and decision controls, copy progress, sandbox verification, artifact links, and ready/blocked/stale/reconnect/failure states.

### Authority and Tests

Do not enable sandbox creation without current approved G07. Submit expected state/gate versions and idempotency, display stale binding changes, reload after SSE gaps, and never show the stage active based only on a click.

Test:

- approve
- modification
- reject
- stale replay
- copy failure
- lease conflict
- refresh
- restart
- authorization
- safe paths
- accessibility

### Dependencies / Estimate

S3-F05-I02. Estimate: M. Risk: Low.

---

# AMFA-173

## S3-F05-I04 — Testing/Security/Docs: Validate G07 and sandbox isolation

- **Issue key:** `AMFA-173`
- **Parent:** `AMFA-144`
- **Status:** À faire
- **Estimate:** S
- **Risk:** Medium

## Description

### Technical Story

Prove stage-start evidence binding, G07 non-bypass, physical sandbox isolation, source safety, and restart/reconnect behavior.

### Scope

Backend stage/gate/workspace tests, temporary SQLite and Artifact Store integration, copy/fingerprint fixtures, API/event/frontend tests, manual G07 review and sandbox scenario, and stage-start documentation.

### Required Coverage

- Exact input and plan lock
- Stale prior-stage output
- Missing fingerprint
- Changed fingerprint
- G07 pending
- G07 rejected
- G07 modification-requested
- G07 stale
- Duplicate decision
- Duplicate copy
- Sandbox collision
- Interrupted copy
- Active lease conflict
- Path escape
- Link escape
- Source fingerprint unchanged
- Event ordering
- Restart
- UI state restoration

### Exit Evidence

- G07 integrity suite
- Sandbox-isolation/source-safety report
- Manual screenshots
- Artifact IDs
- Event IDs
- Decision IDs
- Updated stage-start runbook

### Dependencies / Estimate

S3-F05-I03. Estimate: S. Risk: Medium.

---

# AMFA-145

## S3-F06 — Run the stage bootstrap clean install

- **Issue key:** `AMFA-145`
- **Status:** À faire
- **Priority:** Must
- **Estimate:** M
- **Risk:** Medium

## Description

### Outcome

A user can run the exact approved bootstrap install in the stage sandbox and inspect its command, environment, lifecycle-script audit binding, logs, and result.

### Scope

StagePipelineService bootstrap step, authorization against the locked StageExecutionPlan, workspace fingerprint binding, npm ci execution, mutation-category handling, and evidence-backed completion.

### API / Events / Evidence

#### API

- `POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install`
- `GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install`

#### Events

- `STAGE_BOOTSTRAP_INSTALL_STARTED`
- `STAGE_BOOTSTRAP_INSTALL_COMPLETED`
- `STAGE_BOOTSTRAP_INSTALL_FAILED`
- command events

#### Evidence

- install command
- logs
- result
- pre-workspace fingerprint
- post-workspace fingerprint
- package-manager diagnostic artifacts

### Frontend

Stage pipeline step card with approved command, progress/log link, result, environment blockers, and retry or reconstruct guidance.

### Authority and Acceptance

The command must match the locked plan/profile and operate only in the approved stage sandbox. Old node_modules or stale generated state cannot be reused silently. Interrupted mutating installs are not retried generically without recovery classification.

### Dependencies

- `S3-F05`

### Risks

- Existing node_modules
- Lockfile mismatch
- Lifecycle-script risk
- Registry failure
- Interrupted install
- Wrong runtime profile

### Estimate

M. Priority: Must. Risk: Medium.

---

# AMFA-174

## S3-F06-I01 — Backend: Implement stage bootstrap clean install

- **Issue key:** `AMFA-174`
- **Parent:** `AMFA-145`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Medium

## Description

### Technical Story

Implement the stage bootstrap-install step through the locked plan and authoritative executor.

### Scope

StagePipelineService bootstrap step, command authorization against active StageExecutionPlan, G07 and sandbox readiness checks, workspace fingerprint binding, removal/validation of stale dependency state, approved npm ci execution, lifecycle-script audit binding, mutation/interruption classification, and evidence-backed completion.

### Authority and Tests

Only CommandExecutor launches the registered install command in the stage sandbox. Reject wrong profile, stale plan/fingerprint, lockfile mismatch, unsafe flags, missing G07, pre-existing node_modules when policy requires cleanup, and generic retry of an unsafe interrupted mutation.

Test:

- success
- registry failure
- network failure
- lifecycle-script blocker
- cancellation
- stale state
- idempotency
- partial evidence

### Dependencies / Estimate

S3-F05. Estimate: M. Risk: Medium.

---

# AMFA-175

## S3-F06-I02 — API/Evidence: Persist bootstrap-install execution and fingerprints

- **Issue key:** `AMFA-175`
- **Parent:** `AMFA-145`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Medium

## Description

### Technical Story

Persist the bootstrap step, command execution, workspace fingerprint bindings, durable events, and immutable install evidence.

### Scope

Add step/command/fingerprint references and indexes; implement POST /api/v1/runs/{id}/stages/{stageId}/bootstrap-install and GET /api/v1/runs/{id}/stages/{stageId}/steps/bootstrap-install. Persist STAGE_BOOTSTRAP_INSTALL_STARTED/COMPLETED/FAILED plus command events. Finalize install command manifest, stdout/stderr, result, pre/post fingerprints, package-manager diagnostics, and partial evidence on failure/cancellation.

### Acceptance and Tests

Test:

- Alembic upgrade
- Alembic rollback
- duplicate idempotency
- conflicting idempotency
- stale state
- stale plan
- stale profile
- stale fingerprint
- missing G07
- event order
- artifact registration failure
- interrupted install
- restart retrieval
- source safety
- authorization

Completion requires finalized evidence.

### Dependencies / Estimate

S3-F06-I01. Estimate: M. Risk: Medium.

---

# AMFA-176

## S3-F06-I03 — Frontend: Build bootstrap-install pipeline step

- **Issue key:** `AMFA-176`
- **Parent:** `AMFA-145`
- **Status:** À faire
- **Estimate:** M
- **Risk:** Low

## Description

### Technical Story

Build the authoritative bootstrap-install step card inside the stage pipeline.

### Scope

Show approved command/profile, prerequisites, lifecycle-script audit reference, running progress, live/stored log links, result and fingerprints, environment or registry blocker, partial/interrupted status, and backend-provided retry/reconstruct guidance.

Render:

- loading
- ready
- running
- completed
- failed
- cancelled
- stale
- reconnecting
- authorization
- backend-failure states

### Authority and Tests

The UI cannot edit argv or advance the step locally. Start action sends expected state version and idempotency, and final status comes from snapshots/events.

Test:

- missing G07
- stale G07
- wrong profile
- duplicate click
- disconnect
- reconnect
- cancellation
- partial evidence
- artifact links
- accessibility
- correlation guidance

### Dependencies / Estimate

S3-F06-I02. Estimate: M. Risk: Low.

---

# AMFA-177

## S3-F06-I04 — Testing/Security/Docs: Validate bootstrap clean install

- **Issue key:** `AMFA-177`
- **Parent:** `AMFA-145`
- **Status:** À faire
- **Estimate:** S
- **Risk:** Medium

## Description

### Technical Story

Prove reproducible bootstrap installation, command authority, interruption handling, evidence integrity, and UI behavior.

### Scope

Backend service and real npm fixture tests, temporary DB/API/Artifact Store tests, event/log/frontend tests, manual stage bootstrap scenario, and install/recovery documentation.

### Required Coverage

- Clean sandbox and locked profile success
- Old node_modules detection
- Old node_modules removal
- Lockfile mismatch
- Lifecycle-script policy
- Registry failure
- Network failure
- Wrong runtime
- Unsafe flags
- Stale G07
- Stale plan
- Stale fingerprint
- Cancellation
- Interrupted mutation
- Idempotency
- Event order
- Artifacts finalized before pass
- Source unchanged
- UI reconnect

### Exit Evidence

- Bootstrap reproducibility matrix
- Lifecycle/source-safety report
- Manual screenshots
- Command IDs
- Artifact IDs
- Event IDs
- Updated install runbook

### Dependencies / Estimate

S3-F06-I03. Estimate: S. Risk: Medium.

---

# Delivery Dependency Order

The Jira dependency order represented by this snapshot is:

```text
AMFA-144 — S3-F05
  ├── AMFA-170 — Backend
  ├── AMFA-171 — API / Evidence
  ├── AMFA-172 — Frontend
  └── AMFA-173 — Testing / Security / Documentation
        ↓
AMFA-145 — S3-F06
  ├── AMFA-174 — Backend
  ├── AMFA-175 — API / Evidence
  ├── AMFA-176 — Frontend
  └── AMFA-177 — Testing / Security / Documentation
```

External dependencies explicitly named by the tickets:

```text
S2-F07
S3-F04
```

No implementation may bypass, duplicate, or replace the existing authorities belonging to those dependencies.

---

# Non-Interpretation Rule

This document captures requirements, not implementation conclusions.

During analysis or implementation:

- Do not assume an item is complete because a similarly named class, endpoint, event, migration, component, or test exists.
- Do not weaken a requirement because the current architecture implements a narrower behavior.
- Do not silently introduce an alternative authority for:
  - workflow state
  - transitions
  - approvals
  - G07
  - stage-plan locking
  - workspace copying
  - leases
  - command execution
  - cancellation
  - artifacts
  - evidence
  - events
  - persistence
  - frontend state
- Record conflicts between this snapshot and the implementation explicitly.
- Treat missing dependency contracts as blockers instead of implementing competing substitutes.
- Keep the original migration source unchanged.
- Require durable evidence before declaring protected operations or steps complete.
