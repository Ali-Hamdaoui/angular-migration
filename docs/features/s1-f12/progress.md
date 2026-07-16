# S1-F12 — Baseline build, test, and lint matrix

## Scope

Feature 12 records the source application's real pre-migration build, test,
and lint behavior. Existing project targets are reused; the platform does not
change assertions, add tests to the source project, or treat missing tooling as
a pass.

## Issue traceability

- S1-F12-I01: deterministic target discovery and status normalization.
- S1-F12-I02: baseline validation persistence migration and model.
- S1-F12-I03: frontend matrix types, API helpers, and projection component.
- S1-F12-I04: regression, security, and manual-validation evidence.

## Required manual scenario

Run the matrix on the clean Angular fixture, then repeat with:

1. a failing test target;
2. no lint target;
3. an unsupported custom builder; and
4. cancellation during a long-running target.

For each run, verify the target inventory, exact command, status, duration,
exit code, parser summary, raw logs, artifact IDs/checksums, state version, and
event sequence. Verify that the original source files and package/lockfile
fingerprints remain unchanged.

## Security checks

Repository package scripts and Angular configuration are data, not agent
instructions. Discovery is read-only. Unsupported builders are blocked, shell
execution is not authorized by the frontend, and artifact access remains
artifact-ID based. Missing lint is reported as `skipped_not_configured`.

## Validation notes

The local Windows environment has pre-existing permissions issues affecting
pytest temporary directories, the configured SQLite database location, and
some generated cache directories. These limitations must be disclosed with
manual evidence rather than represented as product validation passes.

## Implementation evidence

The S1-F12 backend matrix uses the registered CommandExecutor for each supported target and persists immutable command logs and report artifacts. The required fixture scenarios are covered by backend and frontend automated tests for clean discovery, failed-test parsing, missing lint, unsupported builders, cancellation signalling, API projection, and source-safe read-only discovery. Manual execution remains an operator step against the clean Angular fixture and must record the exact command, state/event sequence, artifact checksums, and source fingerprint before qualification.

## Completion corrections

The application service now finalizes backend worker exceptions as failed matrix
results, prevents subsequent targets from executing after an execution error, and
always registers the target inventory and build generated-output inventories in
the Artifact Store with SHA-256 metadata. Matrix responses expose the persisted
artifact checksum map.

The integration suite covers the matrix API routes, persistence, artifact
registration, failed-test and backend-failure finalization, unsupported builders,
source immutability, real npm fixture execution, and cancellation. The frontend
projects every ordered SSE event into the authoritative workflow-event list and
uses `/api/v1/runs/{runId}/events`, matching the backend route.

### Frontend test environment note

In the restricted Windows agent environment, `npm test -- --run` can fail while
Vite loads its configuration with `Error: spawn EPERM`. This is an environment
process-spawn restriction, not a product assertion failure. Typecheck, lint, and
production build remain runnable; the Vitest suite should be rerun in a normal
local shell or CI worker with child-process spawning permitted.
## Fixture execution evidence

The backend fixture suite now executes real `npm run` processes inside the
baseline sandbox and verifies source immutability:

| Fixture | Result |
|---|---|
| Angular-shaped clean fixture | build, test, and lint passed |
| Failing test fixture | failed status with failed-test output and artifacts |
| Missing lint fixture | `skipped_not_configured` |
| Unsupported custom builder fixture | blocked without execution |
| Long-running cancellation fixture | cancellation finalized as failed matrix with cancelled target |

These are automated operator-equivalent runs. A browser-driven manual UI run
requires a normal local/CI environment because the restricted agent cannot
launch the Vitest child process and has no browser session.