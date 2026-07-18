# S1-F11 — Frozen baseline clean installation

Feature 11 executes the approved baseline `npm ci` command only in the qualified `BASELINE_SANDBOX`.

## Authoritative flow

1. `POST /api/v1/runs/{run_id}/baseline/install` validates G02 approval, the selected execution-profile checksum, install authorization, sandbox registration, and the qualified lockfile checksum.
2. The application service persists `COMMAND_QUEUED` and accepts the command asynchronously.
3. The sole CommandExecutor runs the frozen `npm ci` template with `shell=false`, bounded live output, timeout, and process-tree cancellation.
4. Output chunks and terminal events are persisted through the Transition Service. Full stdout/stderr, npm debug logs, fingerprints, dependency-tree verification, and summary artifacts are stored by artifact ID.
5. The frontend resumes from the authoritative run snapshot/SSE stream and exposes status, elapsed time, logs, cancellation, failure classification, and artifacts.

## Recovery and cancellation

Cancellation is persisted on the command execution before the process signal is sent. Worker leases include execution ID, worker ID, backend instance ID, heartbeat, and expiry. On startup, orphaned commands are compared with their start fingerprints: unchanged inputs are safely rerun; changed or unavailable inputs are marked for baseline reconstruction.

## Validation

- Backend: `python -m pytest -q`
- Frontend: `npm run typecheck`, `npm run test`, `npm run build`
- Database: `python -m alembic -c alembic.ini heads` and `python -m alembic -c alembic.ini check`

The clean-install manual scenario must verify live output, browser refresh, successful dependency-tree evidence, cancellation of a controlled slow command, process-tree termination, and reconstruction classification.