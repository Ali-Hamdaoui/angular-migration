# As-Built Documentation — G02 Stage Workspace Bootstrap

## Overview

This capability implements the **S3-F05** (stage sandbox preparation + G07 gate) and **S3-F06** (stage bootstrap clean install) features from the AMFA migration control tower. These features enable creating isolated run-scoped stage sandboxes from the source snapshot, obtaining G07 approval, and running the bootstrap clean install.

## Architecture

```text
User/Reviewer
     │ typed HTTP + SSE
     ▼
Next.js Frontend (StagePreparationPanel, BootstrapInstallPanel)
     │ typed API calls (POST/GET)
     ▼
FastAPI Routes (stages.py)
     │
     ├── StagePreparationApplicationService  ──► MigrationStage / StageWorkspace / G07Approval
     ├── StageBootstrapApplicationService    ──► CommandExecution / StageStep
     ├── TransitionService                   ──► WorkflowEvent (durable events)
     └── ArtifactStore                       ──► Immutable SHA-256 evidence
```

## Backend Modules

### Domain (`backend/app/domain/stage_workspace.py`)

Pure domain models with no side effects:
- **G07Decision** — Approval gate decision enum (APPROVED, REJECTED, etc.)
- **StageStatus** — Stage lifecycle states
- **StageExecutionPlan** — Locked plan for a stage
- **WorkspaceCopyReport** — Report of sandbox copy operation
- **StageInputManifest** — Input manifest for sandbox preparation
- **G07ApprovalPackage** — Checksum-bound evidence package
- **G07ApprovalService** — Fail-closed decision rules
- **G07ApprovalPackageBuilder** — Canonical package builder

### Persistence (`backend/app/repositories/stage_workspace_models.py`)

- **G07ApprovalModel** — `g07_approvals` table (run+stage scoped, idempotent)
- **StageWorkspaceModel** — `stage_workspaces` table (fingerprint tracking)

### Services

- **StagePreparationApplicationService** — Stage creation, sandbox copy, G07 decision
- **StageBootstrapApplicationService** — Bootstrap install authorization and execution

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/runs/{id}/stages/{stageId}/prepare` | Create stage and lock plan |
| POST | `/runs/{id}/stages/{stageId}/sandbox` | Create isolated sandbox |
| GET | `/runs/{id}/approvals/G07?stage_id=` | Get G07 gate status |
| POST | `/runs/{id}/approvals/G07/decisions` | Submit G07 decision |
| POST | `/runs/{id}/stages/{stageId}/bootstrap-install` | Run bootstrap install |
| GET | `/runs/{id}/stages/{stageId}/steps/bootstrap-install` | Get install status |

### Durable Events

- `STAGE_CREATED`, `STAGE_PREPARING`, `STAGE_PLAN_LOCKED`, `STAGE_WAITING_APPROVAL`, `STAGE_SANDBOX_READY`
- `G07_CREATED`, `G07_APPROVED`, `G07_REJECTED`, `G07_STALE`
- `STAGE_BOOTSTRAP_INSTALL_STARTED`, `STAGE_BOOTSTRAP_INSTALL_COMPLETED`, `STAGE_BOOTSTRAP_INSTALL_FAILED`

### Artifact Evidence

- Stage-start package with exact plan/profile
- Copy report, input manifest, fingerprints
- Sandbox verification
- Install command/logs/result

## Frontend Modules

- `frontend/src/api/stages.ts` — Typed API client
- `frontend/src/components/StagePreparationPanel.tsx` — Stage review UI with G07 controls
- `frontend/src/components/BootstrapInstallPanel.tsx` — Bootstrap step card

## Migration

Alembic migration `20260720_01_stage_workspace_g07.py` creates:
- `g07_approvals` table
- `stage_workspaces` table
