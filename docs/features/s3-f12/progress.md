# S3-F12 — Run complete stage tests and conditional lint

## Status
COMPLETED

## Backend implementation
- `backend/app/domain/stage_tests.py` — Test/lint domain models
- `backend/app/services/stage_tests_application_service.py` — Application service
- `backend/app/api/stage_tests_contracts.py` — Pydantic contracts
- `backend/app/api/routes/stage_tests.py` — POST/GET endpoints

## Frontend implementation
- `frontend/src/api/stageTests.ts` — Typed API client
- `frontend/src/components/StageTestPanel.tsx` — UI component

## Persistence
- `StageTestModel` in workflow.py
- Alembic migration 20260719_09

## Events
STAGE_TESTS_STARTED, STAGE_TESTS_COMPLETED, STAGE_TESTS_FAILED, STAGE_LINT_STARTED, STAGE_LINT_COMPLETED, STAGE_LINT_FAILED

## Naming note
`StageTestApplicationError` was renamed to `StageTestError` to match project domain conventions.
