# API

Owns FastAPI routers, request validation, response shaping, dependency wiring,
and error-envelope adaptation.

Routers must delegate workflow, persistence, execution, artifact, approval, and
assistant behavior to application services. They must not implement state-machine
logic, call repositories directly, execute commands, or infer workflow progress.

## S1-F06 authoritative runs

The versioned `/api/v1/runs` routes expose the real run lifecycle:

- `POST /api/v1/runs` creates exactly one run from an approved, current G01
  preflight and returns its setup artifacts and graph thread ID.
- `POST /api/v1/runs/{runId}/start` performs the guarded source-intake handoff.
- `GET /api/v1/runs/{runId}/state` returns the durable authoritative snapshot.
- `GET /api/v1/runs/{runId}/events` replays ordered events for SSE clients and
  honors `Last-Event-ID`.

The router only maps DTOs and stable domain errors. Run creation, leases,
artifact evidence, transitions, and graph handoff belong to
`MigrationRunService`; an unconfigured graph fails closed rather than falling
back to a mock.
