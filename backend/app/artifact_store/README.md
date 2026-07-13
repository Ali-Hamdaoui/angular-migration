# Artifact Store

Owns immutable, checksum-bound artifact persistence and artifact lookup by
artifact ID.

Artifacts are append-only and stage or repair-attempt scoped. This module must
not overwrite evidence, expose arbitrary filesystem paths, decide workflow
state, or publish incomplete delivery output.

Each artifact write creates content plus a `*.meta.json` envelope containing the
schema version, artifact ID, run/stage/attempt identifiers, producer, artifact
type, content type, input hashes, policy version, content hash, relative path,
and timestamp. Existing paths are versioned instead of replaced. Reads support
run-scoped relative paths for compatibility and artifact IDs for UI opening.
