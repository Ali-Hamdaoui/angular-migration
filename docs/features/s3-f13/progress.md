# S3-F13 — Compare parity evidence, display assurance, and decide G09

## Status
COMPLETED

## Backend implementation
- `backend/app/domain/stage_assurance.py` — Assurance domain models and G09 gate
- `backend/app/domain/stage_comparison.py` — Route and backend comparison services
- `backend/app/services/stage_assurance_application_service.py` — Application service
- `backend/app/api/stage_assurance_contracts.py` — Pydantic contracts
- `backend/app/api/routes/stage_assurance.py` — Parity, summary, and approval endpoints
- `backend/app/api/approval_contracts.py` — Reusable approval contracts
- `backend/app/api/routes/approvals.py` — G09/G12 decision routes

## Frontend implementation
- `frontend/src/api/stageAssurance.ts` — Typed API client
- `frontend/src/components/StageAssurancePanel.tsx` — UI component

## Persistence
- `StageAssuranceModel`, `G09ApprovalModel` in workflow.py
- Alembic migration 20260719_09

## Events
PARITY_COMPARISON_STARTED, PARITY_COMPARISON_COMPLETED, PARITY_COMPARISON_FAILED, STAGE_VALIDATION_COMPLETED, G09_CREATED, G09_APPROVED, G09_REJECTED, G09_STALE
