# Authoritative Angular 18 baseline flow

This flow ends at baseline qualification and G03 readiness. It does not run
Angular 18 to 19 migration commands.

## Manual test

1. Configure the backend with a database and operational roots outside this
   repository. Provide the external Angular application path and an external
   target parent path during production preflight.
2. Refresh environment diagnostics so Node, npm, npx, Git, storage, and
   registry readiness are persisted through the command authority.
3. Complete and approve G01, create a run, and press **Start Migration**.
4. Confirm the accepted response contains the run and durable intake job IDs.
   Follow the run SSE stream and verify `SOURCE_INTAKE_QUEUED`,
   `SOURCE_INTAKE_STARTED`, snapshot progress, `SNAPSHOT_CREATED`, and
   `SOURCE_INTAKE_COMPLETED`.
5. Confirm G02 appears without a manual package API call. Approve G02 from the
   authoritative dashboard.
6. Verify the selected runtime profile displays the exact Node/npm/npx
   executables and checksums. If more than one compatible profile exists,
   select one before the worker continues.
7. Verify that the baseline sandbox is under the run-owned external workspace,
   not the source or this repository. Observe real `npm ci` output and its
   registered stdout, stderr, command-log, result, and dependency evidence.
8. Observe discovered build, test, and lint targets. Each configured command
   must run through `CommandExecutor`; absent lint is shown as not configured.
9. Verify the baseline summary and `G03_CREATED` appear only after required
   evidence is registered. Do not approve G03 unless the evidence is complete.
10. Recalculate the original source fingerprint and compare it with the G01
    boundary. The source must remain byte-for-byte unchanged.

## Evidence layout

Run evidence is stored under the registered run artifact root. Source intake
includes source/snapshot manifests, Git metadata, exclusion policy, copy and
fingerprint reports, source validation, and `g02_evidence_index.json`. Runtime,
baseline installation, build/test/lint, qualification, and G03 artifacts are
registered by their existing application services and are retrievable by
artifact ID.

The canonical run-owned layout is:

```text
<external-target-root>/<generated-output>/
└── .migration-factory/
    └── runs/<run-id>/
        ├── source-snapshot/
        ├── baseline-sandbox/
        ├── artifacts/
        │   ├── global/source-snapshots/<snapshot-id>/
        │   ├── global/g02/<snapshot-id>/
        │   ├── global/execution-profile/
        │   └── 01_baseline/
        └── logs/
```

The exact roots come from the run's registered workspace aliases and artifact
root; the external source path and this repository are never used as command
working directories.

## Failure and recovery

Missing or changed source, unsafe links, snapshot verification failures,
missing or invalid `package-lock.json`/`npm-shrinkwrap.json`, incompatible runtimes, registry failures, unauthorized
commands, command failures, and artifact failures leave a durable failed or
blocked record with evidence. A repeated Start request replays the same job
and does not copy a second snapshot. Backend startup re-dispatches queued,
running, and approval-waiting intake jobs; SSE reconnect reads the persisted
run event history from the last sequence.

For a failed step, inspect the persisted event payload first, then retrieve the
listed artifact IDs from the run artifact endpoint. A missing lockfile blocks
before `npm ci`; a failed install prevents build/test/lint; a configured failing
target blocks G03; and absent lint is recorded as
`skipped_not_configured`/`NOT_CONFIGURED`, never as a pass.
