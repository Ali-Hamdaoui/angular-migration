# Generic V2.3 Recovery Hardening

## Scope

Remove incident-specific recovery branching while preserving the proven
Angular migration graph, durable state-version checks, gate authority,
checkpoint safety, and sealed evidence.

## Implementation

1. Add a pure `StageRecoveryPolicyService` that maps typed failure evidence to
   a sanctioned action and denies unsafe or unknown automatic recovery.
2. Move Factory-only test tooling selection to `ProvenStageToolingPolicy` and
   validate target cohorts with structured semantic errors at the producer.
3. Make `StageRecoveryService` the execution owner for generic re-execution and
   stale-gate renewal; keep `TransformationContinuationService` as orchestration.
4. Make workspace-binding selection deterministic with timestamp and ID
   ordering, without altering sealed database evidence.
5. Add focused tests for policy invariance, unknown/dependency/environment/gate
   safety, tooling families, cohort errors, and future-stage IDs.

## Validation

Run only the new and directly impacted focused tests. Verify no exact run ID,
generated stage ID, error-message, package-version, or Angular-specific branch
remains in continuation recovery code, and do not continue Angular 16 to 17.
