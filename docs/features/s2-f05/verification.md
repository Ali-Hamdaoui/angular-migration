# S2-F05 Verification Record

## Feature

S2-F05 — Resolve the family route, support level, and exact Stage 1 profile
with G05.

This record covers S2-F05-I04 and verifies the I01 backend contract, I02
persistence/API evidence boundary, and I03 frontend projection. It does not
authorize Angular command execution, Angular 22 behavior, LLM-selected
versions, or later planning/stage-execution issues.

## Acceptance mapping

| Requirement | Verification |
| --- | --- |
| Deterministic route and support truth | Backend tests assert the 18.x→19.x→20.x→21.x ladder, catalogue-owned support classification, exact Stage 1 Angular/CLI/Node/npm profile, and G05 creation. |
| Evidence and events | Persistence tests assert six registered SHA-256 artifacts, safe artifact links, immutable retrieval, and ordered `COMPATIBILITY_RESOLUTION_STARTED` then completion/blocked events. |
| Invalid, stale, and unauthorized input | Tests assert stable validation, `STALE_STATE_VERSION`, authorization rejection, prerequisite checksum rejection, and no unauthorized resolution/event mutation. |
| G05 binding and protected progression | Tests assert idempotent replay, blocked/pending approval rejection, tampered package rejection, and binding checks before decisions/progression. |
| Failure and frontend behavior | Tests assert redacted backend failure with no partial authoritative records and UI correlation guidance, blocked state, empty state, and stale reload. |

## Automated verification

Executed from the repository root or workspace directories:

```powershell
python -m pytest backend/tests/test_compatibility_application_service_s2_f05_i01.py backend/tests/test_compatibility_evidence_persistence_api_s2_f05_i02.py backend/tests/test_compatibility_verification_s2_f05_i04.py -q
python -m pytest backend/tests -q
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

The I04 test uses temporary SQLite and Artifact Store roots. Generated full
Angular workspaces are not stored in the repository. The live browser scenario
remains manual evidence and is not represented as an automated pass.

## Manual verification scenario

1. Start the backend and frontend with an authenticated local reviewer/operator
   identity, then open an authoritative run with the required prior evidence.
2. Open the Feasibility view and confirm the empty state before resolution.
3. Resolve the route using a synthetic Angular 18.x single-application fixture.
4. Confirm the deterministic 18.x→19.x→20.x→21.x ladder, support badge,
   exact Stage 1 Angular/CLI/Node/npm profile, warnings/blockers, six artifact
   links, and pending G05 package.
5. Refresh or disconnect/reconnect during the operation and confirm the view
   rehydrates from the backend snapshot/events without local workflow advance.
6. Open G05, submit an allowed decision with a review comment, and confirm the
   append-only decision and authoritative state update.
7. Repeat in isolated runs with malformed input, stale state, missing
   prerequisite, unavailable runtime, changed binding, and tampered package.
   Confirm a stable error, no illegal transition, no unauthorized artifact
   trust, and no progression from a pending/blocked gate.

## Evidence to retain

- six feasibility artifact IDs and SHA-256 checksums;
- catalogue and registry snapshot IDs/checksums;
- resolution, G05, and ordered event IDs/sequences;
- state versions before resolution, after package creation, and after decision;
- correlation ID and response envelope for one failure/authorization negative;
- screenshots or recording of the ladder/profile/G05 success state and one
  blocked or stale state.

## Manual environment note

Automated verification is reproducible with temporary local dependencies. A
live browser run requires an operator-configured backend/frontend and an
authenticated run fixture; until those are started, the manual scenario is
`manual_validation_required`, not an automated pass. Cleanup must use the
product-owned disposable workspace action and retain immutable evidence IDs.
