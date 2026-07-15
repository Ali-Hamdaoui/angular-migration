# S1-F07 — Immutable arbitrary-project source snapshot

## Issue progress

- S1-F07-I01 — Backend / Domain: complete.
- S1-F07-I02 — Database / API / Event / Artifact: complete.
- S1-F07-I03 — Frontend: complete.
- S1-F07-I04 — Testing / Security / Documentation: in progress.

## I04 verification scope

The verification suite protects the snapshot boundary by rejecting source paths
inside the platform repository and snapshot IDs that escape the run-scoped
snapshot root. Inspection validates the manifest checksum, fingerprint evidence,
and every included file checksum. Existing tests also cover link rejection,
source mutation detection, policy exclusions, and cleanup of incomplete copies.

The manual acceptance path is: acquire an external project, inspect the manifest,
exclusions, fingerprint, Git metadata, copy report, and artifact links, prove that
the original source is unchanged, then reconnect the dashboard and verify the
same snapshot remains inspectable before approval.