# S1-F11 progress

S1-F11 — Execute and inspect the frozen baseline clean installation.

## Delivered issues

- S1-F11-I01: exact frozen `npm ci` command policy and deterministic post-install inspection.
- S1-F11-I02: durable command execution persistence, typed install/status API, ordered command/install events, idempotent replay, and checksum-bound artifact metadata.

## I02 evidence

The backend records the command definition, runtime and baseline checksums, lifecycle status, timing, exit code, cancellation/timeout/reconstruction state, fingerprints, stable blockers, and artifact references. The install request is accepted only for an authorized, unblocked S1-F10 baseline with a checksum-matched selected execution profile and valid lockfile.

API routes:

- `POST /api/v1/runs/{runId}/baseline/install`
- `GET /api/v1/runs/{runId}/commands/{executionId}`

The existing artifact routes expose the immutable evidence by run path or artifact ID.

## Scope boundary

Frontend install controls and reconnect presentation belong to S1-F11-I03. Security/regression/documentation completion belongs to S1-F11-I04.