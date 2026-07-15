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
emits ordered `SNAPSHOT_STARTED`, `SNAPSHOT_PROGRESS_UPDATED`, and `SNAPSHOT_CREATED` events, advances the
authoritative run state to `SOURCE_VALIDATED`, and replays duplicate
idempotency requests without copying again.

## S1-F07-I04 verification and security checklist

The snapshot domain is covered by tests for source/platform repository separation,
run-scoped destination containment, symlink rejection, incomplete-copy cleanup,
source mutation detection, policy exclusions, and tamper detection during
inspection. Inspection requires both the manifest and fingerprint evidence and
recomputes each included file checksum before returning the record.

Manual acceptance scenario:

1. Submit an external project path to `POST /api/v1/runs/{runId}/snapshots`.
2. Follow the run SSE stream and confirm `SNAPSHOT_STARTED`, then
   `SNAPSHOT_CREATED` with an ordered sequence.
3. Inspect the returned snapshot and verify the manifest, exclusion policy,
   fingerprint, Git metadata, copy report, and artifact links.
4. Compare the source directory before and after acquisition; the source must
   remain unchanged.
5. Refresh or reconnect the dashboard and confirm the same immutable evidence
   is restored through the GET endpoint.
6. Approve the run only after the snapshot evidence is inspected.
Completed snapshot files and directories are marked read-only after atomic
finalization. Inspection recomputes all manifest checksums, so a privileged
mutation is detected rather than treated as valid evidence. Source traversal
fails closed for symbolic links and Windows reparse points, uses case-stable
ordering, supports long nested paths, and retries transient stat/read/copy
sharing errors.

Failed acquisition emits `SNAPSHOT_FAILED` followed by
`SNAPSHOT_QUARANTINED` after incomplete product-owned data is safely removed.