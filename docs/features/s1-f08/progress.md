# S1-F08 Progress

## Delivered

- S1-F08-I01: deterministic G02 integrity evidence, checksum-bound approval package, and fail-closed domain decisions.
- S1-F08-I02: durable G02 approval persistence, optimistic state-version/idempotency handling, API routes, workflow events, and immutable evidence artifacts.
- S1-F08-I03: Control Tower G02 review panel with fingerprint comparison, evidence links, decision controls, stale handling, and blocked-next-step presentation.
- S1-F08-I04: backend integration/security coverage and frontend API/component coverage.

## Security boundary

G02 approval is accepted only when the source fingerprint still matches the pre-snapshot fingerprint, the snapshot manifest and files pass checksum inspection, and the snapshot evidence is read-only. A failed or stale check cannot establish `BASELINE_SANDBOX` input. Evidence is retained in the run-scoped immutable artifact store and is opened by artifact ID.

## Manual scenario

1. Create an external source snapshot and inspect its manifest, exclusions, copy report, Git metadata, and fingerprints.
2. Open the G02 review surface and confirm the source and snapshot fingerprints match.
3. Approve G02. Confirm the immutable snapshot is shown as the baseline input boundary and the G02 evidence artifacts are linked.
4. Repeat after changing the original source. Confirm the review is stale/rejected and no baseline boundary is established.
5. Repeat after tampering with the snapshot manifest checksum. Confirm the review is stale/rejected and no baseline boundary is established.
6. Repeat a decision with the same idempotency key. Confirm the persisted decision is replayed without new mutation.
