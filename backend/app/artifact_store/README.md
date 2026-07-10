# Artifact Store

Owns immutable, checksum-bound artifact persistence and artifact lookup by
artifact ID.

Artifacts must be append-only and stage or repair-attempt scoped. This module
must not overwrite evidence, expose arbitrary filesystem paths, decide workflow
state, or publish incomplete delivery output.