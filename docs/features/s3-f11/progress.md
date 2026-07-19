# S3-F11 — Run and inspect the required stage build matrix

## Status
COMPLETED

## Backend implementation
- `backend/app/domain/stage_build.py` — Build matrix domain models
- `backend/app/services/stage_build_application_service.py` — Application service
- `backend/app/api/stage_build_contracts.py` — Pydantic contracts
- `backend/app/api/routes/stage_build.py` — POST/GET endpoints

## Frontend implementation
- `frontend/src/api/stageBuild.ts` — Typed API client
- `frontend/src/components/StageBuildPanel.tsx` — UI component

## Persistence
- `StageBuildModel` in workflow.py
- Alembic migration 20260719_09

## Events
STAGE_BUILD_STARTED, TARGET_COMPLETED, STAGE_BUILD_COMPLETED, STAGE_BUILD_FAILED
