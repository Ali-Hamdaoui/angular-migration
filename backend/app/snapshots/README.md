# Snapshots

Owns immutable source snapshot creation, source manifests, checksums, and source
integrity verification.

Snapshots must never mutate the original source. They must not publish
`migrated-app`, execute commands, or replace workspace lifecycle management.