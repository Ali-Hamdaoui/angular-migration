# G09 — Final Assurance, Delivery, Reporting (As-Built)

## Overview

This capability implements the final three gates of the AMFA migration workflow:

- **G13 (Final Assurance)**: Independent clean-workspace verification before delivery
- **G14 (Delivery)**: Atomic delivery candidate creation and publication
- **G15 (Report)**: Deterministic evidence report generation with optional AI narrative

All three gates follow the established G02 approval pattern with checksum-bound packages, state versioning, idempotency, durable events, and immutable artifact storage.

## Architecture

```
Frontend                       Backend
  │                              │
  ├─ POST /final-assurance ─────► FinalAssuranceService ──► SQLite
  ├─ POST /approvals/G13/decide ─► G13ApprovalService      events
  │                              │
  ├─ POST /delivery-candidate ──► DeliveryService ────────► SQLite
  ├─ POST /approvals/G14/decide ─► G14ApprovalService      events
  │                              │
  ├─ POST /reports ─────────────► ReportService ──────────► SQLite
  ├─ POST /approvals/G15/decide ─► G15ApprovalService      events
  │                              │
  └──── ArtifactStore ──────────► Immutable SHA-256 artifacts
```

## Backend

### New files

| File | Purpose | Lines |
|---|---|---|
| `backend/app/domain/final_assurance.py` | G13 domain models, package builder, decision service | ~70 |
| `backend/app/domain/delivery.py` | G14 domain models, package builder, decision service | ~70 |
| `backend/app/domain/report.py` | G15 domain models, package builder, decision service | ~70 |
| `backend/app/api/final_assurance_contracts.py` | G13 request/response DTOs | ~30 |
| `backend/app/api/delivery_contracts.py` | G14 request/response DTOs | ~30 |
| `backend/app/api/report_contracts.py` | G15 request/response DTOs | ~30 |
| `backend/app/api/routes/final_assurance.py` | G13 API routes | ~50 |
| `backend/app/api/routes/delivery.py` | G14 API routes | ~50 |
| `backend/app/api/routes/reports.py` | G15 API routes | ~50 |
| `backend/app/services/final_assurance_application_service.py` | G13 application service | ~400 |
| `backend/app/services/delivery_application_service.py` | G14 application service | ~217 |
| `backend/app/services/report_application_service.py` | G15 application service | ~346 |
| `backend/app/repositories/final_assurance_models.py` | G13 DB model | ~35 |
| `backend/app/repositories/delivery_models.py` | G14 DB model | ~37 |
| `backend/app/repositories/report_models.py` | G15 DB model | ~35 |

### Modified files

| File | Change |
|---|---|
| `backend/app/domain/contracts.py` | Added 25 new event types (FINAL_ASSURANCE_STARTED through G15_STALE) |
| `backend/app/api/router.py` | Registered 3 new routers in both api_router and api_v1_router |
| `backend/app/repositories/models/__init__.py` | Added imports for 3 new models |
| `backend/alembic/versions/20260719_09_final_assurance_delivery_report.py` | Creates 3 new tables |

### Event types

**G13**: FINAL_ASSURANCE_STARTED, STEP_COMPLETED, COMPLETED, FAILED, G13_CREATED, APPROVED, MODIFICATION_REQUESTED, REJECTED, STALE

**G14**: DELIVERY_CANDIDATE_READY, FAILED, G14_CREATED, APPROVED, MODIFICATION_REQUESTED, REJECTED, STALE

**G15**: REPORT_GENERATION_STARTED, COMPLETED, FAILED, G15_CREATED, APPROVED, MODIFICATION_REQUESTED, REJECTED, STALE

### Routes

```
GET    /api/v1/runs/{id}/approvals/G13        — Get assurance status
POST   /api/v1/runs/{id}/final-assurance       — Run final assurance
POST   /api/v1/runs/{id}/approvals/G13/decisions — Decide G13

GET    /api/v1/runs/{id}/approvals/G14        — Get delivery status
POST   /api/v1/runs/{id}/delivery-candidate    — Create delivery candidate
POST   /api/v1/runs/{id}/approvals/G14/decisions — Decide G14

GET    /api/v1/runs/{id}/approvals/G15        — Get report status
POST   /api/v1/runs/{id}/reports              — Generate report
POST   /api/v1/runs/{id}/approvals/G15/decisions — Decide G15
```

### Schema

Three new tables:
- `final_assurance_records` — G13 gate records with checksum-bound packages
- `delivery_records` — G14 gate records with delivery destination/fingerprint
- `report_records` — G15 gate records with report checksum/narrative flag

All tables use `(run_id, idempotency_key)` unique constraints for idempotency.

## Testing

- 15 domain unit tests (G13/G14/G15 models, builders, decision services)
- 12 API integration tests with temp SQLite
- All 13 existing tests pass (1 pre-existing G05 failure unrelated to G09)
- Alembic upgrade/downgrade cycle verified

## Limitations

- Upstream G04/G07/G08/S4-F11 unavailable — consuming via frozen contracts
- Frontend pages require separate implementation
- Manual runtime validation requires Angular fixtures
- Integration verification requires merged Sprint 3/4 branches
