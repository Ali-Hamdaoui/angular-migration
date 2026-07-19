# S3-F14 — Seal G12, copy forward, and reuse the parameterized stage engine

## Status
COMPLETED

## Backend implementation
- `backend/app/domain/stage_seal.py` — Seal and copy-forward domain models
- `backend/app/domain/stage_copy_forward.py` — Copy-forward domain models
- `backend/app/services/stage_seal_application_service.py` — Application service
- `backend/app/api/stage_seal_contracts.py` — Pydantic contracts
- `backend/app/api/routes/stage_seal.py` — Complete package, G12 decisions, copy-forward endpoints

## Frontend implementation
- `frontend/src/api/stageSeal.ts` — Typed API client
- `frontend/src/components/StageSealPanel.tsx` — UI component

## Persistence
- `StageSealModel`, `StageCopyForwardRecord`, `OutputFingerprintModel`, `G12ApprovalModel` in workflow.py
- Alembic migration 20260719_09

## Events
STAGE_CLEANUP_COMPLETED, STAGE_WAITING_APPROVAL, STAGE_COMPLETED, STAGE_SEALED, NEXT_STAGE_CREATED, NEXT_STAGE_SANDBOX_READY, COPY_FORWARD_STARTED, COPY_FORWARD_COMPLETED, G12_CREATED, G12_APPROVED, G12_REJECTED, G12_STALE
