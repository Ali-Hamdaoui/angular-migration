# S2-F04 Verification Record

## Feature

S2-F04 — Generate a checksum-bound Analysis phase review chain and decide G04.

This record covers S2-F04-I04 and verifies the completed I01 backend contract,
I02 persistence/API evidence boundary, and I03 frontend projection. The feature
does not authorize Planning Agent behavior, repair roles, repository browsing,
support-level determination by AI, or workflow advancement from the browser.

## Acceptance mapping

| Requirement | Verification |
| --- | --- |
| Deterministic facts remain authoritative | Analysis application tests bind the narrative to registered artifact IDs/checksums and reject mismatches before provider calls. |
| Proposer/Reviewer review chain | Tests require a checksum-bound phase Proposer result, a non-authoring phase Reviewer result, one bounded revision, and Reviewer acceptance before G04 can be created. |
| Evidence is persisted and immutable | I02 integration tests assert registered input, Proposer, Reviewer, final-reviewed-analysis, human-readable, usage, and G04 package artifacts with SHA-256 checksums and safe links. |
| Durable event chain | Frontend and backend tests cover `ANALYSIS_AGENT_*`, `ANALYSIS_REVIEWER_*`, and `G04_*`, including duplicate suppression and sequence-gap recovery. |
| G04 decisions are bound and append-only | Backend tests cover approval, rejection, idempotent replay, state/package/workspace/plan binding, package-integrity failure, stale records, and protected-transition blocking. |
| Failure and security behavior | Provider failure is redacted and fails closed; invalid prerequisite checksums create no Analysis events; blocked/schema-invalid UI content is rendered as text and never as HTML. |
| Authoritative frontend projection | Component tests cover empty, completed split-view, backend failure/correlation ID, stale conflict, blocked analysis, artifact links, provenance, usage/cost, and required-comment validation. |

## Automated verification

Executed from the repository root or the `frontend` directory as shown:

```powershell
python -m pytest backend/tests/test_analysis_application_service_s2_f04_i01.py backend/tests/test_analysis_evidence_persistence_api_s2_f04_i02.py -q
python -m pytest -q
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Expected results for the current implementation:

- Feature 4 backend regression suite passes, including Review-chain, integrity,
  and protected-progression coverage.
- Full backend suite passes: 370 passed, 2 skipped.
- Full frontend suite passes.
- Typecheck and production build pass.
- Lint has one pre-existing warning in `BaselinePreparationPanel.tsx`.
- An isolated Alembic upgrade → downgrade → upgrade round trip passes through
  revision `20260719_03`.

## Manual verification scenario

1. Start the backend and frontend with an authenticated local reviewer identity.
2. Open an authoritative run that has the approved G03 baseline and registered deterministic evidence.
3. Open the Analysis/G04 panel and confirm the empty state before generation.
4. Generate analysis and observe `ANALYSIS_AGENT_STARTED`, running state, `ANALYSIS_AGENT_COMPLETED`, and `G04_CREATED`.
5. Confirm the split view separates registered deterministic artifact references from the AI narrative.
6. Inspect provider/role/prompt/schema provenance, token counts, estimated cost, five artifact links, and the G04 package checksum.
7. Refresh or disconnect/reconnect while the operation is running; confirm the panel rehydrates from the backend snapshot without duplicate action.
8. Submit `approve`, `approve_with_comment`, `request_modification`, and `reject` in isolated runs. Confirm only backend-authoritative state changes are displayed.
9. Repeat with a stale state version or changed package checksum. Confirm `STALE_STATE_VERSION` or `STALE_ANALYSIS_PACKAGE`, snapshot reload, and no progression to the next phase.
10. Repeat with a provider failure, blocked/schema-invalid response, unauthorized actor, or tampered prerequisite checksum. Confirm correlation guidance, fail-closed behavior, preserved safe evidence, and no illegal transition.

## Evidence to retain

- Analysis artifact IDs and SHA-256 checksums.
- G04 package artifact ID/checksum.
- Analysis and G04 event IDs/sequences.
- State versions before generation and after the decision.
- Correlation ID for any failure or authorization rejection.
- Screenshots or screen recording of the split view and one negative path.

## Executed manual-environment check

On 2026-07-19 the local environment was inspected before attempting the live
scenario. `LLM_ENABLED` was `false`, Azure endpoint/deployment/API-key settings
were absent, and no backend or frontend server was running. A live authenticated
Azure OpenAI/browser run was therefore not attempted: it would only fail at the
configured provider boundary and could not produce valid evidence.

The automated FastAPI + temporary SQLite + Artifact Store seam was executed
instead. It exercised an authenticated actor, G03 prerequisite, Proposer and
Reviewer chain, immutable artifacts, G04 decisions, stale integrity rejection,
and protected-transition guard. Retain this record with the command output when
an operator executes the live scenario below.

## Remaining environment prerequisite

The live Azure/browser scenario remains blocked until an authorized operator
provides a configured Azure deployment and starts the authenticated backend and
frontend. The existing unrelated lint warning remains unchanged.
