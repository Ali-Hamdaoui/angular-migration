# S2-F06 Verification Record

This record covers S2-F06-I04 and verifies the I01 backend contract, I02
persistence/API evidence boundary, and I03 frontend projection. It does not
authorize plan approval, plan modification, Angular command execution, or
optional modernization. Plan generation additionally requires the current
approved S2-F05/G05 package and uses its checksum-bound route, profile, and
artifact-set inputs.

## Acceptance mapping

| Requirement | Verification |
| --- | --- |
| Deterministic plan | Backend tests assert the complete adjacent family route, exact Stage 1 target, structured `shell=false` commands, policies, builder decision, and checksums. |
| Persistence and evidence | API integration tests assert plan/stage/decision/active-pointer records, seven registered artifacts, SHA-256 retrieval, and immutable read validation. |
| Events and replay | Persistence tests assert ordered `MIGRATION_PLAN_CREATED` then `STAGE_PLAN_CREATED`; frontend SSE tests assert ordered delivery and duplicate suppression. |
| Invalid, stale, and unauthorized input | Tests assert stable prerequisite, unsupported-builder, stale-version, authorization, and idempotency errors without unauthorized plan/event mutation. |
| Security and failure behavior | Tests assert shell syntax rejection, tampered artifact rejection, correlation-safe fail-closed provider errors, and no command execution. |
| Required corrections | Plan generation rejects missing/stale G05 approval and active plans; nested domain validation and integrity conflicts use canonical envelopes; durable artifact references are arrays; Angular CLI exact versions are separate command inputs; Alembic round-trip validation uses temporary SQLite. |
| Frontend behavior | Component tests cover route/Stage 1 inspection, empty prerequisites, stale reload, backend correlation guidance, and artifact links. |

## Automated verification

The primary seams use temporary SQLite and temporary Artifact Store roots. No
generated Angular workspace is stored in the repository and no migration
command is executed by this feature.

```powershell
python -m pytest backend/tests/test_planning_application_service_s2_f06_i01.py backend/tests/test_planning_evidence_persistence_api_s2_f06_i02.py backend/tests/test_planning_verification_s2_f06_i04.py -q
cd frontend
npm test -- src/hooks/__tests__/useMigrationEvents.test.ts src/components/__tests__/MigrationPlanPanel.test.tsx
npm run lint
npm run typecheck
npm run build
```

## Evidence to retain

- plan and first-stage artifact IDs with their SHA-256 checksums;
- event IDs/sequences for both plan-created events;
- state versions before generation and after the two legal transitions;
- one correlation ID and error envelope from an authorization or failure case;
- screenshots of the successful Plan viewer and one blocked/stale state.

## Manual verification status

The browser scenario below is reproducible with an authenticated local
operator and an external synthetic Angular 18.x fixture. Browser-driver
automation is not part of this repository; its result must be recorded as
`manual_validation_required` until the backend and frontend are launched.
