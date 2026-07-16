# S1-F13 Progress

## Delivered issues

- S1-F13-I01: deterministic failure fingerprints, structural route inventory, backend-integration indicators, confidence labels, and parser/schema versions.
- S1-F13-I02: checksum-bound persistence, immutable evidence artifacts, versioned API routes, idempotency, and authoritative workflow events.
- S1-F13-I03: Control Tower baseline parity evidence tabs, confidence/provenance display, reconnect state, and capture action.
- S1-F13-I04: regression/security coverage, SSE replay coverage, frontend verification, and this traceability/manual-validation record.

## Security and authority boundary

Parity capture reads the authorized baseline sandbox and already-produced validation evidence. It does not execute source code, mutate the source or sandbox, infer functional parity, or let the frontend advance workflow state. Failure fingerprints are explicitly `pre-existing`; incomplete route/backend evidence is `unknown` rather than a parity claim. Endpoint values are reduced to scheme/host/path without credentials or query strings, and evidence is exposed through immutable artifact references and checksums.

## Automated verification

I04 covers stable identity under normalized paths, repeated and one-shot diagnostics, parser-version drift, pre-existing origin classification, conservative empty-evidence confidence, credential/query redaction, versioned API capture, immutable artifact/event persistence, idempotent replay, stale state, SSE replay after reconnect, and frontend rendering/stale-state behavior.

## Manual acceptance scenario

1. Run the S1-F12 known-failure fixture and capture baseline parity from the Control Tower.
2. Inspect known failures and confirm stable fingerprints, `pre-existing` origin, occurrence counts, parser version, schema version, artifact IDs, and checksums.
3. Repeat capture/reload and verify the same evidence is shown; reconnect with an SSE `Last-Event-ID` and confirm ordered parity events replay without creating a second capture.
4. Inspect routes and backend integration. Confirm they are structural anchors with confidence labels, not a functional parity conclusion.
5. Use a fixture with incomplete route/backend evidence. Confirm confidence is `unknown`/`NOT_PROVEN` and no secret, credential, query token, or source content is displayed.

## Scope boundary

Deep semantic route analysis, full API contract extraction, migration-caused failure classification, functional parity conclusions, AI analysis, and G03 qualification remain outside S1-F13.
