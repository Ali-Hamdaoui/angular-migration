# S2-F07 Verification Record

This record covers S2-F07-I04 and verifies the I01 backend/domain contract,
I02 persistence/API evidence boundary, and I03 frontend projection for
Revise, explain, and approve the migration plan through G06. It does not
authorize free-form command editing, automatic approval, Stage 1 execution,
or later-stage resolution.

## Acceptance mapping

| Requirement | Verification |
| --- | --- |
| Bounded revision and immutable versions | I01 service tests and `test_verification_rejects_tampered_plan_binding_before_revision` verify plan/stage binding and immutable revision inputs. |
| Security and integrity negatives | Verification tests reject a tampered plan checksum and an unapproved custom builder; no revision is persisted by those paths. |
| Planning explanation | I01/I02 tests verify the Planning narrative and reviewer remain checksum-bound to deterministic plan facts. |
| G06 binding and progression blocker | Verification asserts stale approved G06 binding blocks protected stage start; I01/I02 tests cover pending, stale, and checksum mismatch decisions. |
| Persistence, artifacts, and events | I02 integration tests assert immutable plan/review records, registered SHA-256 artifacts, idempotency lineage, and durable PLAN_REVISION_CREATED, PLANNING_AGENT_COMPLETED, G06_CREATED, and decision events. |
| Frontend projection | `PlanReviewPanel.test.tsx` covers version/diff, separated explanation, evidence links, disabled prerequisites, stale, and correlation-ID failure presentation. Existing SSE tests cover duplicate suppression, sequence gaps, and reconnect/recovery. |

## Automated verification

The backend seams use temporary SQLite and Artifact Store roots; no generated
Angular workspace is committed and no migration command executes in this
issue. The frontend tests use typed API/hook seams and jsdom.

```powershell
.venv\Scripts\python.exe -m pytest -q `
  backend/tests/test_planning_review_application_service_s2_f07_i01.py `
  backend/tests/test_planning_review_evidence_s2_f07_i02.py `
  backend/tests/test_planning_review_verification_s2_f07_i04.py

Push-Location frontend
npm test -- --run src/components/__tests__/PlanReviewPanel.test.tsx src/api/__tests__/planningReview.test.ts src/hooks/__tests__/useMigrationEvents.test.ts
npm run lint
npm run typecheck
npm run build
Pop-Location
```

## Manual evidence to retain

- current and revised plan version IDs and SHA-256 checksums;
- diff artifact ID and checksum;
- Planning explanation and usage/cost artifact IDs;
- G06 package and append-only decision artifact IDs;
- durable event IDs/sequences for revision, stale approval, Planning Agent,
  G06 creation, and G06 decision;
- state versions before revision, explanation, and approval;
- one correlation ID from a stale, authorization, or backend-failure path;
- screenshots of successful review, disabled G06, and stale/failure states.

## Manual scenario

1. Launch the backend and frontend with an authenticated local reviewer and an
   external synthetic Angular 18.x fixture.
2. Open the run's Plan review surface and confirm the current plan checksum,
   Stage 1 checksum, registered artifact links, and pending G06 state.
3. Change one approved field, submit the bounded revision, and confirm a new
   immutable version, diff, stale dependent approval, and revision event.
4. Request the Planning explanation and confirm the narrative is displayed
   separately from executable plan facts and references the current checksum.
5. Open the G06 package, enter a comment, and approve the current plan.
6. Refresh the browser and disconnect/reconnect SSE; confirm the same backend
   snapshot and no duplicate action.
7. Repeat with a stale state version, tampered checksum, missing package, or
   rejected G06. Confirm a stable failure/stale presentation and that protected
   stage start remains blocked.

Manual browser execution is recorded as `manual_validation_required` until
the local backend and frontend are launched. Product-owned disposable fixture
workspaces are removed only through the approved cleanup action; immutable
evidence is retained.
