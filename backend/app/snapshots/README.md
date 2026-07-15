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
