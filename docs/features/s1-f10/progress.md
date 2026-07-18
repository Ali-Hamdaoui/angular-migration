# S1-F10 progress

S1-F10 — Create the baseline sandbox and prequalify package, lockfile, registry, and lifecycle scripts.

## Delivered issues

- S1-F10-I01: deterministic baseline sandbox creation, package and lockfile inspection, dependency-source inventory, lifecycle-script audit, execution-profile readiness, and install-authorization domain results.
- S1-F10-I02: durable baseline qualification persistence, typed API routes, optimistic state-version and idempotency handling, ordered workflow events, immutable evidence artifacts, and Alembic migration.
- S1-F10-I03: Control Tower baseline preparation panel with authoritative loading, empty, running, blocked, review, stale, failure, and success states.
- S1-F10-I04: security negatives, regression coverage, API/component verification, and this traceability record.
- Gap closure: cancellation/reconstruction, private registry authentication enforcement, complete lifecycle classifications, missing durable events, detailed evidence projection, and SSE-triggered baseline refresh are covered by the current implementation and tests.

## Evidence and security boundary

The baseline is copied only from the approved G02 snapshot into the registered `BASELINE_SANDBOX` alias. The copy is writable, excludes `node_modules` and generated caches, rejects snapshot/baseline overlap, and can enforce containment beneath the registered run root. Package and lockfile inputs are inspected without rewriting either file. Dependency URLs and lifecycle commands redact embedded credentials before evidence is persisted. Private scoped registries declared in `.npmrc` require explicit private-auth capability. Lifecycle scripts produce allowed, restricted, requires-review, blocked, or unknown classifications. Cancelled copies leave no published sandbox and can be reconstructed from the immutable snapshot.

Prequalification does not install packages and does not execute lifecycle scripts. It records deterministic package-source, lockfile, registry/profile, and script evidence. A missing or invalid lockfile, unsupported source, blocked lifecycle command, unavailable execution profile, or unapproved registry capability remains blocked. Review-required scripts cannot be authorized through the frontend when blockers exist.

## Automated verification

- Backend domain and sandbox tests cover exact lockfile mismatch without file mutation, missing metadata, unsupported dependency sources, lifecycle classifications, snapshot fingerprint mismatch, generated-content exclusion, credential redaction, run-root escape, and source/baseline overlap.
- Backend persistence/API tests cover durable baseline records, six evidence artifacts, ordered events, state-version transitions, and duplicate prequalification replay.
- Frontend tests cover typed versioned routes, empty-to-workspace projection, backend blocker display, and action submission with the authoritative state version.
- Full validation: backend `256 passed, 2 skipped`; frontend `17 test files, 43 tests passed`; frontend TypeScript check and production build passed; Alembic upgrade to head passed on temporary SQLite.

## Manual acceptance scenario

1. Start the backend and frontend, complete the external source path, output path, G01/G02, and ExecutionProfile prerequisites.
2. Open the authoritative run and select **Create baseline sandbox**. Confirm the displayed sandbox is the backend-registered path, the source snapshot remains unchanged, and the input/sandbox fingerprints are visible.
3. Select **Prequalify package**. Inspect lockfile status, dependency-source categories, lifecycle scripts, registry readiness, checksum, and artifact count.
4. Repeat with a review-required lifecycle script. Confirm the UI shows review-required evidence and does not permit install authorization while blockers remain.
5. Repeat with an exact package/lockfile mismatch and an unapproved Git, tarball, or local dependency. Confirm the backend status is blocked, no install command starts, and the original package files remain byte-for-byte unchanged.
6. Submit an action with an old state version. Confirm stale feedback appears and refresh restores the authoritative snapshot.
7. Refresh/reconnect the run. Confirm the same persisted status, ordered events, and artifact references are restored.

## Scope boundary

Actual `npm ci`, npm debug logs, dependency-tree verification, and post-install lockfile checks belong to S1-F11. Baseline build/test/lint belongs to S1-F12. No installation or Angular update is performed by S1-F10.
