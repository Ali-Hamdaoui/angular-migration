# S2-F01 Verification Record

## Delivered issues

- S2-F01-I01: deterministic, read-only workspace, dependency, builder, test/lint, SSR/PWA/i18n, UI/theme, and state-management scanners.
- S2-F01-I02: checksum-bound evidence persistence, API contracts, and durable discovery events.
- S2-F01-I03: authoritative findings explorer with filters, confidence/unknown labels, source references, and artifact links.
- S2-F01-I04: automated API/persistence/SSE/frontend/security regression coverage and this manual-validation record.

## Security and authority boundary

Discovery reads only the run's `SOURCE_SNAPSHOT` alias. It receives no user-supplied filesystem path, executes no package scripts or shell command, stores only registered artifact identifiers/checksums, and presents repository values as React text rather than HTML. Prerequisite evidence must already be registered and match the requested checksum; stale and tampered requests create neither discovery evidence nor events.

## Automated verification

I04 verifies deterministic persisted inventories, immutable SHA-256 artifact references and ID retrieval/versioning, ordered `DISCOVERY_STARTED`, `SCANNER_COMPLETED`, `DISCOVERY_COMPLETED`, and blocked scanner events, idempotent replay, versioned API retrieval, SSE replay/gap recovery, stale-state rejection, prerequisite-checksum tamper rejection, scanner isolation, redaction, and findings-panel loading/success/unknown/filter/empty/blocked/stale/authorization/backend-failure states. The test fixture is generated under pytest's external temporary root and is not a repository workspace.

## External-fixture evidence

On 2026-07-18, the S2-F01 persistence/API scenario was executed against a generated external Angular-style fixture under `C:\tmp\s2f01-artifact`: an isolated SQLite run, approved G03 record, registered baseline prerequisite, and source snapshot containing `angular.json` and `package.json`. The run produced seven redacted, immutable `02_analysis` inventories; the persisted API/SSE assertion passed, and artifact-ID retrieval plus versioned rewrite preserved the original artifact unchanged. This is reproducible with:

```text
python -m pytest backend/tests/test_discovery_persistence_api_s2_f01.py -q --basetemp C:\tmp\s2f01-artifact
```

A human browser walkthrough is still required before release: this record does not claim an interactive browser session was performed.

## Manual acceptance scenario

1. Start the backend and frontend, then open an approved G03 run with a registered source snapshot and baseline artifact.
2. Trigger discovery and watch the explorer refresh from the backend snapshot/events. Confirm each scanner status and the workspace, dependency/private-package, builder, test/lint, SSR/PWA/i18n, UI-library, and state-management facts.
3. Filter a scanner, inspect confidence/unknown labels and source references, and open each inventory only through its artifact ID. Confirm no absolute source path or secret is shown.
4. Refresh or reconnect after `DISCOVERY_STARTED`; confirm ordered events replay and the completed snapshot returns without a duplicate operation.
5. Submit a stale request and a request with a tampered prerequisite checksum. Confirm the UI gives corrective feedback and no new evidence, workflow event, or state progression appears.
6. Record the run ID, discovery ID, artifact IDs/checksums, and discovery event sequence in the sprint evidence package.

## Scope boundary

Route/backend deep comparison, AI interpretation, compatibility support decisions, migration commands, and workspace mutation are not part of S2-F01.
