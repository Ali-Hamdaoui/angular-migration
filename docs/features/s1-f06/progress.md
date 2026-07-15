# S1-F06 ? Authoritative run handoff

## Scope delivered

The approved G01 decision is the only entry point for a real migration run.
`POST /api/v1/runs` validates the durable preflight snapshot, gate decision,
checksums, expiry, active-run exclusivity, and target ownership before it
creates the run and its evidence namespace. The initial `RUN_CREATED` event and
the five setup artifacts are committed with the run record.

`POST /api/v1/runs/{runId}/start` is the only production handoff path. It
persists `RUN_START_ACCEPTED`, invokes the configured source-intake graph with
the durable graph thread ID, and persists `RUN_STARTED` only after the adapter
accepts the handoff. `GET /api/v1/runs/{runId}/state` is the authoritative
snapshot. The SSE endpoint replays ordered workflow events after a browser
disconnect using `Last-Event-ID`.

The frontend treats real run IDs as backend-owned state and keeps the existing
`mock-*` route explicitly isolated for fixture/demo use. It does not approve a
gate, infer a transition, or execute a migration locally.

## Security and recovery boundaries

- A stale, expired, missing, blocked, or unapproved G01 fails before a run ID,
  database row, event, or artifact namespace is created.
- Only one mutating run and one active target claim may exist at a time.
- Run evidence is written under the run artifact namespace and is represented
  by persisted checksums and metadata.
- The default source-intake graph is fail-closed. A missing production graph
  configuration cannot silently become a mock execution.
- A failed graph handoff rolls back the accepted transition, leaving the
  authoritative run in `CREATED` for safe diagnosis or retry.
- Event replay is ordered by durable sequence and the frontend de-duplicates
  event IDs before rendering them.

## Validation

The I04 test coverage includes stale-G01 no-partial-creation, safe graph
handoff failure rollback, artifact metadata/path checks, and frontend rendering
of authoritative snapshots, event history, and evidence.

Manual browser scenario:

1. Start the backend and frontend and complete path validation and G01 approval.
2. Select **Create and start authoritative run**.
3. Confirm the URL contains the returned real `run-*` ID and the dashboard shows
   the source/target, state version, `RUN_CREATED`, and setup artifacts.
4. Disconnect/reconnect the browser and confirm the snapshot and SSE replay do
   not duplicate events.
5. Repeat the start request with an old state version or while another run is
   mutating; confirm the backend returns a conflict and no local transition is
   inferred by the UI.

## Known limitation

The production `JobSupervisor` graph composition and full SQLite restart
reconstruction remain follow-up work in the later S1-F06 execution issue. The
current default graph intentionally fails closed until that production adapter
is configured.
