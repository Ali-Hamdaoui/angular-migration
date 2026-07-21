# Cross-Goal Contracts — G07

## Consumes

- `goals/shared/contracts/repair_proposal.schema.json`
- `goals/shared/contracts/repair_review_decision.schema.json`
- `goals/shared/contracts/repair_g10_package.schema.json`
- `goals/shared/contracts/stage_validation_summary.schema.json`
- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`

## Provides

- `goals/shared/contracts/patch_apply_ledger.schema.json`
- `goals/shared/contracts/stage_validation_summary.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
