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
