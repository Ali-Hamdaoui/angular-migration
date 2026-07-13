# Snapshots

Owns immutable source snapshot creation, source manifests, checksums, and source
integrity verification.

Snapshots must never mutate the original source. They must not publish
`migrated-app`, execute commands, or replace workspace lifecycle management.

Canonical Sprint 0 snapshot path:

```text
{target}/.migration-factory/snapshots/{snapshotId}/
```

`SourceManifestBuilder` records deterministic file metadata and SHA-256 content
checksums. `SnapshotService` writes `source-manifest.json` beside the copied
source. `SourceIntegrityVerifier` compares the live source back to that manifest
before delivery.
