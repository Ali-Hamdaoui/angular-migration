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
| Evidence is persisted and immutable | I02 integration tests assert five registered artifacts, SHA-256 checksums, safe artifact links, no raw content, and state/event versions. |
| Durable event chain | Frontend SSE tests cover `ANALYSIS_AGENT_STARTED`, `ANALYSIS_AGENT_COMPLETED`, `G04_CREATED`, and `G04_APPROVED`, including duplicate suppression and sequence-gap recovery. Backend tests assert ordered Analysis/G04 events. |
| G04 decisions are bound and append-only | Backend tests cover approval, approval-with-comment, rejection, idempotent replay, stale state, and stale package checksum. |
| Failure and security behavior | Provider failure is redacted and fails closed; invalid prerequisite checksums create no Analysis events; blocked/schema-invalid UI content is rendered as text and never as HTML. |
| Authoritative frontend projection | Component tests cover empty, completed split-view, backend failure/correlation ID, stale conflict, blocked analysis, artifact links, provenance, usage/cost, and required-comment validation. |

## Automated verification

Executed from the repository root or the `frontend` directory as shown:

```powershell
python -m pytest backend/tests/test_analysis_application_service_s2_f04_i01.py backend/tests/test_analysis_evidence_persistence_api_s2_f04_i02.py -q
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Expected results for the current implementation:

- Feature 4 backend regression suite passes.
- Full frontend suite passes.
- Typecheck and production build pass.
- Lint has one pre-existing warning in `BaselinePreparationPanel.tsx`.

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

## Known limitations

The automated suite uses fake gateways and temporary SQLite/artifact stores as
required by the sprint testing boundary. Live Azure OpenAI behavior and browser
screenshots require the local manual scenario and are not claimed by automated
tests. The existing unrelated lint warning remains unchanged.
