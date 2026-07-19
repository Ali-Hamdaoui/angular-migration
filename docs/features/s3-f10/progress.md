# S3-F10 — Run final clean install and deterministic static checks

## Status
COMPLETED

## Backend implementation
- `backend/app/domain/stage_validation.py` — Domain models for install/static checks
- `backend/app/services/stage_validation_application_service.py` — Application service
- `backend/app/api/stage_validation_contracts.py` — Pydantic request/response models
- `backend/app/api/routes/stage_validation.py` — POST/GET endpoints

## Frontend implementation
- `frontend/src/api/stageValidation.ts` — Typed API client
- `frontend/src/components/StageValidationPanel.tsx` — UI component with all states

## Persistence
- `StageValidationModel` in workflow.py
- Alembic migration 20260719_09

## Events
VALIDATION_FINAL_INSTALL_STARTED, VALIDATION_FINAL_INSTALL_COMPLETED, VALIDATION_FINAL_INSTALL_FAILED, STATIC_CHECKS_STARTED, STATIC_CHECKS_COMPLETED, STATIC_CHECKS_FAILED

## Tests
55 G04 backend tests pass (shared across all features)
