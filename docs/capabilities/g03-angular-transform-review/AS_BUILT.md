# G03 — Exact Angular Transformation and G08 — As-Built Documentation

## Overview

G03 implements three capabilities for the AI Migration Factory:
- **S3-F07/AMFA-146**: Execute the exact Angular update and verify the target version
- **S3-F08/AMFA-147**: Capture transformation diffs and classify changed-file risk
- **S3-F09/AMFA-148**: Review and decide G08 transformation acceptance

## Architecture

All G03 logic follows the existing domain → service → API pattern established by G02 and other features. The new code adds:

### Backend Structure

| Layer | Module | Purpose |
|-------|--------|---------|
| Domain | `domain/transformation.py` | Pure Pydantic models and checksum-bound builders with zero persistence side effects |
| Contracts | `api/transformation_contracts.py` | FastAPI request/response DTOs for all G03 endpoints |
| Service | `services/transformation_application_service.py` | AMFA-178 locked-plan validation, worker dispatch, bounded output, and exact target evidence; sibling evidence/approval services unchanged |
| API | `api/routes/transformations.py` | 9 REST endpoints registered under `/runs/{id}/stages/{stageId}/` |
| DB | `repositories/transformation_models.py` | 3 SQLAlchemy models: `AngularUpdateRecordModel`, `TransformationEvidenceModel`, `G08ApprovalModel` |
| Migration | `alembic/versions/20260719_07_*` | Append-only schema migration |

### Frontend Structure

| Component | Feature | Purpose |
|-----------|---------|---------|
| `AngularUpdatePanel.tsx` | S3-F07 | Version matrix, start update, live logs, target verification |
| `TransformationEvidenceViewer.tsx` | S3-F08 | Diff file tree, risk filters, package changes, forbidden changes |
| `G08ReviewWorkspace.tsx` | S3-F09 | Decision controls, comments, stale warnings, evidence summary |

### Event Types Added

- `ANGULAR_UPDATE_STARTED/COMPLETED/FAILED`
- `INTERACTIVE_DECISION_REQUIRED`
- `TARGET_VERSION_VERIFIED/FAILED`
- `TRANSFORMATION_EVIDENCE_STARTED/COMPLETED/BLOCKED`
- `APPROVAL_GATE_CREATED`, `G08_CREATED/APPROVED/REJECTED/MODIFICATION_REQUESTED/STALE`

## API Endpoints

| Method | Path | Feature |
|--------|------|---------|
| POST | `/api/v1/runs/{id}/stages/{stageId}/angular-update` | S3-F07 |
| GET | `/api/v1/runs/{id}/stages/{stageId}/angular-update` | S3-F07 |
| GET | `/api/v1/runs/{id}/stages/{stageId}/target-version` | S3-F07 |
| POST | `/api/v1/runs/{id}/stages/{stageId}/angular-update/complete` | S3-F07 |
| POST | `/api/v1/runs/{id}/stages/{stageId}/target-version/verify` | S3-F07 |
| POST | `/api/v1/runs/{id}/stages/{stageId}/transformation-evidence` | S3-F08 |
| GET | `/api/v1/runs/{id}/stages/{stageId}/transformation-evidence` | S3-F08 |
| GET | `/api/v1/runs/{id}/stages/{stageId}/approvals/G08` | S3-F09 |
| POST | `/api/v1/runs/{id}/stages/{stageId}/approvals/G08/decisions` | S3-F09 |
| POST | `/api/v1/runs/{id}/stages/{stageId}/approvals/G08/package` | S3-F09 |

## Domain Rules

### G08 Approval Gate Rules (fail-closed)
- Approval requires complete evidence (`evidence_complete == true`)
- Evidence with `CRITICAL` risk level is automatically rejected
- `APPROVED_WITH_COMMENT` requires a non-empty comment
- Stale packages (evidence changes after package creation) are detected and marked stale

## Test Coverage

|- **Domain unit tests**: 21 tests covering all domain models, builders, and decision rules
- **API integration tests**: 9 tests covering happy paths, stale state, 404s, G08 approve/reject flows
- **Regression**: 33 existing tests continue to pass with no changes required

## Dependencies

- Consumes contracts: `approved_stage_plan`, `stage_sandbox_ready`, `command_execution_record`, `artifact_ref`, `durable_event_envelope`
- Provides contract: `transformation_result.schema.json`
- Depends on G02 for upstream integration

## Limitations

- Full Angular fixture generation must be done outside Git through production intake APIs
- `integration_verified` remains `false` until cross-goal integration evidence exists
