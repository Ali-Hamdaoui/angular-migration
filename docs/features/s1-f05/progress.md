# S1-F05 Progress

Feature: Create a checksum-bound production preflight and decide G01.

## Implemented

- Durable preflight, approval-gate, append-only decision, and preflight-event records.
- Immutable evidence package with request, environment, path, eligibility, result, and G01 index artifacts.
- SHA-256 input and artifact-set bindings with expiry, blocker enforcement, stale-input rejection, and idempotent decisions.
- Versioned API under `/api/v1/preflights` and the documented draft approval route.
- Replayable preflight SSE events with `Last-Event-ID`, centralized draft-gate transitions, and generated OpenAPI coverage.
- GET projection includes current G01 status and append-only decision history.

## Authority decisions

- G01 is explicit human approval; no automatic approval path was added.
- Preflight evidence is composed from the persisted S1-F02, S1-F03, and S1-F04 snapshots.
- A G01 decision does not create a migration run; run creation remains S1-F06.

## Validation

- `python -m pytest backend/tests/test_production_preflight.py -q` — passed (2 tests).
- Frontend typecheck/build and the complete backend suite remain to be run at the issue review checkpoint.
