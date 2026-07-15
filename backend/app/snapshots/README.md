# Snapshot Service

S1-F07 creates and inspects a product-owned immutable source snapshot.

SnapshotService writes only beneath the registered run alias:

```text
<resolved-output-root>/.migration-factory/runs/<run-id>/source-snapshot/
```

The service applies the versioned `source-snapshot-policy-v1` inclusion policy,
records generated-directory exclusions, rejects symbolic links and unsafe
destinations, captures deterministic file checksums, detects source changes
during acquisition, and publishes the completed copy atomically. Completed
snapshots include `source-manifest.json` and
`snapshot-fingerprint.json`; `inspect_snapshot` validates the manifest before
returning its immutable domain record.

I02 persists each run snapshot in the `source_snapshots` table and exposes:

```text
POST /api/v1/runs/{runId}/snapshots
GET  /api/v1/runs/{runId}/snapshots/{snapshotId}
```

A successful creation records six immutable JSON artifacts under the run
artifact root: `source_manifest.json`, `source_git_metadata.json`,
`snapshot_manifest.json`, `exclusion_policy_snapshot.json`,
`snapshot_copy_report.json`, and `snapshot_fingerprint.json`. Creation
emits ordered `SNAPSHOT_STARTED` and `SNAPSHOT_CREATED` events, advances the
authoritative run state to `SOURCE_VALIDATED`, and replays duplicate
idempotency requests without copying again.
