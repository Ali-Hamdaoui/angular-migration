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

## I04 verification evidence

S1-F11-I04 adds regression and security coverage for stale state, removed authorization, and runtime checksum authority bypasses. Frontend API tests verify encoded install/status routes and checksum-bound request fields. Frontend component tests cover selected-profile start, blocked runtime, reconnecting state, and cancellation result rendering.

Manual verification scenario:

1. Start the backend and frontend against a clean run created through the documented S1-F10 path.
2. Create the baseline sandbox, prequalify the package, authorize installation, and select an exact ExecutionProfile.
3. In the Control Tower, verify the install card is blocked until all prerequisites are present, then start the frozen `npm ci` command.
4. Observe the ordered `COMMAND_QUEUED`, `COMMAND_STARTED`, output, and terminal install event states; refresh the browser during execution and verify status recovery from authoritative state.
5. Cancel a running installation and verify the terminal cancellation state, partial log/artifact references, and reconstruction warning when reported.
6. Inspect the command record, event sequence, state version, artifact IDs/checksums, `npm-ci-command.json`, stdout/stderr logs, dependency-tree verification, lockfile post-install verification, and summary artifact.
7. Confirm the original source path is unchanged and verify negative cases: stale state, missing authorization, mismatched runtime checksum, and invalid/blocked lockfile do not start a command.

The local MVP reports controlled local execution; it does not claim hardened isolation from package lifecycle scripts. Capture run ID, execution ID, event IDs/sequences, artifact IDs/checksums, screenshots, and any environment blocker as manual evidence.

## Scope boundary

S1-F11 is complete through I04. Build/test/lint matrix work belongs to S1-F12.