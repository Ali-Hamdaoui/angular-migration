# Cross-Goal Contracts — G09

## Consumes

- `goals/shared/contracts/sealed_stage_output.schema.json`
- `goals/shared/contracts/stage_validation_summary.schema.json`
- `goals/shared/contracts/patch_apply_ledger.schema.json`
- `goals/shared/contracts/recovery_decision.schema.json`
- `goals/shared/contracts/assistant_answer.schema.json`
- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`

## Provides

- `goals/shared/contracts/final_assurance_summary.schema.json`
- `goals/shared/contracts/delivery_record.schema.json`
- `goals/shared/contracts/final_report_record.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
