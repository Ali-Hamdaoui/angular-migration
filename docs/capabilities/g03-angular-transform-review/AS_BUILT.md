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
| API | `api/routes/transformations.py` | 10 REST endpoints registered under `/runs/{id}/stages/{stageId}/` |
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

|- **Domain unit tests**: 21 tests (`test_g03_domain.py`) covering all domain models, builders, and decision rules
- **API integration tests**: 13 tests (`test_g03_api.py`) covering Angular update, transformation evidence, and G08 approval flows; prerequisite-missing and non-authoritative command fixtures fail closed
- **AMFA-178 service tests**: 13 tests (`test_angular_update_amfa178.py`) covering worker dispatch, idempotency, prompts, target disagreement, partial mutation, timeout, and cancellation
- **AMFA-179 API tests**: 8 tests (`test_angular_update_amfa179.py`) covering complete/verify routes and artifact integrity
- **Policy tests**: 8 tests (`test_angular_update_policy_amfa178.py`) covering the exact local CLI shape, forbidden flags, and registered verification commands
- **Frontend component tests**: 17 tests (`AngularUpdatePanel.test.tsx`) covering all view states, SSE transitions, accessibility
- **Frontend API client tests**: 11 tests (`transformations.test.ts`) covering all 10 transformation API functions
- **Focused regression**: 63 AMFA-181/G03 tests pass on Windows; the full repository suite still has unrelated command-runtime and S2 planning/compatibility failures

### Evidence Matrix

The transformation evidence captures the following artifact types for each changed file:

| Artifact Type | Classification | Risk Level | Example Patterns |
|---------------|---------------|------------|------------------|
| TypeScript/JS source | `low_risk` | Low | `*.ts`, `*.js`, `*.html` |
| Generated/built output | `generated` | Low | `dist/`, `build/`, `.angular/`, `node_modules/` |
| Binary assets | `binary` | Low | `*.png`, `*.jpg`, `*.ico`, `*.exe`, `*.dll` |
| Package lockfiles | `medium_risk` | Medium | `package-lock.json`, `yarn.lock` |
| Auth/security files | `sensitive` | High | Paths containing `auth`, `security`, `credential` |
| CI/CD configs | `forbidden` | Critical | `.github/workflows/`, `.gitlab-ci.yml` |
| Credential files | `forbidden` | Critical | `.env`, `secrets`, `*.pem`, `kubeconfig` |
| Security policy files | `forbidden` | Critical | `security/`, `.htaccess`, `snyk`, `codeql` |
| Unknown extensions | `unknown` | Varies | `*.xyz`, unrecognized formats |

Each file's content is scanned for sensitive patterns (HTTP clients, router guards, form modules, lifecycle hooks, theme configuration, deprecated APIs, DOM manipulation) and assigned a `SensitiveChangeReason` to inform the reviewer.

### Security Protections

| Protection | Implementation |
|------------|----------------|
| File size guard | Files >50MB are classified `GENERATED` and their content is not read (avoids OOM from large binary files) |
| Binary detection | Binary extensions (`.exe`, `.dll`, `.png`, etc.) are classified `BINARY` without content scanning |
| Credential leak prevention | Paths matching credential patterns (`.env`, `secrets`, `*.pem`, `kubeconfig`) are classified `FORBIDDEN` (critical risk) |
| CI/CD tampering detection | CI/CD pipeline files (`.github/workflows`, `.gitlab-ci.yml`, etc.) are classified `FORBIDDEN` |
| Security policy change detection | Security config files (`security/`, `.htaccess`, `snyk`, `codeql`) are classified `FORBIDDEN` |
| Content-based secret scanning | Content patterns for DOM access, cookies, `eval()` usage flagged as `SECURITY_RELEVANT` |
| State version idempotency | Evidence operations are guarded by expected state version and idempotency keys to prevent replay/stale-write attacks |

## Dependencies

- Consumes contracts: `approved_stage_plan`, `stage_sandbox_ready`, `command_execution_record`, `artifact_ref`, `durable_event_envelope`
- Provides no standalone JSON schema; evidence is returned inline via the `/transformation-evidence` API response using the `TransformationEvidenceResult` Pydantic model as the implicit contract
- Depends on G02 for upstream integration

## Limitations

- Full Angular fixture generation must be done outside Git through production intake APIs
- `integration_verified` remains `false` until cross-goal integration evidence exists
- Manual runtime verification against the merged full application is deferred until the upstream G02 runtime and integrated application are available; no manual pass is claimed here.
